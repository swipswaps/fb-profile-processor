#!/usr/bin/env python3
"""
Selenium-based enricher using existing Firefox profile
Connects to user's Firefox with Facebook already logged in
Enhanced with marketplace data extraction (join date, listings, response rate, badges, images)

Supports:
- Marionette connection to running Firefox (port 2828)
- Profile copy fallback (copies profile to temp dir)
"""
import sqlite3
import time
import os
import re
import json
import shutil
import tempfile
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Import enhanced extraction functions
from selenium_enricher_enhanced import (
    extract_location,
    extract_profile_picture,
    extract_cover_photo,
    extract_join_date,
    extract_active_listings_count,
    extract_response_info,
    extract_seller_badges
)

# Global to track temp profile for cleanup
_temp_profile_dir = None


def get_firefox_profile_path():
    """Find Firefox profile directory"""
    firefox_dir = Path.home() / ".mozilla" / "firefox"

    # Look for default-release profile
    for profile_dir in firefox_dir.glob("*.default-release"):
        return str(profile_dir)

    # Fallback to any default profile
    for profile_dir in firefox_dir.glob("*.default*"):
        return str(profile_dir)

    return None


def copy_firefox_profile(profile_path: str) -> str:
    """
    Copy Firefox profile to temp directory for use while Firefox is running.
    Removes lock files that would prevent concurrent access.

    Returns: Path to copied profile
    """
    global _temp_profile_dir

    # Create temp directory
    _temp_profile_dir = tempfile.mkdtemp(prefix="firefox_profile_copy_")

    print(f"  📋 Copying profile to temp directory...")
    print(f"     Source: {profile_path}")
    print(f"     Dest:   {_temp_profile_dir}")

    # Copy essential files (not the entire profile - would be too slow)
    essential_files = [
        "cookies.sqlite",
        "cookies.sqlite-wal",
        "cookies.sqlite-shm",
        "key4.db",
        "logins.json",
        "cert9.db",
        "prefs.js",
        "user.js",
        "permissions.sqlite",
        "content-prefs.sqlite",
        "formhistory.sqlite",
        "places.sqlite",
        "places.sqlite-wal",
        "places.sqlite-shm",
    ]

    copied_count = 0
    for filename in essential_files:
        src = Path(profile_path) / filename
        dst = Path(_temp_profile_dir) / filename
        if src.exists():
            try:
                shutil.copy2(src, dst)
                copied_count += 1
            except Exception as e:
                print(f"     ⚠️  Could not copy {filename}: {e}")

    print(f"     ✅ Copied {copied_count} profile files")

    # Remove any lock files in the copy
    for lock_file in Path(_temp_profile_dir).glob("*.lock"):
        lock_file.unlink()
    for lock_file in Path(_temp_profile_dir).glob("lock"):
        lock_file.unlink()

    # Create a prefs.js that disables session restore
    prefs_path = Path(_temp_profile_dir) / "prefs.js"
    with open(prefs_path, "a") as f:
        f.write('\n// Added by selenium_enricher to prevent session restore\n')
        f.write('user_pref("browser.sessionstore.resume_from_crash", false);\n')
        f.write('user_pref("browser.startup.page", 0);\n')
        f.write('user_pref("browser.startup.homepage", "about:blank");\n')

    return _temp_profile_dir


def cleanup_temp_profile():
    """Remove temporary profile directory"""
    global _temp_profile_dir
    if _temp_profile_dir and Path(_temp_profile_dir).exists():
        try:
            shutil.rmtree(_temp_profile_dir)
            print(f"  🧹 Cleaned up temp profile: {_temp_profile_dir}")
        except Exception as e:
            print(f"  ⚠️  Could not cleanup temp profile: {e}")
        _temp_profile_dir = None


def update_profile_in_db(conn, db_id, enrichment_data):
    """Update profile in database with enrichment data"""
    cur = conn.cursor()

    update_fields = []
    update_values = []

    for key, value in enrichment_data.items():
        if value is not None:
            update_fields.append(f"{key} = ?")
            update_values.append(value)

    if update_fields:
        update_fields.append("enriched_at = datetime('now')")
        update_values.append(db_id)
        sql = f"UPDATE profiles SET {', '.join(update_fields)} WHERE id = ?"
        cur.execute(sql, update_values)
        conn.commit()


