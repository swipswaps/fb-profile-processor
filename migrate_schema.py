#!/usr/bin/env python3
"""
Database Schema Migration Script
Upgrades existing profiles table to support browser enrichment (future)

USAGE:
    python3 migrate_schema.py --database test_profiles.db
    python3 migrate_schema.py --database test_profiles.db --dry-run
"""

import sqlite3
import argparse
import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def get_current_columns(conn):
    """Get list of current column names"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(profiles)")
    return [col[1] for col in cur.fetchall()]


def upgrade_schema(conn, dry_run=False):
    """Add new columns to profiles table"""
    cur = conn.cursor()

    # Get current columns
    existing_columns = get_current_columns(conn)
    logging.info(f"Current schema has {len(existing_columns)} columns")

    # Define new columns to add
    new_columns = [
        # Stage 1: HTTP Collection enhancements
        ("clean_url", "TEXT"),
        ("profile_id", "TEXT"),

        # Stage 2: Browser Enrichment (future-ready)
        ("browser_resolved_url", "TEXT"),
        ("browser_resolved_username", "TEXT"),
        ("browser_profile_name", "TEXT"),
        ("browser_profile_bio", "TEXT"),
        ("browser_profile_location", "TEXT"),
        ("browser_followers", "TEXT"),
        ("browser_profile_pic_url", "TEXT"),
        ("browser_enriched_at", "TEXT"),
        ("browser_error", "TEXT"),
        ("enrichment_status", "TEXT DEFAULT 'pending'")
    ]

    added_count = 0
    skipped_count = 0

    for col_name, col_type in new_columns:
        if col_name in existing_columns:
            logging.debug(f"Column '{col_name}' already exists, skipping")
            skipped_count += 1
            continue

        sql = f"ALTER TABLE profiles ADD COLUMN {col_name} {col_type}"

        if dry_run:
            logging.info(f"[DRY RUN] Would execute: {sql}")
            added_count += 1
        else:
            try:
                cur.execute(sql)
                logging.info(f"✓ Added column: {col_name} ({col_type})")
                added_count += 1
            except sqlite3.OperationalError as e:
                logging.warning(f"✗ Failed to add {col_name}: {e}")

    if not dry_run:
        conn.commit()

    logging.info(f"Schema upgrade: {added_count} columns added, {skipped_count} skipped")
    return added_count


def backfill_data(conn, dry_run=False):
    """Backfill clean_url and profile_id from existing resolved_url"""
    cur = conn.cursor()

    # Check if columns exist
    columns = get_current_columns(conn)
    if 'clean_url' not in columns or 'profile_id' not in columns:
        logging.warning("Cannot backfill: clean_url or profile_id columns missing")
        return 0

    # Get records that need backfilling
    cur.execute("""
        SELECT id, resolved_url 
        FROM profiles 
        WHERE resolved_url IS NOT NULL 
        AND (clean_url IS NULL OR profile_id IS NULL)
    """)

    records = cur.fetchall()
    logging.info(f"Found {len(records)} records to backfill")

    if dry_run:
        logging.info("[DRY RUN] Would backfill data from resolved_url")
        return len(records)

    updated_count = 0
    for record_id, resolved_url in records:
        # Extract profile ID from resolved_url
        # Format: https://www.facebook.com/{profile_id}
        if resolved_url and 'facebook.com/' in resolved_url:
            profile_id = resolved_url.split('facebook.com/')[-1].strip('/')

            cur.execute("""
                UPDATE profiles 
                SET clean_url = ?, profile_id = ?
                WHERE id = ?
            """, (resolved_url, profile_id, record_id))

            updated_count += 1
            logging.debug(f"Backfilled record {record_id}: profile_id={profile_id}")

    conn.commit()
    logging.info(f"✓ Backfilled {updated_count} records")
    return updated_count


def create_indexes(conn, dry_run=False):
    """Create indexes for new columns"""
    indexes = [
        ("idx_profile_id", "profiles", "profile_id"),
        ("idx_enrichment_status", "profiles", "enrichment_status")
    ]

    created_count = 0
    for idx_name, table, column in indexes:
        sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})"

        if dry_run:
            logging.info(f"[DRY RUN] Would create index: {idx_name}")
            created_count += 1
        else:
            try:
                conn.execute(sql)
                logging.info(f"✓ Created index: {idx_name}")
                created_count += 1
            except sqlite3.OperationalError as e:
                logging.debug(f"Index {idx_name} may already exist: {e}")

    if not dry_run:
        conn.commit()

    return created_count


def verify_migration(conn):
    """Verify migration completed successfully"""
    cur = conn.cursor()

    # Check column count
    cur.execute("PRAGMA table_info(profiles)")
    columns = cur.fetchall()

    logging.info("=" * 60)
    logging.info("MIGRATION VERIFICATION")
    logging.info(f"Total columns: {len(columns)}")

    # Check for required columns
    column_names = [col[1] for col in columns]
    required = ['clean_url', 'profile_id', 'enrichment_status']

    for col in required:
        status = "✓" if col in column_names else "✗"
        logging.info(f"{status} Column '{col}': {'present' if col in column_names else 'MISSING'}")

    # Check record counts
    cur.execute("SELECT COUNT(*) FROM profiles")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM profiles WHERE clean_url IS NOT NULL")
    backfilled = cur.fetchone()[0]

    logging.info(f"Total records: {total}")
    logging.info(f"Backfilled records: {backfilled}")
    logging.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Migrate database schema for browser enrichment')
    parser.add_argument('--database', '-d', default='test_profiles.db',
                       help='Path to database file')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    args = parser.parse_args()

    logging.info(f"Starting migration for: {args.database}")
    if args.dry_run:
        logging.info("DRY RUN MODE - No changes will be made")

    # Connect to database
    try:
        conn = sqlite3.connect(args.database)
    except sqlite3.Error as e:
        logging.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    try:
        # Step 1: Upgrade schema
        added = upgrade_schema(conn, dry_run=args.dry_run)

        # Step 2: Backfill data
        backfilled = backfill_data(conn, dry_run=args.dry_run)

        # Step 3: Create indexes
        indexed = create_indexes(conn, dry_run=args.dry_run)

        # Step 4: Verify
        if not args.dry_run:
            verify_migration(conn)

        logging.info("Migration completed successfully")

    except Exception as e:
        logging.error(f"Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()

