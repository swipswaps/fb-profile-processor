#!/usr/bin/env python3
"""
Database Migration: Add Facebook Marketplace Columns
Adds 7 new columns to the profiles table for marketplace-specific data.
"""

import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str) -> bool:
    """
    Add marketplace columns to profiles table.
    
    Args:
        db_path: Path to SQLite database file
        
    Returns:
        True if migration successful, False otherwise
    """
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Define new columns
    new_columns = [
        ("fb_join_date", "TEXT"),
        ("fb_active_listings_count", "INTEGER"),
        ("fb_response_rate", "TEXT"),
        ("fb_response_time", "TEXT"),
        ("fb_seller_badges", "TEXT"),  # JSON array
        ("fb_picture_url", "TEXT"),
        ("fb_cover_url", "TEXT"),
    ]
    
    print("=== DATABASE MIGRATION: ADD MARKETPLACE COLUMNS ===")
    print(f"Database: {db_path}\n")
    
    # Get existing columns
    cursor.execute("PRAGMA table_info(profiles);")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns: {len(existing_columns)}")
    
    # Add each column if it doesn't exist
    added_count = 0
    skipped_count = 0
    
    for col_name, col_type in new_columns:
        if col_name in existing_columns:
            print(f"  ⏭️  {col_name:30} {col_type:10} (already exists)")
            skipped_count += 1
        else:
            try:
                cursor.execute(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_type};")
                print(f"  ✅ {col_name:30} {col_type:10} (added)")
                added_count += 1
            except sqlite3.Error as e:
                print(f"  ❌ {col_name:30} {col_type:10} (error: {e})")
                conn.close()
                return False
    
    conn.commit()
    
    # Verify final schema
    cursor.execute("PRAGMA table_info(profiles);")
    final_columns = cursor.fetchall()
    
    print(f"\n=== MIGRATION SUMMARY ===")
    print(f"Columns added: {added_count}")
    print(f"Columns skipped: {skipped_count}")
    print(f"Total columns now: {len(final_columns)}")
    
    # Show new columns
    print(f"\n=== NEW COLUMNS VERIFIED ===")
    for row in final_columns:
        col_id, col_name, col_type, not_null, default, pk = row
        if col_name in [col[0] for col in new_columns]:
            print(f"  {col_name:30} {col_type:10}")
    
    conn.close()
    print(f"\n✅ Migration complete: {db_path}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 add_marketplace_columns.py <database_path>")
        print("Example: python3 add_marketplace_columns.py test_profiles.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    success = migrate_database(db_path)
    sys.exit(0 if success else 1)