def create_firefox_driver(profile_path: str = None):
    """
    Create Firefox WebDriver with profile.

    ONLY uses profile copy strategy to avoid zombie browsers.
    Direct profile access often fails partially (browser opens but driver fails).

    Args:
        profile_path: Path to Firefox profile. If None, auto-detect.

    Returns:
        Tuple of (WebDriver instance, temp_profile_dir or None)
    """
    # Auto-detect profile path if not provided
    if profile_path is None:
        profile_path = get_firefox_profile_path()
        if not profile_path:
            print("  ❌ Could not find Firefox profile")
            return None, None

    # ONLY use profile copy strategy (more reliable, no zombie browsers)
    print("  📋 Creating browser with profile copy...")
    driver = None
    temp_profile = None
    try:
        temp_profile = copy_firefox_profile(profile_path)
        options = Options()
        options.add_argument("-profile")
        options.add_argument(temp_profile)
        # Disable session restore (don't load previous tabs)
        options.set_preference("browser.sessionstore.resume_from_crash", False)
        options.set_preference("browser.startup.page", 0)  # 0 = blank page
        options.set_preference("browser.startup.homepage_override.mstone", "ignore")
        # Disable crash reporter
        options.set_preference("toolkit.crashreporter.enabled", False)
        # Start headless to avoid blank window flash
        # options.add_argument("-headless")  # Uncomment if you don't need to see browser
        driver = webdriver.Firefox(options=options)
        print("  ✅ Browser created successfully")
        return driver, temp_profile
    except Exception as e:
        print(f"  ❌ Browser creation failed: {e}")
        # Clean up if driver was partially created
        if driver:
            try:
                driver.quit()
            except:
                pass
        cleanup_temp_profile()
        return None, None

