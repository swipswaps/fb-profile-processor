#!/usr/bin/env python3
"""
Database Schema Upgrade to Facebook Graph API Compatible Structure
Migrates existing data to future-proof schema aligned with Graph API v24.0

USAGE:
    python3 schema_upgrade_v2.py --database facebook_profiles.db
"""

import sqlite3
import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# Facebook Graph API v24.0 compatible schema
GRAPH_API_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles_v2 (
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
    fb_id TEXT UNIQUE,                    -- Graph API: id
    fb_username TEXT,                     -- Graph API: username (deprecated but useful)
    fb_name TEXT,                         -- Graph API: name
    fb_first_name TEXT,                   -- Graph API: first_name
    fb_last_name TEXT,                    -- Graph API: last_name
    fb_middle_name TEXT,                  -- Graph API: middle_name
    
    -- Contact & demographics
    fb_email TEXT,                        -- Graph API: email (requires permission)
    fb_gender TEXT,                       -- Graph API: gender
    fb_birthday TEXT,                     -- Graph API: birthday
    fb_age_range_min INTEGER,             -- Graph API: age_range.min
    fb_age_range_max INTEGER,             -- Graph API: age_range.max
    
    -- Profile content
    fb_bio TEXT,                          -- Graph API: bio / about
    fb_quotes TEXT,                       -- Graph API: quotes
    fb_website TEXT,                      -- Graph API: website
    
    -- Location data (structured)
    fb_location_name TEXT,                -- Graph API: location.name
    fb_location_id TEXT,                  -- Graph API: location.id
    fb_hometown_name TEXT,                -- Graph API: hometown.name
    fb_hometown_id TEXT,                  -- Graph API: hometown.id
    
    -- Profile URLs
    fb_link TEXT,                         -- Graph API: link (canonical profile URL)
    fb_profile_url TEXT,                  -- Resolved numeric URL (e.g., facebook.com/100...)
    fb_vanity_url TEXT,                   -- Vanity URL (e.g., facebook.com/john.doe)
    
    -- Media
    fb_picture_url TEXT,                  -- Graph API: picture.data.url
    fb_picture_is_silhouette INTEGER,     -- Graph API: picture.data.is_silhouette
    fb_cover_source TEXT,                 -- Graph API: cover.source
    fb_cover_id TEXT,                     -- Graph API: cover.id
    local_picture_path TEXT,              -- Local downloaded image
    
    -- Social metrics
    fb_followers_count INTEGER,           -- Graph API: followers_count (Page only)
    fb_friends_count INTEGER,             -- Graph API: friends (requires permission)
    
    -- Metadata
    fb_locale TEXT,                       -- Graph API: locale
    fb_timezone INTEGER,                  -- Graph API: timezone
    fb_verified INTEGER,                  -- Graph API: verified
    fb_is_verified INTEGER,               -- Graph API: is_verified
    
    -- Enrichment tracking
    enrichment_status TEXT DEFAULT 'pending',  -- pending, enriched, failed, skipped
    enrichment_method TEXT,               -- http, browser, api
    enriched_at TEXT,
    enrichment_error TEXT,
    
    -- Legacy compatibility (for migration)
    legacy_clean_url TEXT,
    legacy_profile_id TEXT,
    legacy_og_title TEXT,
    legacy_og_description TEXT,
    legacy_page_title TEXT
)
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_fb_id ON profiles_v2(fb_id)",
    "CREATE INDEX IF NOT EXISTS idx_fb_username ON profiles_v2(fb_username)",
    "CREATE INDEX IF NOT EXISTS idx_enrichment_status ON profiles_v2(enrichment_status)",
    "CREATE INDEX IF NOT EXISTS idx_input_url ON profiles_v2(input_url)",
    "CREATE INDEX IF NOT EXISTS idx_created_at ON profiles_v2(created_at)"
]


def migrate_database(db_path):
    """Migrate existing database to new schema"""
    logging.info(f"Starting migration for {db_path}")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if old table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'")
    old_table_exists = cur.fetchone() is not None

    if not old_table_exists:
        logging.info("No existing 'profiles' table found. Creating new schema...")
        cur.execute(GRAPH_API_SCHEMA)
        for idx_sql in INDEXES:
            cur.execute(idx_sql)
        conn.commit()
        logging.info("✅ New schema created successfully")
        conn.close()
        return

    # Create new table
    logging.info("Creating new Graph API compatible schema...")
    cur.execute(GRAPH_API_SCHEMA)

    # Migrate data from old schema
    logging.info("Migrating existing data...")
    cur.execute("""
        INSERT INTO profiles_v2 (
            input_url, http_status, http_error, http_fetched_at,
            fb_id, fb_username, fb_name, fb_bio, fb_location_name,
            fb_picture_url, local_picture_path, fb_followers_count,
            fb_profile_url, fb_link,
            enrichment_status, enriched_at, enrichment_error,
            legacy_clean_url, legacy_profile_id, legacy_og_title,
            legacy_og_description, legacy_page_title
        )
        SELECT 
            input_url, http_status, error, fetched_at,
            profile_id, browser_resolved_username, browser_profile_name,
            browser_profile_bio, browser_profile_location,
            browser_profile_pic_url, local_image_path, browser_followers,
            clean_url, browser_resolved_url,
            enrichment_status, browser_enriched_at, browser_error,
            clean_url, profile_id, og_title, og_description, page_title
        FROM profiles
    """)

    rows_migrated = cur.rowcount
    logging.info(f"✅ Migrated {rows_migrated} rows")

    # Create indexes
    for idx_sql in INDEXES:
        cur.execute(idx_sql)

    # Rename tables
    logging.info("Backing up old table...")
    cur.execute("ALTER TABLE profiles RENAME TO profiles_old_backup")
    cur.execute("ALTER TABLE profiles_v2 RENAME TO profiles")

    conn.commit()
    logging.info("✅ Migration complete!")
    logging.info(f"   Old table backed up as 'profiles_old_backup'")
    logging.info(f"   New table 'profiles' is now active")

    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Upgrade database to Graph API compatible schema')
    parser.add_argument('--database', '-d', required=True, help='Database file path')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')

    args = parser.parse_args()

    if not Path(args.database).exists():
        logging.error(f"Database file not found: {args.database}")
        exit(1)

    if args.dry_run:
        logging.info("DRY RUN MODE - No changes will be made")
        logging.info(f"Would migrate: {args.database}")
        exit(0)

    migrate_database(args.database)

