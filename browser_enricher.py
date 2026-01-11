#!/usr/bin/env python3
"""
Browser Enrichment Module for Facebook Profile Processor
Connects to existing Chrome session and enriches database with resolved URLs

USAGE:
    # Step 1: Launch Chrome with debugging
    google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.config/google-chrome"
    
    # Step 2: Log into Facebook in that Chrome window
    
    # Step 3: Run enrichment
    python3 browser_enricher.py --database test_profiles.db
"""

import sqlite3
import time
import random
import argparse
import logging
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def connect_to_chrome():
    """Connect to Chrome with remote debugging enabled"""
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp('http://localhost:9222')
        context = browser.contexts[0]  # Use existing context (logged in)
        page = context.new_page()
        logging.info("✓ Connected to Chrome session")
        return playwright, browser, page
    except Exception as e:
        logging.error(f"✗ Failed to connect to Chrome: {e}")
        logging.error("Make sure Chrome is running with --remote-debugging-port=9222")
        logging.error("\nLaunch command:")
        logging.error("  google-chrome --remote-debugging-port=9222 --user-data-dir=\"$HOME/.config/google-chrome\"")
        raise


def upgrade_schema(conn):
    """Add enrichment columns to existing database"""
    cur = conn.cursor()
    
    # Check if upgrade needed
    cur.execute("PRAGMA table_info(profiles)")
    columns = [col[1] for col in cur.fetchall()]
    
    if 'enrichment_status' in columns:
        logging.info("Database schema already upgraded")
        return
    
    logging.info("Upgrading database schema for enrichment...")
    
    alterations = [
        "ALTER TABLE profiles ADD COLUMN clean_url TEXT",
        "ALTER TABLE profiles ADD COLUMN profile_id TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_resolved_url TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_resolved_username TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_profile_name TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_profile_bio TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_profile_location TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_followers TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_profile_pic_url TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_enriched_at TEXT",
        "ALTER TABLE profiles ADD COLUMN browser_error TEXT",
        "ALTER TABLE profiles ADD COLUMN enrichment_status TEXT DEFAULT 'pending'"
    ]
    
    for sql in alterations:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
    
    # Create index
    try:
        cur.execute("CREATE INDEX idx_enrichment_status ON profiles(enrichment_status)")
    except sqlite3.OperationalError:
        pass
    
    # Backfill profile_id and clean_url from existing data
    cur.execute("""
        UPDATE profiles 
        SET profile_id = (
            SELECT SUBSTR(input_url, 
                INSTR(input_url, '/marketplace/profile/') + 21,
                INSTR(SUBSTR(input_url, INSTR(input_url, '/marketplace/profile/') + 21), '/') - 1
            )
        )
        WHERE profile_id IS NULL 
        AND input_url LIKE '%/marketplace/profile/%'
    """)
    
    cur.execute("""
        UPDATE profiles 
        SET clean_url = 'https://www.facebook.com/' || profile_id
        WHERE clean_url IS NULL AND profile_id IS NOT NULL
    """)
    
    conn.commit()
    logging.info("✓ Schema upgraded successfully")


def get_pending_profiles(db_path):
    """Get profiles that need enrichment (Graph API compatible)"""
    conn = sqlite3.connect(db_path)

    # Upgrade schema if needed
    upgrade_schema(conn)

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get pending profiles using new schema
    cur.execute("""
        SELECT id, fb_id, fb_profile_url, input_url,
               legacy_profile_id, legacy_clean_url
        FROM profiles
        WHERE enrichment_status = 'pending'
        AND (fb_id IS NOT NULL OR legacy_profile_id IS NOT NULL)
        AND (http_error IS NULL OR http_error = '')
        ORDER BY id
    """)

    profiles = cur.fetchall()
    conn.close()
    return profiles


