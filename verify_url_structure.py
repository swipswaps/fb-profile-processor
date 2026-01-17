#!/usr/bin/env python3
"""
URL Structure Verification Tool

Purpose: Document which Facebook URLs contain which data elements.
This prevents guessing and ensures we visit the correct pages.

Usage:
    python3 verify_url_structure.py 100024126863464

Rules enforced:
- Never guess which URL has data
- Always verify URL structure before writing extraction code
- Document findings for future reference
"""

import sys
import time
from typing import Dict, List
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException


def check_element_exists(driver, xpath: str, description: str) -> bool:
    """Check if an element exists on the page"""
    try:
        driver.find_element(By.XPATH, xpath)
        return True
    except NoSuchElementException:
        return False


def analyze_profile_page(driver, fb_id: str) -> Dict[str, bool]:
    """
    Analyze regular profile page to see what data is available.
    
    Args:
        driver: Selenium WebDriver
        fb_id: Facebook user ID
        
    Returns:
        Dictionary of {data_field: is_present}
    """
    url = f"https://www.facebook.com/{fb_id}"
    print(f"\n{'=' * 80}")
    print(f"ANALYZING: {url}")
    print(f"{'=' * 80}\n")

    driver.get(url)
    time.sleep(5)

    # Check for various data elements
    elements = {
        'profile_name': "//h1",
        'profile_picture': "//img[contains(@class, 'profilePic') or @data-imgperflogname='profileCoverPhoto']",
        'cover_photo': "//img[contains(@class, 'cover')]",
        'join_date': "//span[contains(text(), 'Joined Facebook')]",
        'active_listings': "//span[contains(text(), 'active listing')]",
        'response_rate': "//span[contains(text(), 'responsive')]",
        'response_time': "//span[contains(text(), 'responds within')]",
        'seller_badges': "//span[contains(text(), 'Recommended seller')]",
        'about_section': "//div[contains(text(), 'About')]",
        'intro_card': "//div[@data-pagelet='ProfileIntroCard']",
    }

    results = {}
    for field, xpath in elements.items():
        exists = check_element_exists(driver, xpath, field)
        results[field] = exists
        status = "✓ Found" if exists else "✗ Not found"
        print(f"  {field:20} {status}")

    return results


def analyze_marketplace_page(driver, fb_id: str) -> Dict[str, bool]:
    """
    Analyze marketplace profile page to see what data is available.
    
    Args:
        driver: Selenium WebDriver
        fb_id: Facebook user ID
        
    Returns:
        Dictionary of {data_field: is_present}
    """
    url = f"https://www.facebook.com/marketplace/profile/{fb_id}/"
    print(f"\n{'=' * 80}")
    print(f"ANALYZING: {url}")
    print(f"{'=' * 80}\n")

    driver.get(url)
    time.sleep(5)

    # Check for various data elements
    elements = {
        'profile_name': "//h1",
        'profile_picture': "//img[contains(@class, 'profilePic') or @data-imgperflogname='profileCoverPhoto']",
        'cover_photo': "//img[contains(@class, 'cover')]",
        'join_date': "//span[contains(text(), 'Joined Facebook')]",
        'active_listings': "//span[contains(text(), 'active listing')]",
        'response_rate': "//span[contains(text(), 'responsive')]",
        'response_time': "//span[contains(text(), 'responds within')]",
        'seller_badges': "//span[contains(text(), 'Recommended seller')]",
        'marketplace_info': "//div[contains(text(), 'Marketplace')]",
        'listings_section': "//div[@aria-label='Listings']",
    }

    results = {}
    for field, xpath in elements.items():
        exists = check_element_exists(driver, xpath, field)
        results[field] = exists
        status = "✓ Found" if exists else "✗ Not found"
        print(f"  {field:20} {status}")

    return results


def compare_results(profile_results: Dict, marketplace_results: Dict):
    """Compare what data is available on each page"""
    print(f"\n{'=' * 80}")
    print(f"COMPARISON: Profile Page vs Marketplace Page")
    print(f"{'=' * 80}\n")

    all_fields = sorted(set(profile_results.keys()) | set(marketplace_results.keys()))

    print(f"{'Field':<25} {'Profile Page':<15} {'Marketplace Page':<15}")
    print(f"{'-' * 55}")

    for field in all_fields:
        profile_status = "✓" if profile_results.get(field) else "✗"
        marketplace_status = "✓" if marketplace_results.get(field) else "✗"
        print(f"{field:<25} {profile_status:<15} {marketplace_status:<15}")


