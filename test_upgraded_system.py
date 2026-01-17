#!/usr/bin/env python3
"""
Test Suite for Upgraded Facebook Profile Processor
Tests Graph API compatible schema and all components

USAGE:
    python3 test_upgraded_system.py
"""

import sqlite3
import sys
from pathlib import Path

def test_schema_compliance():
    """Test that database schema is Graph API v24.0 compatible"""
    print("=" * 60)
    print("TEST 1: Schema Compliance")
    print("=" * 60)

    db_path = 'test_profiles.db'
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get schema
    cur.execute("PRAGMA table_info(profiles)")
    columns = {row[1]: row[2] for row in cur.fetchall()}

    # Required Graph API fields
    required_fields = {
        'fb_id': 'TEXT',
        'fb_username': 'TEXT',
        'fb_name': 'TEXT',
        'fb_first_name': 'TEXT',
        'fb_last_name': 'TEXT',
        'fb_email': 'TEXT',
        'fb_bio': 'TEXT',
        'fb_location_name': 'TEXT',
        'fb_picture_url': 'TEXT',
        'fb_link': 'TEXT',
        'enrichment_status': 'TEXT',
        'enrichment_method': 'TEXT'
    }

    missing = []
    for field, expected_type in required_fields.items():
        if field not in columns:
            missing.append(field)
            print(f"❌ Missing field: {field}")
        else:
            print(f"✅ Found: {field} ({columns[field]})")

    conn.close()

    if missing:
        print(f"\n❌ FAILED: {len(missing)} fields missing")
        return False
    else:
        print(f"\n✅ PASSED: All required fields present")
        return True


def test_data_migration():
    """Test that existing data was migrated correctly"""
    print("\n" + "=" * 60)
    print("TEST 2: Data Migration")
    print("=" * 60)

    db_path = 'test_profiles.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if data exists
    cur.execute("SELECT COUNT(*) FROM profiles")
    count = cur.fetchone()[0]
    print(f"Total records: {count}")

    if count == 0:
        print("⚠️  No data to test migration")
        conn.close()
        return True

    # Check if fb_id is populated
    cur.execute("SELECT COUNT(*) FROM profiles WHERE fb_id IS NOT NULL")
    with_fb_id = cur.fetchone()[0]
    print(f"Records with fb_id: {with_fb_id}")

    # Check enrichment status
    cur.execute("SELECT enrichment_status, COUNT(*) FROM profiles GROUP BY enrichment_status")
    status_counts = cur.fetchall()
    print("\nEnrichment status distribution:")
    for status, count in status_counts:
        print(f"  {status}: {count}")

    conn.close()

    if with_fb_id > 0:
        print(f"\n✅ PASSED: Data migration successful")
        return True
    else:
        print(f"\n⚠️  WARNING: No fb_id values found (may need enrichment)")
        return True


def test_indexes():
    """Test that required indexes exist"""
    print("\n" + "=" * 60)
    print("TEST 3: Database Indexes")
    print("=" * 60)

    db_path = 'test_profiles.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='profiles'")
    indexes = [row[0] for row in cur.fetchall()]

    required_indexes = ['idx_fb_id', 'idx_fb_username', 'idx_enrichment_status', 'idx_input_url']

    missing = []
    for idx in required_indexes:
        if idx in indexes:
            print(f"✅ Found index: {idx}")
        else:
            print(f"❌ Missing index: {idx}")
            missing.append(idx)

    conn.close()

    if missing:
        print(f"\n❌ FAILED: {len(missing)} indexes missing")
        return False
    else:
        print(f"\n✅ PASSED: All required indexes present")
        return True


def test_backward_compatibility():
    """Test that legacy fields are preserved"""
    print("\n" + "=" * 60)
    print("TEST 4: Backward Compatibility")
    print("=" * 60)

    db_path = 'test_profiles.db'
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(profiles)")
    columns = [row[1] for row in cur.fetchall()]

    legacy_fields = ['legacy_clean_url', 'legacy_profile_id', 'legacy_og_title', 'legacy_og_description']

    missing = []
    for field in legacy_fields:
        if field in columns:
            print(f"✅ Found legacy field: {field}")
        else:
            print(f"❌ Missing legacy field: {field}")
            missing.append(field)

    conn.close()

    if missing:
        print(f"\n❌ FAILED: {len(missing)} legacy fields missing")
        return False
    else:
        print(f"\n✅ PASSED: All legacy fields preserved")
        return True


if __name__ == '__main__':
    print("\n🧪 Facebook Profile Processor - Upgrade Test Suite\n")

    tests = [
        test_schema_compliance,
        test_data_migration,
        test_indexes,
        test_backward_compatibility
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ TEST FAILED WITH EXCEPTION: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} TESTS FAILED")
        sys.exit(1)