def enrich_profile(page, profile_id):
    """Navigate to profile and extract data"""
    numeric_url = f'https://www.facebook.com/{profile_id}'

    try:
        # Navigate to profile
        logging.debug(f"Navigating to {numeric_url}")
        page.goto(numeric_url, wait_until='domcontentloaded', timeout=30000)

        # Wait for page to settle
        time.sleep(2)

        # Get resolved URL (after redirect)
        resolved_url = page.url
        username = resolved_url.split('facebook.com/')[-1].split('?')[0].strip('/')

        # Check if profile is accessible
        page_text = page.content().lower()
        error_indicators = [
            'this content isn\'t available',
            'this page isn\'t available',
            'the link you followed may be broken',
            'sorry, this page isn\'t available'
        ]

        for indicator in error_indicators:
            if indicator in page_text:
                return {
                    'fb_link': resolved_url,
                    'fb_username': username,
                    'enrichment_error': f'Profile not accessible: {indicator}',
                    'enrichment_status': 'failed',
                    'enrichment_method': 'browser'
                }

        # Extract profile data using Graph API compatible field names
        data = {
            'fb_link': resolved_url,  # Graph API: link
            'fb_username': username,  # Graph API: username
            'fb_name': None,  # Graph API: name
            'fb_bio': None,  # Graph API: bio
            'fb_location_name': None,  # Graph API: location.name
            'fb_followers_count': None,  # Graph API: followers_count
            'fb_picture_url': None,  # Graph API: picture.data.url
            'enriched_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'enrichment_error': None,
            'enrichment_status': 'enriched',
            'enrichment_method': 'browser'
        }

        # Name - try multiple selectors
        name_selectors = ['h1', '[role="main"] h1', 'span[dir="auto"] > span']
        for selector in name_selectors:
            try:
                name = page.locator(selector).first.inner_text(timeout=3000)
                if name and len(name) > 0:
                    data['fb_name'] = name
                    break
            except:
                continue

        # Bio/Intro
        try:
            intro = page.locator('[data-pagelet*="ProfileIntro"]').first.inner_text(timeout=3000)
            data['fb_bio'] = intro
        except:
            pass

        # Location
        try:
            location = page.locator('a[href*="/maps/place"]').first.inner_text(timeout=3000)
            data['fb_location_name'] = location
        except:
            pass

        # Followers (extract number)
        try:
            followers_text = page.locator('a:has-text("follower")').first.inner_text(timeout=3000)
            # Extract number from text like "1.2K followers"
            import re
            match = re.search(r'([\d,.]+[KMB]?)', followers_text)
            if match:
                data['fb_followers_count'] = match.group(1)
        except:
            pass

        # Profile picture (from meta tag - most reliable)
        try:
            pic = page.locator('meta[property="og:image"]').get_attribute('content')
            data['fb_picture_url'] = pic
        except:
            pass

        logging.info(f"✓ Enriched: {username} → {data['fb_name']}")
        return data

    except Exception as e:
        logging.error(f"✗ Failed to enrich {profile_id}: {e}")
        return {
            'enrichment_error': str(e),
            'enrichment_status': 'failed',
            'enriched_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'enrichment_method': 'browser'
        }


def update_profile(conn, profile_id_db, enrichment_data):
    """Update database with enriched data"""
    cur = conn.cursor()

    # Build UPDATE statement dynamically
    set_clause = ', '.join([f"{k} = ?" for k in enrichment_data.keys()])
    values = list(enrichment_data.values()) + [profile_id_db]

    sql = f"UPDATE profiles SET {set_clause} WHERE id = ?"
    cur.execute(sql, values)
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Browser Enrichment for FB Profile Processor')
    parser.add_argument('--database', '-d', default='test_profiles.db',
                       help='Path to database file (default: test_profiles.db)')
    parser.add_argument('--limit', '-l', type=int, default=None,
                       help='Limit number of profiles to enrich')
    parser.add_argument('--delay', type=float, default=3.0,
                       help='Delay between requests in seconds (default: 3.0)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Connect to database
    profiles = get_pending_profiles(args.database)

    if not profiles:
        logging.info("✓ No profiles need enrichment")
        return

    logging.info(f"Found {len(profiles)} profiles to enrich")

    if args.limit:
        profiles = profiles[:args.limit]
        logging.info(f"Limiting to {args.limit} profiles")

    # Connect to Chrome
    playwright, browser, page = connect_to_chrome()

    conn = sqlite3.connect(args.database)

    try:
        success_count = 0
        error_count = 0

        for i, profile in enumerate(profiles, 1):
            percent = (i / len(profiles)) * 100
            # Use new schema fields with fallback to legacy
            profile_id = profile['fb_id'] or profile['legacy_profile_id']
            logging.info(f"[{i}/{len(profiles)}] ({percent:.1f}%) Profile ID: {profile_id}")

            # Enrich
            enrichment_data = enrich_profile(page, profile_id)

            # Update database
            update_profile(conn, profile['id'], enrichment_data)

            if enrichment_data.get('enrichment_status') == 'enriched':
                success_count += 1
            else:
                error_count += 1

            # Human-like delay
            if i < len(profiles):
                delay = args.delay + random.uniform(-0.5, 0.5)
                logging.debug(f"Waiting {delay:.1f}s before next request...")
                time.sleep(delay)

        logging.info("="*60)
        logging.info("ENRICHMENT COMPLETE")
        logging.info(f"Total: {len(profiles)}, Success: {success_count}, Errors: {error_count}")
        logging.info(f"Success rate: {(success_count/len(profiles)*100):.1f}%")
        logging.info("="*60)

    finally:
        conn.close()
        page.close()
        browser.close()
        playwright.stop()


if __name__ == '__main__':
    main()

