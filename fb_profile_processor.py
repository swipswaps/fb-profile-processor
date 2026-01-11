#!/usr/bin/env python3
"""
Facebook Profile URL Processor - Production Version
Transforms Marketplace URLs, fetches metadata, stores in SQLite database

FEATURES:
- Deduplication (skip already-processed URLs)
- Resume capability (process only pending URLs)
- Proper retry logic with exponential backoff
- Command-line arguments
- Progress indicators with percentage
- File + console logging
- Comprehensive error handling
- Export to JSON/CSV/SQL formats

USAGE:
    python3 fb_profile_processor.py --input links.txt
    python3 fb_profile_processor.py --help
"""

import sqlite3
import time
import sys
import argparse
import logging
import json
import csv
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser
from html import unescape

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error


# ======================
# SCHEMA DETECTION
# ======================

def detect_schema_version(conn):
    """
    Detect database schema version

    Returns:
        'new': Facebook API compatible schema (fb_id, fb_name, etc.)
        'old': Legacy schema (profile_id, page_title, etc.)
    """
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(profiles)")
    columns = {row[1] for row in cur.fetchall()}

    # Check for new schema marker column
    if 'fb_id' in columns:
        return 'new'
    else:
        return 'old'


def get_schema_field_map(schema_version):
    """
    Get field mapping for schema version

    Returns dict mapping logical field names to actual column names
    """
    if schema_version == 'new':
        return {
            'id_field': 'fb_id',
            'username_field': 'fb_username',
            'name_field': 'fb_name',
            'profile_url_field': 'fb_profile_url',
            'error_field': 'http_error',
            'fetched_at_field': 'http_fetched_at',
            'picture_field': 'fb_picture_url',
            'link_field': 'fb_link',
            'bio_field': 'fb_bio',
            'location_field': 'fb_location_name'
        }
    else:  # old schema
        return {
            'id_field': 'profile_id',
            'username_field': 'browser_resolved_username',
            'name_field': 'page_title',
            'profile_url_field': 'clean_url',
            'error_field': 'error',
            'fetched_at_field': 'fetched_at',
            'picture_field': 'browser_profile_pic_url',
            'link_field': 'resolved_url',
            'bio_field': 'browser_profile_bio',
            'location_field': 'browser_profile_location'
        }


# ======================
# HTML METADATA PARSER
# ======================

class MetaParser(HTMLParser):
    """Parse HTML to extract page title and OpenGraph metadata"""
    def __init__(self):
        super().__init__()
        self.title = None
        self.og_title = None
        self.og_description = None
        self._in_title = False
        self._title_content = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self._in_title = True
            self._title_content = []

        if tag == "meta":
            prop = attrs.get("property", "")
            content = attrs.get("content", "")

            if prop == "og:title" and content:
                self.og_title = unescape(content.strip())
            elif prop == "og:description" and content:
                self.og_description = unescape(content.strip())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            if self._title_content and not self.title:
                self.title = unescape(''.join(self._title_content).strip())

    def handle_data(self, data):
        if self._in_title:
            self._title_content.append(data)


# ======================
# DATABASE
# ======================

