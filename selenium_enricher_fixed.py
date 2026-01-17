#!/usr/bin/env python3
"""
Fixed Selenium Enricher - Visits CORRECT URLs with Auto-Validation

Key fixes:
1. Visits marketplace profile URLs (not regular profile URLs)
2. Auto-validates extraction results
3. Reports success rate
4. Fails loudly when extraction rate < 70%
5. Shows sample data to prove it worked
"""

import sqlite3
import time
import sys
from datetime import datetime
from typing import Dict, Optional
from selenium_enricher_validated import (
    extract_marketplace_info,
    validate_extraction_data,
    ExtractionReport
)

# Import the fixed create_firefox_driver from existing enricher
# (This assumes the Firefox profile handling code is already in selenium_enricher.py)

def get_marketplace_url(fb_id: str) -> str:
    """
    Get the CORRECT marketplace profile URL.
    
    Args:
        fb_id: Facebook user ID
        
    Returns:
        Full marketplace profile URL
    """
    # THIS IS THE KEY FIX - use marketplace URL, not profile URL
    return f"https://www.facebook.com/marketplace/profile/{fb_id}/"


def enrich_profile_with_validation(driver, profile: Dict, db_path: str) -> bool:
    """
    Enrich a single profile with VALIDATION.
    
    Returns:
        True if enrichment succeeded (>70% fields extracted)
        False if enrichment failed
    """
    fb_id = profile['fb_id']
    profile_id = profile['id']

    print(f"\n{'=' * 80}")
    print(f"Enriching Profile: {profile.get('fb_name', 'Unknown')} (ID: {fb_id})")
    print(f"{'=' * 80}")

    # STEP 1: Visit the CORRECT URL
    marketplace_url = get_marketplace_url(fb_id)
    print(f"URL: {marketplace_url}")

    try:
        driver.get(marketplace_url)
        time.sleep(5)  # Wait for page to load

    except Exception as e:
        print(f"❌ Failed to load page: {e}")
        return False

    # STEP 2: Extract marketplace data
    print(f"\nExtracting marketplace data...")
    extraction_result = extract_marketplace_info(driver)

    # Remove the internal report object
    report = extraction_result.pop('_extraction_report', None)

    # STEP 3: Validate extraction
    print(f"\nValidating extraction...")
    is_valid = validate_extraction_data(extraction_result)

    # Calculate success rate
    total_fields = 7
    extracted_fields = sum(1 for v in extraction_result.values() if v is not None and v != '')
    success_rate = (extracted_fields / total_fields) * 100

    print(f"\nSuccess Rate: {extracted_fields}/{total_fields} fields ({success_rate:.1f}%)")

    # STEP 4: Decide if this is acceptable
    if success_rate < 70:
        print(f"❌ ENRICHMENT FAILED - Success rate too low ({success_rate:.1f}% < 70%)")
        print(f"   This likely means:")
        print(f"   • Page structure has changed")
        print(f"   • XPath selectors are broken")
        print(f"   • Page didn't fully load")
        return False

    if not is_valid:
        print(f"❌ ENRICHMENT FAILED - Data validation failed")
        return False

    # STEP 5: Save to database
    print(f"\nSaving to database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE profiles SET
            fb_join_date = ?,
            fb_active_listings_count = ?,
            fb_response_rate = ?,
            fb_response_time = ?,
            fb_seller_badges = ?,
            fb_picture_url = ?,
            fb_cover_url = ?,
            enriched_at = ?,
            enrichment_status = 'enriched'
        WHERE id = ?
    """, (
        extraction_result.get('fb_join_date'),
        extraction_result.get('fb_active_listings_count'),
        extraction_result.get('fb_response_rate'),
        extraction_result.get('fb_response_time'),
        extraction_result.get('fb_seller_badges'),
        extraction_result.get('fb_picture_url'),
        extraction_result.get('fb_cover_url'),
        datetime.now().isoformat(),
        profile_id
    ))

    conn.commit()
    conn.close()

    print(f"✅ ENRICHMENT SUCCESSFUL - Data saved to database")

    # STEP 6: Show sample of extracted data
    print(f"\nExtracted Data Sample:")
    for field, value in extraction_result.items():
        if value:
            display_val = str(value)[:60]
            if len(str(value)) > 60:
                display_val += "..."
            print(f"  {field:30} = {display_val}")

    return True


def verify_enrichment_results(db_path: str, profile_ids: list) -> Dict:
    """
    Verify that enrichment actually worked by checking database.
    
    Returns:
        Dictionary with verification results
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    results = {
        'total': len(profile_ids),
        'successful': 0,
        'failed': 0,
        'field_coverage': {}
    }

    # Check each profile
    for profile_id in profile_ids:
        cursor.execute("""
            SELECT 
                fb_join_date, fb_active_listings_count, fb_response_rate,
                fb_response_time, fb_seller_badges, fb_picture_url, fb_cover_url
            FROM profiles WHERE id = ?
        """, (profile_id,))

        row = cursor.fetchone()
        if row:
            non_null_fields = sum(1 for v in row if v is not None and v != '')
            if non_null_fields >= 5:  # At least 5/7 fields
                results['successful'] += 1
            else:
                results['failed'] += 1

    # Check overall field coverage
    for field in ['fb_join_date', 'fb_active_listings_count', 'fb_response_rate',
                  'fb_response_time', 'fb_seller_badges', 'fb_picture_url', 'fb_cover_url']:
        cursor.execute(f"SELECT COUNT(*) FROM profiles WHERE {field} IS NOT NULL AND {field} != ''")
        count = cursor.fetchone()[0]
        results['field_coverage'][field] = count

    conn.close()
    return results


def print_enrichment_summary(results: Dict):
    """Print summary of enrichment results"""
    print(f"\n{'=' * 80}")
    print(f"ENRICHMENT SUMMARY")
    print(f"{'=' * 80}")
    print(f"Total Profiles: {results['total']}")
    print(f"✅ Successful:  {results['successful']}")
    print(f"❌ Failed:      {results['failed']}")

    success_rate = (results['successful'] / results['total'] * 100) if results['total'] > 0 else 0
    print(f"\nOverall Success Rate: {success_rate:.1f}%")

    print(f"\nField Coverage:")
    for field, count in results['field_coverage'].items():
        percentage = (count / results['total'] * 100) if results['total'] > 0 else 0
        print(f"  {field:30} {count:3}/{results['total']:3} ({percentage:5.1f}%)")

    print(f"{'=' * 80}\n")


def show_sample_data(db_path: str, limit: int = 3):
    """Show sample of extracted data to prove it worked"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            fb_id, fb_name, fb_join_date, fb_active_listings_count,
            fb_response_rate, fb_seller_badges, fb_picture_url
        FROM profiles
        WHERE fb_join_date IS NOT NULL
        ORDER BY enriched_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()

    print(f"\n{'=' * 80}")
    print(f"SAMPLE EXTRACTED DATA (Last {limit} Enriched Profiles)")
    print(f"{'=' * 80}\n")

    if not rows:
        print("❌ No profiles with marketplace data found")
        print("   This means enrichment failed for all profiles")
    else:
        for i, row in enumerate(rows, 1):
            print(f"Profile {i}:")
            print(f"  ID:             {row['fb_id']}")
            print(f"  Name:           {row['fb_name']}")
            print(f"  Join Date:      {row['fb_join_date']}")
            print(f"  Active Listings: {row['fb_active_listings_count']}")
            print(f"  Response Rate:  {row['fb_response_rate']}")
            print(f"  Seller Badges:  {row['fb_seller_badges']}")
            print(f"  Picture URL:    {row['fb_picture_url'][:60] if row['fb_picture_url'] else 'None'}...")
            print()

    conn.close()


def main():
    """Main enrichment workflow with validation"""
    import argparse

    parser = argparse.ArgumentParser(description='Enrich Facebook profiles with marketplace data')
    parser.add_argument('--force', action='store_true', help='Re-enrich already enriched profiles')
    parser.add_argument('--verify', action='store_true', help='Run verification after enrichment')
    parser.add_argument('--dry-run', action='store_true', help='Extract data but don\'t save to DB')
    parser.add_argument('--profile', type=str, help='Enrich specific profile by fb_id')
    args = parser.parse_args()

    db_path = 'test_profiles.db'

    # Get profiles to enrich
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if args.profile:
        cursor.execute("SELECT * FROM profiles WHERE fb_id = ?", (args.profile,))
    elif args.force:
        cursor.execute("SELECT * FROM profiles")
    else:
        cursor.execute("SELECT * FROM profiles WHERE enrichment_status IN ('pending', 'partial')")

    profiles = [dict(row) for row in cursor.fetchall()]
    conn.close()

    if not profiles:
        print("No profiles to enrich")
        return 0

    print(f"Found {len(profiles)} profiles to enrich")

    # Import Firefox driver creation function
    # (Assumes it's in the existing selenium_enricher.py)
    try:
        from selenium_enricher import create_firefox_driver
    except ImportError:
        print("❌ Error: Could not import create_firefox_driver")
        print("   Make sure selenium_enricher.py has the Firefox profile handling code")
        return 1

    # Create driver
    driver, temp_profile_dir = create_firefox_driver()
    if not driver:
        print("❌ Failed to create Firefox driver")
        return 1

    try:
        enriched_ids = []
        success_count = 0
        fail_count = 0

        for profile in profiles:
            if args.dry_run:
                print(f"\n[DRY RUN] Would enrich: {profile['fb_name']} ({profile['fb_id']})")
                continue

            success = enrich_profile_with_validation(driver, profile, db_path)

            if success:
                enriched_ids.append(profile['id'])
                success_count += 1
            else:
                fail_count += 1

            time.sleep(2)  # Rate limiting

        # Verify results
        if enriched_ids and args.verify:
            print(f"\n{'=' * 80}")
            print(f"RUNNING VERIFICATION")
            print(f"{'=' * 80}\n")

            results = verify_enrichment_results(db_path, enriched_ids)
            print_enrichment_summary(results)

        # Show sample data
        show_sample_data(db_path)

        # Final verdict
        total = success_count + fail_count
        if total > 0:
            overall_rate = (success_count / total) * 100
            print(f"{'=' * 80}")
            print(f"FINAL RESULTS")
            print(f"{'=' * 80}")
            print(f"Processed: {total} profiles")
            print(f"✅ Success: {success_count}")
            print(f"❌ Failed:  {fail_count}")
            print(f"Success Rate: {overall_rate:.1f}%")

            if overall_rate >= 80:
                print(f"\n✅ ENRICHMENT COMPLETED SUCCESSFULLY")
                return 0
            else:
                print(f"\n❌ ENRICHMENT PARTIALLY FAILED")
                print(f"   Success rate ({overall_rate:.1f}%) is below 80%")
                return 1

    finally:
        driver.quit()
        if temp_profile_dir:
            import shutil
            try:
                shutil.rmtree(temp_profile_dir)
            except:
                pass


if __name__ == "__main__":
    sys.exit(main())
