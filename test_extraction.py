#!/usr/bin/env python3
"""
Test Extraction Suite: VERIFY that Facebook marketplace data extraction works
This script RUNS the enricher and PROVES the data was extracted correctly.

Usage:
    python3 test_extraction.py test_profiles.db 100024126863464

Rules enforced:
- Never guess. Always check answers.
- Show BEFORE/AFTER states
- Verify data is non-null
- Report failures explicitly
"""

import sqlite3
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_header(text: str):
    """Print colored section header"""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text:^80}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{GREEN}✓ {text}{RESET}")


def print_failure(text: str):
    """Print failure message"""
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{YELLOW}⚠ {text}{RESET}")


def get_profile_data(db_path: str, fb_id: str) -> Optional[Dict]:
    """Get profile data from database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            fb_id,
            fb_name,
            fb_location_name,
            fb_join_date,
            fb_active_listings_count,
            fb_response_rate,
            fb_response_time,
            fb_seller_badges,
            fb_picture_url,
            fb_cover_url,
            enriched_at
        FROM profiles
        WHERE fb_id = ?
    """, (fb_id,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def check_field(field_name: str, value, required: bool = True) -> bool:
    """Check if a field has valid data"""
    if value is None or value == '':
        if required:
            print_failure(f"{field_name:30} = NULL (REQUIRED)")
            return False
        else:
            print_warning(f"{field_name:30} = NULL (optional)")
            return True
    else:
        # Truncate long values for display
        display_value = str(value)[:60]
        if len(str(value)) > 60:
            display_value += "..."
        print_success(f"{field_name:30} = {display_value}")
        return True


def verify_json_field(field_name: str, value: str) -> bool:
    """Verify a JSON field is valid JSON"""
    if not value or value == '':
        print_warning(f"{field_name:30} = NULL (empty JSON)")
        return True  # Empty JSON is acceptable

    try:
        parsed = json.loads(value)
        print_success(f"{field_name:30} = {json.dumps(parsed)[:60]}")
        return True
    except json.JSONDecodeError as e:
        print_failure(f"{field_name:30} = INVALID JSON: {e}")
        return False


def run_extraction_test(db_path: str, fb_id: str) -> int:
    """
    Run full extraction test
    Returns: 0 for success, 1 for failure
    """
    if not Path(db_path).exists():
        print_failure(f"Database not found: {db_path}")
        return 1

    print_header("FACEBOOK MARKETPLACE EXTRACTION TEST")
    print(f"Database: {db_path}")
    print(f"Profile ID: {fb_id}")

    # STEP 1: Check BEFORE state
    print_header("STEP 1: BEFORE STATE")
    before_data = get_profile_data(db_path, fb_id)

    if not before_data:
        print_failure(f"Profile {fb_id} not found in database")
        return 1

    print(f"Profile Name: {before_data.get('fb_name', 'N/A')}")
    print(f"Location: {before_data.get('fb_location_name', 'N/A')}")
    print(f"Last Enriched: {before_data.get('enriched_at', 'Never')}")

    # Show BEFORE marketplace data
    print("\nMarketplace Data (BEFORE):")
    for field in ['fb_join_date', 'fb_active_listings_count', 'fb_response_rate',
                  'fb_response_time', 'fb_seller_badges', 'fb_picture_url', 'fb_cover_url']:
        value = before_data.get(field)
        if value:
            print(f"  {field:30} = {str(value)[:60]}")
        else:
            print(f"  {field:30} = NULL")

    # STEP 2: Run enricher (user must do this manually for now)
    print_header("STEP 2: RUN ENRICHER")
    print_warning("MANUAL STEP REQUIRED:")
    print("\nRun the following command in another terminal:")
    print(f"\n    python3 selenium_enricher.py\n")
    print("Then press ENTER here to continue verification...")
    input()

    # STEP 3: Check AFTER state
    print_header("STEP 3: AFTER STATE (VERIFICATION)")
    after_data = get_profile_data(db_path, fb_id)

    if not after_data:
        print_failure(f"Profile {fb_id} disappeared from database!")
        return 1

    # Verify all fields
    print("\nMarketplace Data (AFTER):")
    passed = 0
    failed = 0

    # Required fields
    if check_field("fb_join_date", after_data.get('fb_join_date'), required=True):
        passed += 1
    else:
        failed += 1

    if check_field("fb_picture_url", after_data.get('fb_picture_url'), required=True):
        passed += 1
    else:
        failed += 1

    # Optional fields (but should be present for active sellers)
    if check_field("fb_active_listings_count", after_data.get('fb_active_listings_count'), required=False):
        passed += 1

    if check_field("fb_response_rate", after_data.get('fb_response_rate'), required=False):
        passed += 1

    if check_field("fb_response_time", after_data.get('fb_response_time'), required=False):
        passed += 1

    if check_field("fb_cover_url", after_data.get('fb_cover_url'), required=False):
        passed += 1

    # JSON field
    if verify_json_field("fb_seller_badges", after_data.get('fb_seller_badges', '')):
        passed += 1
    else:
        failed += 1

    # STEP 4: Compare BEFORE vs AFTER
    print_header("STEP 4: CHANGES DETECTED")

    changes_found = False
    for field in ['fb_join_date', 'fb_active_listings_count', 'fb_response_rate',
                  'fb_response_time', 'fb_seller_badges', 'fb_picture_url', 'fb_cover_url']:
        before_val = before_data.get(field)
        after_val = after_data.get(field)

        if before_val != after_val:
            changes_found = True
            print(f"\n{field}:")
            print(f"  BEFORE: {before_val or 'NULL'}")
            print(f"  AFTER:  {after_val or 'NULL'}")

    if not changes_found:
        print_warning("No changes detected. Enrichment may not have run.")

    # STEP 5: Final verdict
    print_header("TEST RESULTS")

    print(f"\nFields Verified: {passed + failed}")
    print_success(f"Passed: {passed}")
    if failed > 0:
        print_failure(f"Failed: {failed}")

    # Check if enrichment timestamp was updated
    if after_data.get('enriched_at') != before_data.get('enriched_at'):
        print_success("Enrichment timestamp updated")
    else:
        print_warning("Enrichment timestamp NOT updated")

    if failed == 0 and changes_found:
        print(f"\n{GREEN}{'=' * 80}{RESET}")
        print(f"{GREEN}{'✓ EXTRACTION TEST PASSED':^80}{RESET}")
        print(f"{GREEN}{'=' * 80}{RESET}\n")
        return 0
    else:
        print(f"\n{RED}{'=' * 80}{RESET}")
        print(f"{RED}{'✗ EXTRACTION TEST FAILED':^80}{RESET}")
        print(f"{RED}{'=' * 80}{RESET}\n")
        return 1


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 test_extraction.py <database_path> <fb_id>")
        print("\nExample:")
        print("  python3 test_extraction.py test_profiles.db 100024126863464")
        sys.exit(1)

    db_path = sys.argv[1]
    fb_id = sys.argv[2]

    result = run_extraction_test(db_path, fb_id)
    sys.exit(result)


if __name__ == "__main__":
    main()