def init_db(db_file):
    """Initialize SQLite database with Facebook Graph API v24.0 compatible schema"""
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    # Create table with Graph API v24.0 compatible schema (Rule 28)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            -- Primary key
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            -- Input tracking
            input_url TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),

            -- Stage 1: HTTP Collection (Basic)
            http_status INTEGER,
            http_error TEXT,
            http_fetched_at TEXT,

            -- Facebook Graph API Standard Fields (v24.0 compatible)
            -- Core identity
            fb_id TEXT UNIQUE,
            fb_username TEXT,
            fb_name TEXT,
            fb_first_name TEXT,
            fb_last_name TEXT,
            fb_middle_name TEXT,

            -- Contact & demographics
            fb_email TEXT,
            fb_gender TEXT,
            fb_birthday TEXT,
            fb_age_range_min INTEGER,
            fb_age_range_max INTEGER,

            -- Profile content
            fb_bio TEXT,
            fb_quotes TEXT,
            fb_website TEXT,

            -- Location data (structured)
            fb_location_name TEXT,
            fb_location_id TEXT,
            fb_hometown_name TEXT,
            fb_hometown_id TEXT,

            -- Profile URLs
            fb_link TEXT,
            fb_profile_url TEXT,
            fb_vanity_url TEXT,

            -- Media
            fb_picture_url TEXT,
            fb_picture_is_silhouette INTEGER,
            fb_cover_source TEXT,
            fb_cover_id TEXT,
            local_picture_path TEXT,

            -- Social metrics
            fb_followers_count INTEGER,
            fb_friends_count INTEGER,

            -- Metadata
            fb_locale TEXT,
            fb_timezone INTEGER,
            fb_verified INTEGER,
            fb_is_verified INTEGER,

            -- Enrichment tracking
            enrichment_status TEXT DEFAULT 'pending',
            enrichment_method TEXT,
            enriched_at TEXT,
            enrichment_error TEXT,

            -- Legacy compatibility
            legacy_clean_url TEXT,
            legacy_profile_id TEXT,
            legacy_og_title TEXT,
            legacy_og_description TEXT,
            legacy_page_title TEXT
        )
    """)

    # Create indexes for faster lookups (Rule 11)
    # Schema-aware: only create indexes for columns that exist
    schema_version = detect_schema_version(conn)

    if schema_version == 'new':
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_input_url ON profiles(input_url)",
            "CREATE INDEX IF NOT EXISTS idx_fb_id ON profiles(fb_id)",
            "CREATE INDEX IF NOT EXISTS idx_fb_username ON profiles(fb_username)",
            "CREATE INDEX IF NOT EXISTS idx_enrichment_status ON profiles(enrichment_status)",
            "CREATE INDEX IF NOT EXISTS idx_created_at ON profiles(created_at)"
        ]
    else:  # old schema
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_input_url ON profiles(input_url)",
            "CREATE INDEX IF NOT EXISTS idx_profile_id ON profiles(profile_id)",
            "CREATE INDEX IF NOT EXISTS idx_clean_url ON profiles(clean_url)",
            "CREATE INDEX IF NOT EXISTS idx_enrichment_status ON profiles(enrichment_status)",
            "CREATE INDEX IF NOT EXISTS idx_fetched_at ON profiles(fetched_at)"
        ]

    for idx_sql in indexes:
        try:
            cur.execute(idx_sql)
        except sqlite3.OperationalError as e:
            logging.warning(f"Could not create index: {e}")
            # Continue - index creation is not critical

    conn.commit()

    # Verify schema (Rule 11)
    cur.execute("PRAGMA table_info(profiles)")
    schema = cur.fetchall()
    logging.debug(f"Database schema verified: {len(schema)} columns")

    return conn


def url_exists(cur, url):
    """Check if URL already processed"""
    cur.execute("SELECT id FROM profiles WHERE input_url = ?", (url,))
    return cur.fetchone() is not None


# ======================
# URL TRANSFORMATION
# ======================

def transform_url(url):
    """Transform marketplace URL to clean profile URL (Rule 27)"""
    import re
    # Extract ID from marketplace/profile/{ID}/?params
    pattern = r'facebook\.com/marketplace/profile/(\d+)'
    match = re.search(pattern, url)
    if match:
        profile_id = match.group(1)
        return {
            'clean': f'https://www.facebook.com/{profile_id}',
            'id': profile_id,
            'valid': True
        }
    return {'clean': None, 'id': None, 'valid': False}


# ======================
# FETCH + RESOLVE
# ======================

def fetch_profile(url, timeout=15):
    """Fetch URL and extract metadata with retry logic (Rule 12)"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; profile-resolver/1.0)"
    }

    max_attempts = 3
    base_delay = 2  # seconds

    for attempt in range(max_attempts):
        try:
            if HAS_REQUESTS:
                r = requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True
                )
                html_content = r.text
                resolved_url = r.url
                http_status = r.status_code
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    html_content = response.read().decode('utf-8', errors='ignore')
                    resolved_url = response.geturl()
                    http_status = response.getcode()

            # Parse HTML metadata (Rule 19)
            parser = MetaParser()
            try:
                parser.feed(html_content)
            except Exception as parse_error:
                logging.warning(f"HTML parsing error: {parse_error}")

            return {
                "resolved_url": resolved_url,
                "http_status": http_status,
                "page_title": parser.title,
                "og_title": parser.og_title,
                "og_description": parser.og_description,
                "fetched_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                "error": None
            }

        except Exception as e:
            error_msg = str(e)

            # Check if we should retry (exponential backoff)
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logging.warning(f"Attempt {attempt + 1} failed: {error_msg}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logging.error(f"All {max_attempts} attempts failed: {error_msg}")
                return {
                    "resolved_url": None,
                    "http_status": None,
                    "page_title": None,
                    "og_title": None,
                    "og_description": None,
                    "fetched_at": datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                    "error": error_msg
                }


# ======================
# EXPORT FUNCTIONS
# ======================

def export_to_json(db_file, output_file):
    """Export database to JSON format"""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM profiles")
    rows = [dict(row) for row in cur.fetchall()]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    conn.close()
    logging.info(f"Exported {len(rows)} records to {output_file}")


def export_to_csv(db_file, output_file):
    """Export database to CSV format"""
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    cur.execute("SELECT * FROM profiles")
    rows = cur.fetchall()

    # Get column names
    columns = [desc[0] for desc in cur.description]

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)

    conn.close()
    logging.info(f"Exported {len(rows)} records to {output_file}")


