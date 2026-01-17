#!/usr/bin/env python3
"""Add local_image_path column to existing databases"""

import sqlite3
from pathlib import Path

def add_column_if_not_exists(db_path):
    """Add local_image_path column to database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if column exists
    cur.execute("PRAGMA table_info(profiles)")
    columns = [row[1] for row in cur.fetchall()]

    if 'local_image_path' not in columns:
        print(f"Adding local_image_path column to {db_path}...")
        cur.execute("ALTER TABLE profiles ADD COLUMN local_image_path TEXT")
        conn.commit()
        print(f"✅ Column added to {db_path}")
    else:
        print(f"✓ Column already exists in {db_path}")

    conn.close()

if __name__ == '__main__':
    # Update all .db files
    for db_file in Path('.').glob('*.db'):
        try:
            add_column_if_not_exists(db_file)
        except Exception as e:
            print(f"Error updating {db_file}: {e}")