def enrich_profile(driver, profile_id, fb_id):
    """
    Visit MARKETPLACE profile page and extract all available data.

    CRITICAL FIX: Uses marketplace URL, not regular profile URL.
    Marketplace-specific data (join date, listings, response rate, badges)
    is ONLY available at facebook.com/marketplace/profile/{fb_id}/
    """
    # FIXED: Use marketplace profile URL, not regular profile URL
    marketplace_url = f"https://www.facebook.com/marketplace/profile/{fb_id}/"

    try:
        print(f"  Visiting MARKETPLACE profile: {marketplace_url}")
        driver.get(marketplace_url)
        time.sleep(5)  # Marketplace pages need more time to load

        # Check if we got redirected to login page
        if "login" in driver.current_url.lower():
            print(f"    ❌ Redirected to login - not authenticated")
            return {"enrichment_status": "failed", "enrichment_error": "Not logged in"}

        # Extract seller name - MARKETPLACE SPECIFIC LOGIC
        # On marketplace pages, seller name is in h2: "{Name}'s listings"
        name = None

        # Strategy 1: Find "{Name}'s listings" h2 element (most reliable)
        try:
            h2_elements = driver.find_elements(By.TAG_NAME, "h2")
            for h2 in h2_elements:
                text = h2.text.strip()
                # Look for pattern: "Name's listings"
                if text and "'s listings" in text:
                    # Extract name: "Olivia C.'s listings" -> "Olivia C."
                    name = text.replace("'s listings", "").strip()
                    break
        except:
            pass

        # Strategy 2: Look for seller name in profile links
        if not name:
            try:
                name_links = driver.find_elements(By.XPATH, "//a[contains(@href, '/marketplace/profile/')]")
                for link in name_links:
                    text = link.text.strip()
                    if text and text not in ["Marketplace", "View profile", ""] and len(text) < 100:
                        name = text
                        break
            except:
                pass

        # Extract username from final URL
        final_url = driver.current_url
        username = None
        if "facebook.com/" in final_url:
            parts = final_url.split("facebook.com/")[1].split("/")[0].split("?")[0]
            if parts and not parts.isdigit() and parts not in ["login", "home", "error", "marketplace"]:
                username = parts

        # === EXTRACT MARKETPLACE DATA ===
        location = extract_location(driver)
        picture_url = extract_profile_picture(driver)
        cover_url = extract_cover_photo(driver)
        join_date = extract_join_date(driver)
        listings_count = extract_active_listings_count(driver)
        response_rate, response_time = extract_response_info(driver)
        seller_badges = extract_seller_badges(driver)

        # Print extraction results
        print(f"    Name: {name or 'Not found'}")
        print(f"    Username: {username or 'Not found'}")
        print(f"    Location: {location or 'Not found'}")
        print(f"    Join Date: {join_date or 'Not found'}")
        print(f"    Active Listings: {listings_count or 'Not found'}")
        print(f"    Profile Pic: {'Found' if picture_url else 'Not found'}")
        print(f"    Cover Photo: {'Found' if cover_url else 'Not found'}")
        print(f"    Response Rate: {response_rate or 'Not found'}")
        print(f"    Badges: {seller_badges or 'None'}")
        print(f"    Final URL: {final_url}")

        # === VALIDATION: Count extracted fields ===
        result = {
            "fb_name": name,
            "fb_username": username,
            "fb_link": final_url,
            "fb_location_name": location,
            "fb_picture_url": picture_url,
            "fb_cover_url": cover_url,
            "fb_join_date": join_date,
            "fb_active_listings_count": listings_count,
            "fb_response_rate": response_rate,
            "fb_response_time": response_time,
            "fb_seller_badges": seller_badges,
        }

        # Status logic: Weight critical vs optional fields
        # Critical fields are those that are almost always available on marketplace profiles
        critical_fields = ['fb_name', 'fb_join_date', 'fb_picture_url']  # Usually available
        optional_fields = ['fb_active_listings_count', 'fb_response_rate', 'fb_response_time',
                          'fb_seller_badges', 'fb_cover_url']  # Often missing

        critical_count = sum(1 for f in critical_fields if result.get(f) is not None and result.get(f) != '')
        optional_count = sum(1 for f in optional_fields if result.get(f) is not None and result.get(f) != '')
        total_count = critical_count + optional_count
        total_fields = len(critical_fields) + len(optional_fields)

        print(f"\n    📊 EXTRACTION VALIDATION:")
        print(f"    Critical fields: {critical_count}/{len(critical_fields)} (name, join_date, picture)")
        print(f"    Optional fields: {optional_count}/{len(optional_fields)} (listings, response, badges, cover)")
        print(f"    Total: {total_count}/{total_fields}")

        # Status based on critical field coverage
        if critical_count >= 2:  # At least 2 of 3 critical fields
            result["enrichment_status"] = "enriched"
            print(f"    ✅ Status: ENRICHED")
        elif critical_count >= 1:  # At least 1 critical field
            result["enrichment_status"] = "partial"
            print(f"    ⚠️  Status: PARTIAL (need more critical fields)")
        else:
            result["enrichment_status"] = "failed"
            print(f"    ❌ Status: FAILED (no critical fields extracted)")

        result["enrichment_method"] = "selenium_marketplace"
        return result

    except Exception as e:
        print(f"    Error: {e}")
        return {
            "enrichment_status": "failed",
            "enrichment_error": str(e)
        }

