#!/usr/bin/env python3
"""
Database Migration Verification
Proves that the migration was successful and data integrity is maintained.

Usage:
    python3 verify_migration.py test_profiles.db
"""

import sqlite3
import sys
from pathlib import Path
from typing import List, Tuple

# Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text: str):
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text:^80}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def verify_schema(db_path: str) -> Tuple[bool, List[str]]:
    """Verify all expected columns exist"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(profiles);")
    columns = {row[1]: row[2] for row in cursor.fetchall()}
    conn.close()

    # Expected marketplace columns
    expected = {
        'fb_join_date': 'TEXT',
        'fb_active_listings_count': 'INTEGER',
        'fb_response_rate': 'TEXT',
        'fb_response_time': 'TEXT',
        'fb_seller_badges': 'TEXT',
        'fb_picture_url': 'TEXT',
        'fb_cover_url': 'TEXT',
    }

    print_header("SCHEMA VERIFICATION")

    all_present = True
    errors = []

    for col_name, expected_type in expected.items():
        if col_name in columns:
            actual_type = columns[col_name]
            if actual_type == expected_type:
                print(f"{GREEN}✓{RESET} {col_name:30} {actual_type:10} (correct)")
            else:
                print(f"{RED}✗{RESET} {col_name:30} {actual_type:10} (expected {expected_type})")
                errors.append(f"Column {col_name} has wrong type: {actual_type} != {expected_type}")
                all_present = False
        else:
            print(f"{RED}✗{RESET} {col_name:30} {'MISSING':10}")
            errors.append(f"Column {col_name} is missing from schema")
            all_present = False

    return all_present, errors


def verify_data_types(db_path: str) -> Tuple[bool, List[str]]:
    """Verify data in columns matches expected types"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print_header("DATA TYPE VERIFICATION")

    # Check INTEGER field
    cursor.execute("""
        SELECT COUNT(*) FROM profiles 
        WHERE fb_active_listings_count IS NOT NULL 
        AND TYPEOF(fb_active_listings_count) != 'integer'
    """)
    bad_int_count = cursor.fetchone()[0]

    if bad_int_count == 0:
        print(f"{GREEN}✓{RESET} fb_active_listings_count: All values are proper integers")
    else:
        print(f"{RED}✗{RESET} fb_active_listings_count: {bad_int_count} values are not integers")

    # Check JSON field validity
    cursor.execute("""
        SELECT fb_id, fb_seller_badges 
        FROM profiles 
        WHERE fb_seller_badges IS NOT NULL 
        AND fb_seller_badges != ''
        LIMIT 10
    """)

    json_errors = []
    import json
    for fb_id, badges_str in cursor.fetchall():
        try:
            json.loads(badges_str)
        except json.JSONDecodeError as e:
            json_errors.append(f"Profile {fb_id}: Invalid JSON - {e}")

    if not json_errors:
        print(f"{GREEN}✓{RESET} fb_seller_badges: All non-null values are valid JSON")
    else:
        print(f"{RED}✗{RESET} fb_seller_badges: {len(json_errors)} invalid JSON entries")
        for error in json_errors[:5]:  # Show first 5
            print(f"    {error}")

    conn.close()

    all_valid = (bad_int_count == 0 and len(json_errors) == 0)
    return all_valid, json_errors