def export_to_sql(db_file, output_file):
    """Export database to SQL dump format"""
    conn = sqlite3.connect(db_file)

    with open(output_file, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(f'{line}\n')

    conn.close()
    logging.info(f"Exported SQL dump to {output_file}")



# ======================
# MAIN
# ======================

def process_single_url(url, db_file, timeout=15):
    """
    Process a single URL and return result

    Args:
        url: Facebook profile URL to process
        db_file: Path to SQLite database
        timeout: HTTP request timeout in seconds

    Returns:
        dict with keys: success, url, profile_id, error
    """
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    try:
        # Check if already exists
        if url_exists(cur, url):
            conn.close()
            return {
                'success': False,
                'url': url,
                'profile_id': None,
                'error': 'URL already processed'
            }

        # Transform URL
        transformed = transform_url(url)

        if not transformed['valid']:
            # Store as error
            cur.execute("""
                INSERT INTO profiles (
                    input_url, fb_id, fb_username,
                    fb_profile_url, http_status,
                    legacy_page_title, legacy_og_title, legacy_og_description,
                    http_fetched_at, http_error, enrichment_status,
                    legacy_clean_url, legacy_profile_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url, None, None, None, None, None, None, None,
                datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'Invalid URL format: not a marketplace profile URL',
                'failed',
                None, None
            ))
            conn.commit()
            conn.close()
            return {
                'success': False,
                'url': url,
                'profile_id': None,
                'error': 'Invalid URL format'
            }

        clean_url = transformed['clean']
        profile_id = transformed['id']

        # Fetch profile
        result = fetch_profile(clean_url, timeout)

        # Store in database with Graph API compatible fields
        cur.execute("""
            INSERT INTO profiles (
                input_url, fb_id, fb_username,
                fb_profile_url, http_status,
                legacy_page_title, legacy_og_title, legacy_og_description,
                http_fetched_at, http_error, enrichment_status,
                legacy_clean_url, legacy_profile_id, enrichment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            profile_id,  # fb_id
            None,  # fb_username (will be enriched later)
            clean_url,  # fb_profile_url
            result.get('http_status'),
            result.get('page_title'),
            result.get('og_title'),
            result.get('og_description'),
            datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            result.get('error'),
            'pending' if not result.get('error') else 'failed',
            clean_url,  # legacy_clean_url
            profile_id,  # legacy_profile_id
            'http'  # enrichment_method
        ))
        conn.commit()
        conn.close()

        return {
            'success': result.get('error') is None,
            'url': url,
            'profile_id': profile_id,
            'error': result.get('error')
        }

    except Exception as e:
        conn.close()
        return {
            'success': False,
            'url': url,
            'profile_id': None,
            'error': str(e)
        }


def process_urls_batch(urls, db_file, rate_limit=1.0, timeout=15, progress_callback=None):
    """
    Process multiple URLs with progress tracking

    Args:
        urls: List of URLs to process
        db_file: Path to SQLite database
        rate_limit: Delay between requests in seconds
        timeout: HTTP request timeout in seconds
        progress_callback: Optional function(current, total, url, result) called after each URL

    Returns:
        dict with keys: total, success, errors, skipped, results
    """
    import time

    # Initialize database if needed
    init_db(db_file)

    results = []
    success_count = 0
    error_count = 0
    skipped_count = 0

    for i, url in enumerate(urls, 1):
        result = process_single_url(url, db_file, timeout)
        results.append(result)

        if result['error'] == 'URL already processed':
            skipped_count += 1
        elif result['success']:
            success_count += 1
        else:
            error_count += 1

        # Call progress callback
        if progress_callback:
            progress_callback(i, len(urls), url, result)

        # Rate limiting (except for last URL)
        if i < len(urls):
            time.sleep(rate_limit)

    return {
        'total': len(urls),
        'success': success_count,
        'errors': error_count,
        'skipped': skipped_count,
        'results': results
    }


def get_profile_by_id(db_file, profile_id):
    """Get profile record by database ID"""
    conn = sqlite3.connect(db_file)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = cur.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def update_profile(db_file, profile_id, updates):
    """
    Update profile record

    Args:
        db_file: Path to SQLite database
        profile_id: Database ID of profile to update
        updates: Dict of column_name: new_value pairs

    Returns:
        bool: True if successful, False otherwise
    """
    if not updates:
        return False

    try:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        # Build UPDATE query
        set_clause = ", ".join([f"{col} = ?" for col in updates.keys()])
        values = list(updates.values()) + [profile_id]

        query = f"UPDATE profiles SET {set_clause} WHERE id = ?"
        cur.execute(query, values)

        conn.commit()
        rows_affected = cur.rowcount
        conn.close()

        return rows_affected > 0

    except Exception as e:
        logging.error(f"Error updating profile {profile_id}: {e}")
        return False


def delete_profile(db_file, profile_id):
    """
    Delete profile record

    Args:
        db_file: Path to SQLite database
        profile_id: Database ID of profile to delete

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        cur.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))

        conn.commit()
        rows_affected = cur.rowcount
        conn.close()

        return rows_affected > 0

    except Exception as e:
        logging.error(f"Error deleting profile {profile_id}: {e}")
        return False


def main():
    """Main processing loop"""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='Facebook Profile URL Processor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use defaults
  %(prog)s --input urls.txt --output db.db   # Custom files
  %(prog)s --rate-limit 2.0                   # 2 second delay
  %(prog)s --timeout 30                       # 30 second timeout
  %(prog)s --export-json output.json          # Export to JSON
        """
    )
    parser.add_argument('--input', '-i',
                       default='links.txt',
                       help='Input file with URLs (default: links.txt)')
    parser.add_argument('--output', '-o',
                       default='facebook_profiles.db',
                       help='Output SQLite database (default: facebook_profiles.db)')
    parser.add_argument('--rate-limit', '-r',
                       type=float,
                       default=1.0,
                       help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--timeout', '-t',
                       type=int,
                       default=15,
                       help='HTTP request timeout in seconds (default: 15)')
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--log-file',
                       default='processing.log',
                       help='Log file path (default: processing.log)')
    parser.add_argument('--export-json',
                       help='Export results to JSON file')
    parser.add_argument('--export-csv',
                       help='Export results to CSV file')
    parser.add_argument('--export-sql',
                       help='Export results to SQL dump file')

    args = parser.parse_args()

    # Setup logging (Rule 25)
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(args.log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Validate input file
    input_file = Path(args.input)
    if not input_file.exists():
        logging.error(f"Input file not found: {input_file}")
        sys.exit(1)

    # Read URLs from file
    logging.info(f"Reading URLs from {input_file}")
    urls = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            if line.startswith('http'):
                urls.append(line)
            else:
                logging.warning(f"Line {line_num}: Invalid URL format, skipping: {line}")

    if not urls:
        logging.error("No valid URLs found in input file")
        sys.exit(1)

    logging.info(f"Found {len(urls)} URLs to process")

    # Initialize database
    db_file = Path(args.output)
    conn = init_db(db_file)
    cur = conn.cursor()

    # Check for duplicates and filter (Rule 11)
    urls_to_process = []
    skipped = 0
    for url in urls:
        if url_exists(cur, url):
            logging.debug(f"Skipping already-processed URL: {url}")
            skipped += 1
        else:
            urls_to_process.append(url)

    if skipped > 0:
        logging.info(f"Skipped {skipped} already-processed URLs")

    if not urls_to_process:
        logging.info("No new URLs to process")
        conn.close()

        # Handle exports if requested
        if args.export_json:
            export_to_json(db_file, args.export_json)
        if args.export_csv:
            export_to_csv(db_file, args.export_csv)
        if args.export_sql:
            export_to_sql(db_file, args.export_sql)

        return

    logging.info(f"Processing {len(urls_to_process)} new URLs")

    # Process each URL
    success_count = 0
    error_count = 0

    for i, url in enumerate(urls_to_process, 1):
        percent = (i / len(urls_to_process)) * 100
        logging.info(f"[{i}/{len(urls_to_process)}] ({percent:.1f}%) Processing: {url}")

        # Transform URL (Rule 27)
        transformed = transform_url(url)

        if not transformed['valid']:
            logging.warning(f"Invalid URL format (not a marketplace URL): {url}")
            # Store as error
            cur.execute("""
                INSERT INTO profiles (
                    input_url, fb_id, fb_username,
                    fb_profile_url, http_status,
                    legacy_page_title, legacy_og_title, legacy_og_description,
                    http_fetched_at, http_error, enrichment_status,
                    legacy_clean_url, legacy_profile_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url, None, None, None, None, None, None, None,
                datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                'Invalid URL format: not a marketplace profile URL',
                'failed',
                None, None
            ))
            conn.commit()
            error_count += 1
            continue

        clean_url = transformed['clean']
        profile_id = transformed['id']

        logging.debug(f"Transformed to: {clean_url} (ID: {profile_id})")

        # Fetch profile data (Rule 12)
        data = fetch_profile(clean_url, timeout=args.timeout)

        # Store in database with Graph API compatible fields (Rule 11 - transactions)
        cur.execute("""
            INSERT INTO profiles (
                input_url,
                fb_id,
                fb_username,
                fb_profile_url,
                http_status,
                legacy_page_title,
                legacy_og_title,
                legacy_og_description,
                http_fetched_at,
                http_error,
                enrichment_status,
                legacy_clean_url,
                legacy_profile_id,
                enrichment_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            profile_id,  # fb_id
            None,  # fb_username (enriched later)
            clean_url,  # fb_profile_url
            data["http_status"],
            data["page_title"],
            data["og_title"],
            data["og_description"],
            data["fetched_at"],
            data["error"],
            'pending' if not data["error"] else 'failed',
            clean_url,  # legacy_clean_url
            profile_id,  # legacy_profile_id
            'http'  # enrichment_method
        ))

        conn.commit()

        # Log results
        if data["error"]:
            logging.error(f"Failed: {data['error']}")
            error_count += 1
        else:
            logging.info(f"Success: Status {data['http_status']}, Title: {data.get('page_title', 'N/A')}")
            success_count += 1

        # Rate limiting (Rule 12)
        if i < len(urls_to_process):
            time.sleep(args.rate_limit)

    conn.close()

    # Final summary (Rule 21)
    logging.info("=" * 60)
    logging.info("PROCESSING COMPLETE")
    logging.info(f"Database: {db_file}")
    logging.info(f"Total processed: {len(urls_to_process)}")
    logging.info(f"Successful: {success_count}")
    logging.info(f"Errors: {error_count}")
    logging.info(f"Success rate: {(success_count / len(urls_to_process) * 100):.1f}%")
    logging.info("=" * 60)

    # Handle exports if requested
    if args.export_json:
        export_to_json(db_file, args.export_json)
    if args.export_csv:
        export_to_csv(db_file, args.export_csv)
    if args.export_sql:
        export_to_sql(db_file, args.export_sql)

    logging.info("\nTo view results:")
    logging.info(f"  sqlite3 {db_file}")
    logging.info("  SELECT * FROM profiles;")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.exception("Fatal error")
        sys.exit(1)