def main():
    import sys

    db_path = "test_profiles.db"
    force_reenrich = "--force" in sys.argv or "-f" in sys.argv

    print("🔍 Selenium Facebook Profile Enricher (Enhanced)")
    print("=" * 60)
    if force_reenrich:
        print("⚡ FORCE MODE: Re-enriching all profiles with empty marketplace data")
    print()

    # Find Firefox profile
    profile_path = get_firefox_profile_path()
    if not profile_path:
        print("❌ Could not find Firefox profile")
        print("   Expected location: ~/.mozilla/firefox/*.default-release")
        return

    print(f"✅ Found Firefox profile: {profile_path}")
    print()

    # Connect to database
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get profiles to enrich
    if force_reenrich:
        # Force mode: Re-enrich ALL profiles with fb_id (including those with bad names)
        cur.execute("""
            SELECT id, fb_id, input_url
            FROM profiles
            WHERE fb_id IS NOT NULL
            LIMIT 10
        """)
    else:
        # Normal mode: Only enrich pending/partial profiles
        cur.execute("""
            SELECT id, fb_id, input_url
            FROM profiles
            WHERE fb_id IS NOT NULL
            AND (enrichment_status IS NULL OR enrichment_status = 'pending' OR enrichment_status = 'partial')
            LIMIT 10
        """)
    profiles = cur.fetchall()

    if not profiles:
        print("❌ No profiles to enrich")
        print("   Tip: Use --force to re-enrich profiles with missing marketplace data")
        return

    print(f"📊 Found {len(profiles)} profiles to enrich")
    print()

    # Setup Firefox with existing profile (handles running Firefox)
    print("🌐 Starting Firefox with your profile...")
    print("   (Will copy profile if Firefox is already running)")
    print()

    try:
        driver, temp_profile_dir = create_firefox_driver(profile_path)
        if driver is None:
            print(f"❌ Could not start Firefox")
            return
    except Exception as e:
        print(f"❌ Could not start Firefox: {e}")
        return

    try:
        # Check if logged into Facebook
        print("🔐 Checking Facebook login...")
        driver.get("https://www.facebook.com")
        time.sleep(3)

        if "login" in driver.current_url.lower():
            print()
            print("❌ NOT LOGGED INTO FACEBOOK")
            print("   Please log in to Facebook in the browser window")
            print("   Then press Enter to continue...")
            input()
        else:
            print("✅ Logged into Facebook!")

        print()
        print("🚀 Starting enrichment (using MARKETPLACE URLs)...")
        print()

        success_count = 0
        partial_count = 0
        fail_count = 0

        # Process each profile
        for i, (profile_id, fb_id, input_url) in enumerate(profiles, 1):
            print(f"[{i}/{len(profiles)}] Profile ID: {profile_id}, FB ID: {fb_id}")

            result = enrich_profile(driver, profile_id, fb_id)

            status = result.get('enrichment_status', 'failed')
            if status == 'enriched':
                success_count += 1
            elif status == 'partial':
                partial_count += 1
            else:
                fail_count += 1

            # Update database
            update_fields = []
            update_values = []

            for key, value in result.items():
                if value is not None:
                    update_fields.append(f"{key} = ?")
                    update_values.append(value)

            if update_fields:
                update_fields.append("enriched_at = datetime('now')")
                update_values.append(profile_id)
                sql = f"UPDATE profiles SET {', '.join(update_fields)} WHERE id = ?"
                cur.execute(sql, update_values)
                conn.commit()

            # Rate limiting
            if i < len(profiles):
                time.sleep(2)

            print()

        # === FINAL VALIDATION REPORT ===
        print("=" * 70)
        print("ENRICHMENT SUMMARY")
        print("=" * 70)
        total = len(profiles)
        print(f"Total profiles processed: {total}")
        print(f"  ✅ Enriched (≥50% fields): {success_count}")
        print(f"  ⚠️  Partial (<50% fields):  {partial_count}")
        print(f"  ❌ Failed:                 {fail_count}")

        overall_success = ((success_count + partial_count) / total * 100) if total > 0 else 0
        print(f"\nOverall Success Rate: {overall_success:.1f}%")

        if overall_success >= 80:
            print("\n✅ ENRICHMENT COMPLETED SUCCESSFULLY")
        elif overall_success >= 50:
            print("\n⚠️  ENRICHMENT PARTIALLY SUCCESSFUL - Some profiles need review")
        else:
            print("\n❌ ENRICHMENT FAILED - Most profiles did not extract properly")
            print("   Possible causes:")
            print("   • XPath selectors may need updating")
            print("   • Page structure may have changed")
            print("   • Need to scroll to load marketplace data")

        # Show sample of extracted data
        print("\n" + "=" * 70)
        print("SAMPLE EXTRACTED DATA (proof of extraction)")
        print("=" * 70)
        cur.execute("""
            SELECT fb_id, fb_name, fb_join_date, fb_active_listings_count, fb_picture_url
            FROM profiles
            WHERE fb_join_date IS NOT NULL OR fb_picture_url IS NOT NULL
            ORDER BY enriched_at DESC
            LIMIT 3
        """)
        samples = cur.fetchall()
        if samples:
            for fb_id, name, join_date, listings, pic_url in samples:
                print(f"\n  {name} ({fb_id}):")
                print(f"    Join Date: {join_date or 'Not found'}")
                print(f"    Listings:  {listings or 'Not found'}")
                print(f"    Picture:   {'Found' if pic_url else 'Not found'}")
        else:
            print("\n  ❌ No marketplace data extracted for any profile")
            print("     This indicates a fundamental extraction issue")

    finally:
        driver.quit()
        conn.close()
        if temp_profile_dir:
            shutil.rmtree(temp_profile_dir, ignore_errors=True)
            print(f"\n  🧹 Cleaned up temp profile: {temp_profile_dir}")

    print()
    print("📊 Verify results with test script:")
    print(f"   python3 test_extraction.py {db_path} 100024126863464")

if __name__ == "__main__":
    main()