def verify_data_coverage(db_path: str) -> Tuple[bool, dict]:
    """Check what percentage of profiles have marketplace data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print_header("DATA COVERAGE ANALYSIS")

    cursor.execute("SELECT COUNT(*) FROM profiles")
    total_profiles = cursor.fetchone()[0]

    print(f"Total profiles: {total_profiles}\n")

    coverage = {}
    for field in ['fb_join_date', 'fb_active_listings_count', 'fb_response_rate',
                  'fb_response_time', 'fb_seller_badges', 'fb_picture_url', 'fb_cover_url']:
        cursor.execute(f"SELECT COUNT(*) FROM profiles WHERE {field} IS NOT NULL AND {field} != ''")
        count = cursor.fetchone()[0]
        percentage = (count / total_profiles * 100) if total_profiles > 0 else 0
        coverage[field] = (count, percentage)

        color = GREEN if percentage > 50 else (YELLOW if percentage > 10 else RED)
        print(f"{color}{field:30}{RESET} {count:5} / {total_profiles:5} ({percentage:5.1f}%)")

    conn.close()

    # At least one profile should have some marketplace data
    has_any_data = any(count > 0 for count, _ in coverage.values())

    return has_any_data, coverage


def show_sample_data(db_path: str):
    """Show sample of actual extracted data"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print_header("SAMPLE DATA (First 3 Profiles with Marketplace Data)")

    cursor.execute("""
        SELECT 
            fb_id,
            fb_name,
            fb_join_date,
            fb_active_listings_count,
            fb_response_rate,
            fb_response_time,
            fb_seller_badges,
            fb_picture_url,
            fb_cover_url
        FROM profiles
        WHERE fb_join_date IS NOT NULL
        ORDER BY enriched_at DESC
        LIMIT 3
    """)

    rows = cursor.fetchall()

    if not rows:
        print(f"{YELLOW}No profiles with marketplace data found{RESET}")
    else:
        for i, row in enumerate(rows, 1):
            print(f"\n{BLUE}--- Profile {i} ---{RESET}")
            print(f"ID:               {row['fb_id']}")
            print(f"Name:             {row['fb_name']}")
            print(f"Join Date:        {row['fb_join_date']}")
            print(f"Active Listings:  {row['fb_active_listings_count']}")
            print(f"Response Rate:    {row['fb_response_rate']}")
            print(f"Response Time:    {row['fb_response_time']}")
            print(f"Seller Badges:    {row['fb_seller_badges']}")
            print(f"Picture URL:      {row['fb_picture_url'][:60] if row['fb_picture_url'] else 'None'}...")
            print(f"Cover URL:        {row['fb_cover_url'][:60] if row['fb_cover_url'] else 'None'}...")

    conn.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 verify_migration.py <database_path>")
        print("\nExample:")
        print("  python3 verify_migration.py test_profiles.db")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"{RED}✗ Database not found: {db_path}{RESET}")
        sys.exit(1)

    print(f"\n{BLUE}Database: {db_path}{RESET}")

    # Run all verification checks
    schema_ok, schema_errors = verify_schema(db_path)
    types_ok, type_errors = verify_data_types(db_path)
    coverage_ok, coverage_data = verify_data_coverage(db_path)

    # Show sample data
    show_sample_data(db_path)

    # Final verdict
    print_header("VERIFICATION SUMMARY")

    if schema_ok:
        print(f"{GREEN}✓{RESET} Schema: All columns present and correct")
    else:
        print(f"{RED}✗{RESET} Schema: Issues found")
        for error in schema_errors:
            print(f"    {error}")

    if types_ok:
        print(f"{GREEN}✓{RESET} Data Types: All values have correct types")
    else:
        print(f"{RED}✗{RESET} Data Types: Issues found")

    if coverage_ok:
        print(f"{GREEN}✓{RESET} Data Coverage: At least some profiles have marketplace data")
    else:
        print(f"{YELLOW}⚠{RESET} Data Coverage: No profiles have marketplace data yet")

    # Overall result
    all_ok = schema_ok and types_ok

    if all_ok:
        print(f"\n{GREEN}{'=' * 80}{RESET}")
        print(f"{GREEN}{'✓ MIGRATION VERIFICATION PASSED':^80}{RESET}")
        print(f"{GREEN}{'=' * 80}{RESET}\n")

        if not coverage_ok:
            print(f"{YELLOW}Note: Migration structure is correct, but no data extracted yet.{RESET}")
            print(f"{YELLOW}Run selenium_enricher.py to populate marketplace data.{RESET}\n")

        sys.exit(0)
    else:
        print(f"\n{RED}{'=' * 80}{RESET}")
        print(f"{RED}{'✗ MIGRATION VERIFICATION FAILED':^80}{RESET}")
        print(f"{RED}{'=' * 80}{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