def generate_recommendations(profile_results: Dict, marketplace_results: Dict):
    """Generate recommendations based on findings"""
    print(f"\n{'=' * 80}")
    print(f"RECOMMENDATIONS")
    print(f"{'=' * 80}\n")

    # Fields we need for marketplace extraction
    required_fields = [
        'join_date',
        'active_listings',
        'response_rate',
        'response_time',
        'seller_badges',
        'profile_picture',
    ]

    profile_only = []
    marketplace_only = []
    both = []
    neither = []

    for field in required_fields:
        on_profile = profile_results.get(field, False)
        on_marketplace = marketplace_results.get(field, False)

        if on_profile and on_marketplace:
            both.append(field)
        elif on_profile and not on_marketplace:
            profile_only.append(field)
        elif on_marketplace and not on_profile:
            marketplace_only.append(field)
        else:
            neither.append(field)

    if marketplace_only:
        print(f"✓ MARKETPLACE PAGE REQUIRED for:")
        for field in marketplace_only:
            print(f"    • {field}")
        print()

    if profile_only:
        print(f"⚠ PROFILE PAGE REQUIRED for:")
        for field in profile_only:
            print(f"    • {field}")
        print()

    if both:
        print(f"ℹ AVAILABLE ON BOTH PAGES:")
        for field in both:
            print(f"    • {field}")
        print()

    if neither:
        print(f"✗ NOT FOUND ON EITHER PAGE:")
        for field in neither:
            print(f"    • {field}")
        print(f"  These fields may require:")
        print(f"    • Different XPath selectors")
        print(f"    • Scrolling to load content")
        print(f"    • Clicking tabs/sections")
        print()

    # Final recommendation
    print(f"{'=' * 80}")
    print(f"FINAL RECOMMENDATION")
    print(f"{'=' * 80}\n")

    if len(marketplace_only) > len(profile_only):
        print(f"✓ PRIMARY URL: https://www.facebook.com/marketplace/profile/{{fb_id}}/")
        print(f"  Reason: Most marketplace-specific fields found here")
        if profile_only:
            print(f"\n  Also visit profile page for: {', '.join(profile_only)}")
    else:
        print(f"⚠ Consider using BOTH URLs:")
        print(f"  • Profile page for: {', '.join(profile_only) if profile_only else 'basic info'}")
        print(f"  • Marketplace page for: {', '.join(marketplace_only) if marketplace_only else 'marketplace info'}")


def main():
    """Main verification workflow"""
    if len(sys.argv) < 2:
        print("Usage: python3 verify_url_structure.py <fb_id>")
        print("\nExample:")
        print("  python3 verify_url_structure.py 100024126863464")
        sys.exit(1)

    fb_id = sys.argv[1]

    # Import Firefox driver creation
    try:
        from selenium_enricher import create_firefox_driver
    except ImportError:
        print("❌ Error: Could not import create_firefox_driver")
        print("   Make sure selenium_enricher.py exists and has the Firefox setup code")
        sys.exit(1)

    print(f"\n{'=' * 80}")
    print(f"URL STRUCTURE VERIFICATION")
    print(f"{'=' * 80}")
    print(f"Profile ID: {fb_id}")
    print(f"Purpose: Verify which URL has which data elements")
    print(f"{'=' * 80}\n")

    # Create driver
    driver, temp_profile_dir = create_firefox_driver()
    if not driver:
        print("❌ Failed to create Firefox driver")
        sys.exit(1)

    try:
        # Analyze both pages
        profile_results = analyze_profile_page(driver, fb_id)
        marketplace_results = analyze_marketplace_page(driver, fb_id)

        # Compare and generate recommendations
        compare_results(profile_results, marketplace_results)
        generate_recommendations(profile_results, marketplace_results)

    finally:
        driver.quit()
        if temp_profile_dir:
            import shutil
            try:
                shutil.rmtree(temp_profile_dir)
            except:
                pass


if __name__ == "__main__":
    main()
