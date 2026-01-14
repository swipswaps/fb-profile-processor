#!/usr/bin/env python3
"""
Marketplace Scraper - Extract logged-in user info and their selling items

Supports two methods:
1. Facebook Graph API (preferred when access token available)
2. Browser scraping via Firefox profile (fallback)

Future: When Facebook API access is available, set FB_ACCESS_TOKEN env var
"""
import sqlite3
import time
import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium_enricher import get_firefox_profile_path, create_firefox_driver, cleanup_temp_profile


# =============================================================================
# FACEBOOK API LAYER (Future-proofing)
# =============================================================================

class FacebookMarketplaceAPI:
    """
    Facebook Graph API interface for Marketplace.

    Note: Facebook Marketplace API access is restricted and requires:
    - Facebook App approval
    - Commerce account setup
    - Specific permissions

    This class is ready for when API access becomes available.
    Currently falls back to browser scraping.
    """

    def __init__(self, access_token: str = None):
        self.access_token = access_token or os.environ.get('FB_ACCESS_TOKEN')
        self.api_base = "https://graph.facebook.com/v18.0"
        self.api_available = False

        if self.access_token:
            self.api_available = self._verify_token()

    def _verify_token(self) -> bool:
        """Verify if the access token is valid."""
        try:
            resp = requests.get(
                f"{self.api_base}/me",
                params={"access_token": self.access_token},
                timeout=10
            )
            return resp.status_code == 200
        except:
            return False

    def get_my_listings(self, limit: int = 50) -> list:
        """
        Get user's marketplace listings via API.

        Note: This endpoint requires special permissions that most apps don't have.
        Returns empty list if API unavailable.
        """
        if not self.api_available:
            return []

        # This would be the API call if we had access:
        # GET /me/marketplace_listings
        # For now, return empty to trigger fallback
        return []

    def get_user_info(self) -> dict:
        """Get logged-in user info via API."""
        if not self.api_available:
            return None

        try:
            resp = requests.get(
                f"{self.api_base}/me",
                params={
                    "access_token": self.access_token,
                    "fields": "id,name,picture"
                },
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "fb_id": data.get("id"),
                    "fb_name": data.get("name"),
                    "profile_picture_url": data.get("picture", {}).get("data", {}).get("url")
                }
        except:
            pass
        return None


# Global API instance - will use if token available
_fb_api = None

def get_facebook_api() -> FacebookMarketplaceAPI:
    """Get or create Facebook API instance."""
    global _fb_api
    if _fb_api is None:
        _fb_api = FacebookMarketplaceAPI()
    return _fb_api


# =============================================================================
# BROWSER MANAGEMENT (Simplified - no persistence to avoid zombie processes)
# =============================================================================

def kill_zombie_browsers():
    """Kill any leftover Firefox/geckodriver processes from previous runs."""
    # Don't use pkill as it can kill the parent process
    # Just rely on proper driver.quit() and cleanup_temp_profile()
    pass


def create_single_use_browser():
    """
    Create a browser for a single operation.
    MUST be closed after use with driver.quit().
    """
    profile_path = get_firefox_profile_path()
    if not profile_path:
        return None, None

    driver, temp_profile = create_firefox_driver(profile_path)
    return driver, temp_profile


# Stub functions for compatibility
def get_persistent_browser():
    """Deprecated - returns None. Use create_single_use_browser instead."""
    return None


def close_persistent_browser():
    """Deprecated - no-op. Browser is closed after each use now."""
    pass


# =============================================================================
# API CONFIGURATION
# =============================================================================

CONFIG_FILE = Path(__file__).parent / ".fb_config.json"

def load_fb_config() -> dict:
    """Load Facebook API configuration."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def save_fb_config(config: dict):
    """Save Facebook API configuration."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_access_token() -> str:
    """Get Facebook access token from config or environment."""
    # Environment variable takes precedence
    token = os.environ.get('FB_ACCESS_TOKEN')
    if token:
        return token

    # Fall back to config file
    config = load_fb_config()
    return config.get('access_token')


def set_access_token(token: str) -> bool:
    """Set and validate Facebook access token."""
    config = load_fb_config()
    config['access_token'] = token
    save_fb_config(config)

    # Update the global API instance
    global _fb_api
    _fb_api = FacebookMarketplaceAPI(token)
    return _fb_api.api_available


def test_access_token(token: str) -> tuple:
    """
    Test if an access token is valid.
    Returns: (is_valid: bool, user_info: dict or error_message: str)
    """
    try:
        resp = requests.get(
            "https://graph.facebook.com/v18.0/me",
            params={"access_token": token, "fields": "id,name"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return True, {"fb_id": data.get("id"), "fb_name": data.get("name")}
        else:
            error = resp.json().get("error", {}).get("message", "Unknown error")
            return False, error
    except Exception as e:
        return False, str(e)


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def init_marketplace_db(db_path: str = "marketplace.db"):
    """Initialize marketplace items database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT UNIQUE,
            title TEXT,
            price TEXT,
            price_numeric REAL,
            description TEXT,
            category TEXT,
            category_id TEXT,
            condition TEXT,
            location TEXT,
            listed_date TEXT,
            status TEXT DEFAULT 'available',
            is_sold INTEGER DEFAULT 0,
            is_pending INTEGER DEFAULT 0,
            is_draft INTEGER DEFAULT 0,
            bump_count INTEGER DEFAULT 0,
            days_until_next_bump INTEGER,
            max_bump_count INTEGER DEFAULT 5,
            image_urls TEXT,
            local_image_paths TEXT,
            seller_id TEXT,
            seller_name TEXT,
            item_url TEXT,
            scraped_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Add new columns if they don't exist (for existing databases)
    new_columns = [
        ("category_id", "TEXT"),
        ("is_sold", "INTEGER DEFAULT 0"),
        ("is_pending", "INTEGER DEFAULT 0"),
        ("is_draft", "INTEGER DEFAULT 0"),
        ("bump_count", "INTEGER DEFAULT 0"),
        ("days_until_next_bump", "INTEGER"),
        ("max_bump_count", "INTEGER DEFAULT 5"),
    ]
    for col_name, col_type in new_columns:
        try:
            cur.execute(f"ALTER TABLE marketplace_items ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logged_in_user (
            id INTEGER PRIMARY KEY,
            fb_id TEXT,
            fb_name TEXT,
            fb_username TEXT,
            profile_picture_url TEXT,
            last_checked TEXT DEFAULT (datetime('now'))
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"✅ Marketplace database initialized: {db_path}")


def get_logged_in_user(driver) -> dict:
    """
    Detect the currently logged-in Facebook user.
    
    Returns dict with: fb_id, fb_name, fb_username, profile_picture_url
    """
    print("🔐 Detecting logged-in Facebook user...")
    
    try:
        # Go to Facebook home
        driver.get("https://www.facebook.com")
        time.sleep(3)
        
        # Check if logged in
        if "login" in driver.current_url.lower():
            print("  ❌ Not logged into Facebook")
            return None
        
        # Try to get user info from the profile link in nav
        user_info = {}
        
        # Method 1: Find profile link in navigation
        try:
            # Look for the user's profile link
            profile_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/me/"], a[href*="profile.php"]')
            for link in profile_links:
                href = link.get_attribute("href")
                if href and ("/me" in href or "profile.php" in href):
                    # Navigate to profile to get ID
                    driver.get("https://www.facebook.com/me/")
                    time.sleep(2)
                    
                    # Get the redirected URL which contains ID or username
                    final_url = driver.current_url
                    if "facebook.com/" in final_url:
                        path = final_url.split("facebook.com/")[1].split("?")[0].rstrip("/")
                        if path.isdigit():
                            user_info["fb_id"] = path
                        else:
                            user_info["fb_username"] = path
                    break
        except Exception as e:
            print(f"  ⚠️ Could not find profile link: {e}")
        
        # Method 2: Get name from page
        try:
            # Go to profile page
            driver.get("https://www.facebook.com/me/")
            time.sleep(2)
            
            # Find the h1 with the user's name
            h1_elements = driver.find_elements(By.TAG_NAME, "h1")
            for h1 in h1_elements:
                text = h1.text.strip()
                if text and len(text) > 1 and len(text) < 100:
                    user_info["fb_name"] = text
                    break
        except Exception as e:
            print(f"  ⚠️ Could not get name: {e}")
        
        # Method 3: Get profile picture
        try:
            # Look for profile picture image
            img_elements = driver.find_elements(By.CSS_SELECTOR, 'image, img[alt*="profile"], svg image')
            for img in img_elements:
                src = img.get_attribute("xlink:href") or img.get_attribute("src")
                if src and "scontent" in src:
                    user_info["profile_picture_url"] = src
                    break
        except Exception as e:
            print(f"  ⚠️ Could not get profile picture: {e}")
        
        if user_info.get("fb_name") or user_info.get("fb_username"):
            print(f"  ✅ Logged in as: {user_info.get('fb_name', user_info.get('fb_username', 'Unknown'))}")
            return user_info
        else:
            print("  ⚠️ Could not determine user info")
            return None
            
    except Exception as e:
        print(f"  ❌ Error detecting user: {e}")
        return None


def get_user_selling_items(driver, limit: int = 50, download_images: bool = True) -> list:
    """
    Get items the logged-in user is currently selling.
    Captures: title, price, image URL, item URL in the order shown on Facebook.

    Returns list of item dicts.
    """
    print(f"🛒 Fetching your marketplace listings (limit: {limit})...")

    items = []
    seen_ids = set()

    try:
        # Navigate to user's selling page
        driver.get("https://www.facebook.com/marketplace/you/selling")
        time.sleep(4)

        # Check if we're on the right page
        if "login" in driver.current_url.lower():
            print("  ❌ Not logged in - redirected to login page")
            return items

        # Scroll to load all items
        for scroll in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        # Find all item links - these contain the item cards
        item_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/marketplace/item/"]')
        print(f"  Found {len(item_links)} item links")

        for link in item_links:
            if len(items) >= limit:
                break

            try:
                href = link.get_attribute("href")
                if not href:
                    continue

                # Extract item ID
                match = re.search(r'/marketplace/item/(\d+)', href)
                if not match:
                    continue

                item_id = match.group(1)
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Get the card container (parent elements)
                card = link
                for _ in range(6):
                    try:
                        card = card.find_element(By.XPATH, "..")
                    except:
                        break

                # Extract text - FB typically shows: price, title, location
                card_text = card.text.strip()
                lines = [l.strip() for l in card_text.split('\n') if l.strip()]

                price = None
                title = None
                location = None

                for line in lines:
                    if not price and ('$' in line or line.lower() == 'free'):
                        price = line
                    elif not title and len(line) > 2 and line != price:
                        title = line
                    elif title and not location and len(line) > 2:
                        location = line
                        break

                # Extract image URL from the card
                image_url = None
                try:
                    # Try to find image in the link or its children
                    img_elements = link.find_elements(By.TAG_NAME, 'img')
                    for img in img_elements:
                        src = img.get_attribute('src')
                        if src and 'scontent' in src:
                            image_url = src
                            break

                    # Also check for background images in style
                    if not image_url:
                        divs = link.find_elements(By.CSS_SELECTOR, 'div[style*="background-image"]')
                        for div in divs:
                            style = div.get_attribute('style')
                            if style and 'url(' in style:
                                match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                                if match:
                                    image_url = match.group(1)
                                    break
                except Exception as e:
                    pass

                item = {
                    "item_id": item_id,
                    "title": title or f"Item {item_id}",
                    "price": price or "Price not listed",
                    "location": location,
                    "image_url": image_url,
                    "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
                    "status": "available"
                }
                items.append(item)
                print(f"    [{len(items)}] {price} - {title[:40] if title else 'Untitled'}...")

            except Exception as e:
                continue

        print(f"  ✅ Found {len(items)} items")

        # Download images if requested
        if download_images and items:
            download_item_images(items)

        return items

    except Exception as e:
        print(f"  ❌ Error fetching items: {e}")
        import traceback
        traceback.print_exc()
        return items


def download_item_images(items: list, images_dir: str = "marketplace_images"):
    """Download item images to local directory"""
    import requests

    Path(images_dir).mkdir(exist_ok=True)

    for item in items:
        image_url = item.get("image_url")
        if not image_url:
            continue

        item_id = item.get("item_id")
        local_path = Path(images_dir) / f"{item_id}.jpg"

        if local_path.exists():
            item["local_image_path"] = str(local_path)
            continue

        try:
            resp = requests.get(image_url, timeout=10)
            if resp.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                item["local_image_path"] = str(local_path)
                print(f"    📷 Downloaded image for {item_id}")
        except Exception as e:
            print(f"    ⚠️ Could not download image for {item_id}: {e}")


def save_user_to_db(user_info: dict, db_path: str = "marketplace.db"):
    """
    Save logged-in user info to database.
    ONLY saves if we have REAL data - never overwrites good data with defaults.
    """
    if not user_info:
        return

    # Check if we have REAL data (not just defaults)
    new_name = user_info.get("fb_name", "")
    new_id = user_info.get("fb_id", "")
    new_username = user_info.get("fb_username", "")

    # If all we have is "Facebook User" default, don't overwrite existing data
    has_real_name = new_name and new_name != "Facebook User"
    has_real_id = bool(new_id)
    has_real_username = bool(new_username)

    if not (has_real_name or has_real_id or has_real_username):
        print(f"  ⚠️ No real user data to save, keeping existing")
        return

    init_marketplace_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # Check existing data first
        cur.execute("SELECT fb_id, fb_name, fb_username FROM logged_in_user WHERE id=1")
        existing = cur.fetchone()

        if existing:
            existing_id, existing_name, existing_username = existing
            # Only overwrite if new data is better
            if existing_name and existing_name != "Facebook User" and not has_real_name:
                # Existing has real name, new doesn't - keep existing
                print(f"  ℹ️ Keeping existing user: {existing_name}")
                conn.close()
                return

        # We have better data - save it
        cur.execute("DELETE FROM logged_in_user")
        cur.execute("""
            INSERT INTO logged_in_user (id, fb_id, fb_name, fb_username, profile_picture_url)
            VALUES (1, ?, ?, ?, ?)
        """, (
            user_info.get("fb_id"),
            user_info.get("fb_name"),
            user_info.get("fb_username"),
            user_info.get("profile_picture_url")
        ))
        conn.commit()
        print(f"  💾 Saved user info: {user_info.get('fb_name', 'Unknown')}")
    except Exception as e:
        print(f"  ⚠️ Could not save user: {e}")
    finally:
        conn.close()


def save_items_to_db(items: list, seller_info: dict, db_path: str = "marketplace.db"):
    """Save marketplace items to database with images and status info"""
    if not items:
        print("  ⚠️ No items to save")
        return 0

    init_marketplace_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    saved_count = 0
    for item in items:
        try:
            cur.execute("""
                INSERT OR REPLACE INTO marketplace_items
                (item_id, title, price, location, item_url, image_urls, local_image_paths,
                 status, is_sold, is_pending, is_draft, category_id,
                 bump_count, days_until_next_bump, max_bump_count,
                 seller_id, seller_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                item.get("item_id"),
                item.get("title"),
                item.get("price"),
                item.get("location"),
                item.get("item_url"),
                item.get("image_url"),  # Store in image_urls field
                item.get("local_image_path"),
                item.get("status", "available"),
                1 if item.get("is_sold") else 0,
                1 if item.get("is_pending") else 0,
                1 if item.get("is_draft") else 0,
                item.get("category_id"),
                item.get("bump_count", 0),
                item.get("days_until_next_bump"),
                item.get("max_bump_count", 5),
                seller_info.get("fb_id") or seller_info.get("fb_username"),
                seller_info.get("fb_name")
            ))
            saved_count += 1
        except Exception as e:
            print(f"  ⚠️ Could not save item {item.get('item_id')}: {e}")

    # Save logged-in user info
    if seller_info:
        cur.execute("DELETE FROM logged_in_user")
        cur.execute("""
            INSERT INTO logged_in_user (id, fb_id, fb_name, fb_username, profile_picture_url)
            VALUES (1, ?, ?, ?, ?)
        """, (
            seller_info.get("fb_id"),
            seller_info.get("fb_name"),
            seller_info.get("fb_username"),
            seller_info.get("profile_picture_url")
        ))

    conn.commit()
    conn.close()
    print(f"  ✅ Saved {saved_count} items to {db_path}")
    return saved_count


def check_facebook_login_status():
    """
    Quick check if Firefox profile has Facebook login.
    Returns: (is_logged_in: bool, user_info: dict or None)
    """
    # Kill any zombie browsers first
    kill_zombie_browsers()

    driver = None
    try:
        driver, temp_profile = create_single_use_browser()
        if not driver:
            return False, None

        user_info = get_logged_in_user(driver)
        return user_info is not None, user_info

    except Exception as e:
        print(f"Error checking login: {e}")
        return False, None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        cleanup_temp_profile()
        kill_zombie_browsers()


def scrape_my_listings_fast(db_path: str = "marketplace.db", limit: int = 50):
    """
    Go directly to selling page, extract user info from there.
    Always closes browser after use to prevent zombie processes.
    """
    print("🛒 Scanning Marketplace listings...")

    # Kill any zombie browsers first
    kill_zombie_browsers()

    driver = None
    try:
        # Create browser for this operation
        print("  🔄 Starting browser...")
        driver, temp_profile = create_single_use_browser()

        if not driver:
            print("❌ Could not start Firefox")
            return None, []

        # Go DIRECTLY to selling page - single navigation
        print("  📍 Navigating to your selling page...")
        driver.get("https://www.facebook.com/marketplace/you/selling")
        time.sleep(3)

        # Check if redirected to login (not logged in)
        if "login" in driver.current_url.lower():
            print("❌ Not logged into Facebook")
            return None, []

        print(f"  ✅ On page: {driver.current_url}")

        # Extract user info - get ACTUAL name by visiting profile page
        user_info = {}
        try:
            # First get user ID from the selling page
            profile_elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/marketplace/profile/"]')
            for elem in profile_elements:
                href = elem.get_attribute("href")
                if href:
                    match = re.search(r'/marketplace/profile/(\d+)', href)
                    if match:
                        user_info["fb_id"] = match.group(1)
                        print(f"  👤 Found user ID: {user_info['fb_id']}")
                        break

            # Now get ACTUAL name by visiting user's profile page
            if user_info.get("fb_id"):
                profile_url = f"https://www.facebook.com/profile.php?id={user_info['fb_id']}"
                print(f"  📍 Getting name from profile...")
                driver.get(profile_url)
                time.sleep(2)

                # Method 1: Find h1 tag with the name
                h1_elements = driver.find_elements(By.TAG_NAME, "h1")
                for h1 in h1_elements:
                    text = h1.text.strip()
                    # Filter out common non-name text
                    if text and len(text) > 1 and len(text) < 50:
                        if text.lower() not in ['facebook', 'marketplace', 'profile', 'your profile']:
                            user_info["fb_name"] = text
                            print(f"  👤 Found name: {text}")
                            break

                # Go back to selling page for item extraction
                driver.get("https://www.facebook.com/marketplace/you/selling")
                time.sleep(4)  # Wait longer for page to fully load

            # Fallback: Try aria-label on selling page
            if "fb_name" not in user_info:
                name_elems = driver.find_elements(By.CSS_SELECTOR, '[aria-label*="profile"]')
                for elem in name_elems:
                    label = elem.get_attribute("aria-label")
                    if label and "profile" in label.lower():
                        parts = label.split(",")
                        if len(parts) > 1:
                            user_info["fb_name"] = parts[1].strip()
                            break

            # Method 3: Look for account switcher which shows name
            if "fb_name" not in user_info:
                switcher = driver.find_elements(By.CSS_SELECTOR, '[aria-label="Your profile"]')
                for elem in switcher:
                    parent = elem.find_element(By.XPATH, "..")
                    text = parent.text.strip()
                    if text and len(text) > 1:
                        user_info["fb_name"] = text.split('\n')[0]
                        break

            if user_info.get("fb_id"):
                print(f"  👤 User ID: {user_info['fb_id']}")
            if user_info.get("fb_name"):
                print(f"  👤 Name: {user_info['fb_name']}")

        except Exception as e:
            print(f"  ⚠️ Could not extract user info: {e}")

        # Fallback if no name found
        if "fb_name" not in user_info:
            user_info["fb_name"] = "Facebook User"

        # Wait for page to fully load before scrolling
        print("  ⏳ Waiting for page to load...")
        time.sleep(3)

        # Scroll to load ALL items - scroll until no new items appear
        print("  📜 Scrolling to load all items...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_count = 0
        max_scrolls = 20  # Safety limit
        no_change_count = 0  # Track consecutive no-change scrolls

        while scroll_count < max_scrolls:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Longer wait for Facebook's lazy loading
            new_height = driver.execute_script("return document.body.scrollHeight")

            if new_height == last_height:
                no_change_count += 1
                if no_change_count >= 2:  # Only stop after 2 consecutive no-change
                    print(f"  ✅ Reached bottom after {scroll_count + 1} scrolls")
                    break
            else:
                no_change_count = 0  # Reset counter when we get new content

            last_height = new_height
            scroll_count += 1

            # Show progress
            if scroll_count % 3 == 0:
                print(f"  📜 Scrolled {scroll_count} times...")

        # Extract items directly
        items = extract_items_from_current_page(driver, limit)

        # ALWAYS save user info to database (even if no items)
        # This ensures login persists across page reloads
        save_user_to_db(user_info, db_path)

        # Save items if any found
        if items:
            save_items_to_db(items, user_info, db_path)
            download_item_images(items)

        print(f"✅ Found {len(items)} listings")
        return user_info, items

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, []
    finally:
        # ALWAYS close the browser
        if driver:
            try:
                driver.quit()
            except:
                pass
        cleanup_temp_profile()
        # Extra cleanup
        kill_zombie_browsers()


def extract_items_from_current_page(driver, limit: int = 50) -> list:
    """
    Extract items from the current page (already on selling page).
    Extracts real titles, prices, and images from Facebook's embedded JSON.
    """
    items = []
    seen_ids = set()

    # Get page source for analysis
    page_source = driver.page_source

    # DEBUG: Save page source for analysis
    debug_path = "/tmp/fb_selling_page.html"
    try:
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(page_source)
        print(f"  📄 Saved page source to {debug_path} ({len(page_source)} chars)")
    except Exception as e:
        print(f"  ⚠️ Could not save debug: {e}")

    # Strategy 1: Extract FULL listing data from embedded JSON
    # Facebook embeds listing data with id, title, price, image together
    # Pattern: "id":"1825376291440129","marketplace_listing_title":"SolarEdge..."

    # Find all listings with full data
    listing_pattern = r'"id":"(\d+)","marketplace_listing_title":"([^"]+)"'
    matches = re.findall(listing_pattern, page_source)
    print(f"  Found {len(matches)} listings with titles")

    # Build a mapping of id -> title
    id_to_title = {m[0]: m[1] for m in matches}

    # Find prices - pattern: "formatted_price":{"text":"$X,XXX"}
    price_pattern = r'"id":"(\d+)"[^}]*"formatted_price":\{"text":"([^"]+)"'
    # Alternative: search near the ID
    price_matches = re.findall(price_pattern, page_source)
    id_to_price = {m[0]: m[1] for m in price_matches}

    # If that didn't work, try finding prices differently
    if not id_to_price:
        # Look for amount in listing_price
        for item_id in id_to_title.keys():
            # Search for price near this ID
            idx = page_source.find(f'"id":"{item_id}"')
            if idx > 0:
                # Look for price within 500 chars after ID
                snippet = page_source[idx:idx+500]
                price_match = re.search(r'"formatted_amount":"([^"]+)"', snippet)
                if price_match:
                    id_to_price[item_id] = price_match.group(1)
                else:
                    # Try another pattern
                    price_match = re.search(r'"amount":"(\d+)"', snippet)
                    if price_match:
                        amount = int(price_match.group(1))
                        id_to_price[item_id] = f"${amount:,}"

    # Find images - pattern: "primary_listing_photo":{"__typename":"Photo","image":{"uri":"https..."}}
    id_to_image = {}
    # Also extract status flags and bump info
    id_to_status = {}  # {item_id: {is_sold, is_pending, is_draft, category_id, bump_count, days_until_next_bump, max_bump_count}}

    for item_id in id_to_title.keys():
        idx = page_source.find(f'"id":"{item_id}"')
        if idx > 0:
            # Get a larger snippet to capture all fields
            snippet = page_source[idx:idx+2500]

            # Look for image URI
            img_match = re.search(r'"primary_listing_photo"[^}]*"image":\{"uri":"([^"]+)"', snippet)
            if img_match:
                # Unescape the URL
                img_url = img_match.group(1).replace('\\/', '/')
                id_to_image[item_id] = img_url

            # Extract status flags
            status_info = {}

            # is_sold
            sold_match = re.search(r'"is_sold":(\w+)', snippet)
            if sold_match:
                status_info['is_sold'] = sold_match.group(1) == 'true'

            # is_pending
            pending_match = re.search(r'"is_pending":(\w+)', snippet)
            if pending_match:
                status_info['is_pending'] = pending_match.group(1) == 'true'

            # is_draft
            draft_match = re.search(r'"is_draft":(\w+)', snippet)
            if draft_match:
                status_info['is_draft'] = draft_match.group(1) == 'true'

            # category_id
            cat_match = re.search(r'"marketplace_listing_category_id":"(\d+)"', snippet)
            if cat_match:
                status_info['category_id'] = cat_match.group(1)

            # bump info
            bump_match = re.search(r'"bump_count":(\d+)', snippet)
            if bump_match:
                status_info['bump_count'] = int(bump_match.group(1))

            days_match = re.search(r'"days_until_next_bump":(\d+)', snippet)
            if days_match:
                status_info['days_until_next_bump'] = int(days_match.group(1))

            max_bump_match = re.search(r'"max_bump_count":(\d+)', snippet)
            if max_bump_match:
                status_info['max_bump_count'] = int(max_bump_match.group(1))

            if status_info:
                id_to_status[item_id] = status_info

    print(f"  Found {len(id_to_price)} prices, {len(id_to_image)} images, {len(id_to_status)} status records")

    # Build items with full data
    for item_id, title in id_to_title.items():
        if len(items) >= limit:
            break
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        status_info = id_to_status.get(item_id, {})

        # Determine display status
        if status_info.get('is_sold'):
            display_status = 'sold'
        elif status_info.get('is_pending'):
            display_status = 'pending'
        elif status_info.get('is_draft'):
            display_status = 'draft'
        else:
            display_status = 'available'

        items.append({
            "item_id": item_id,
            "title": title,
            "price": id_to_price.get(item_id, "See on Facebook"),
            "location": None,
            "image_url": id_to_image.get(item_id),
            "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
            "status": display_status,
            "is_sold": status_info.get('is_sold', False),
            "is_pending": status_info.get('is_pending', False),
            "is_draft": status_info.get('is_draft', False),
            "category_id": status_info.get('category_id'),
            "bump_count": status_info.get('bump_count', 0),
            "days_until_next_bump": status_info.get('days_until_next_bump'),
            "max_bump_count": status_info.get('max_bump_count', 5),
        })

    if items:
        print(f"  ✅ Extracted {len(items)} items with full details")
        return items

    # Fallback: Strategy 2 - Just find IDs if full extraction failed
    print("  ⚠️ Full extraction failed, falling back to ID-only...")
    all_patterns = [
        (r'/marketplace/item/(\d+)', 'standard URL'),
        (r'GroupCommerceProductItem[^}]*"id":"(\d+)"', 'GroupCommerceProductItem'),
    ]

    unique_ids = set()
    for pattern, name in all_patterns:
        found = re.findall(pattern, page_source)
        if found:
            unique_ids.update(found)

    for item_id in unique_ids:
        if len(items) >= limit:
            break
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        items.append({
            "item_id": item_id,
            "title": f"Item {item_id}",
            "price": "See on Facebook",
            "location": None,
            "image_url": None,
            "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
            "status": "available"
        })

    if items:
        print(f"  ✅ Extracted {len(items)} items (ID only)")
        return items

    # Strategy 3: Find all links and filter for marketplace items
    item_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/marketplace/item/"]')
    if not item_links:
        all_links = driver.find_elements(By.TAG_NAME, 'a')
        for link in all_links:
            href = link.get_attribute('href') or ''
            if '/marketplace/item/' in href:
                item_links.append(link)
        print(f"  Strategy 3: Found {len(item_links)} marketplace item links")

    # Process found links
    for link in item_links:
        if len(items) >= limit:
            break

        try:
            href = link.get_attribute("href")
            if not href:
                continue

            match = re.search(r'/marketplace/item/(\d+)', href)
            if not match:
                continue

            item_id = match.group(1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            # Get card container by walking up the DOM
            card = link
            card_text = ""
            for _ in range(8):  # Go up more levels
                try:
                    card = card.find_element(By.XPATH, "..")
                    card_text = card.text.strip()
                    # Stop when we have enough text (price + title at minimum)
                    if len(card_text) > 10 and '\n' in card_text:
                        break
                except:
                    break

            # Extract text
            lines = [l.strip() for l in card_text.split('\n') if l.strip()]

            price = None
            title = None
            location = None

            for line in lines:
                # Skip navigation/button text
                if line.lower() in ['selling', 'your listings', 'create new listing', 'see all']:
                    continue
                if not price and ('$' in line or line.lower() == 'free'):
                    price = line
                elif not title and len(line) > 2 and line != price:
                    title = line
                elif title and not location and len(line) > 2 and '$' not in line:
                    location = line
                    break

            # Extract image - try multiple methods
            image_url = None
            try:
                # Method 1: img tag inside link
                img_elements = link.find_elements(By.TAG_NAME, 'img')
                for img in img_elements:
                    src = img.get_attribute('src')
                    if src and ('scontent' in src or 'fbcdn' in src):
                        image_url = src
                        break

                # Method 2: background-image style
                if not image_url:
                    divs = link.find_elements(By.CSS_SELECTOR, 'div[style*="background"]')
                    for div in divs:
                        style = div.get_attribute('style') or ''
                        if 'url(' in style:
                            url_match = re.search(r'url\(["\']?(https://[^"\']+)["\']?\)', style)
                            if url_match:
                                image_url = url_match.group(1)
                                break
            except:
                pass

            items.append({
                "item_id": item_id,
                "title": title or f"Item {item_id}",
                "price": price or "Price not listed",
                "location": location,
                "image_url": image_url,
                "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
                "status": "available"
            })
            print(f"    [{len(items)}] {price or '?'} - {(title or 'Untitled')[:40]}")

        except Exception as e:
            continue

    print(f"  ✅ Extracted {len(items)} items")
    return items


def scrape_my_listings(db_path: str = "marketplace.db", limit: int = 50):
    """
    Main function: Get logged-in user's marketplace listings.

    Tries methods in order:
    1. Facebook Graph API (if FB_ACCESS_TOKEN env var set)
    2. Fast browser scraping (single page navigation)
    """
    # Try API first (future-proofing)
    api = get_facebook_api()
    if api.api_available:
        print("🔗 Using Facebook API...")
        user_info = api.get_user_info()
        items = api.get_my_listings(limit)
        if items:
            save_items_to_db(items, user_info, db_path)
            return user_info, items
        # API available but no items - fall through to scraping

    # Fallback to browser scraping
    return scrape_my_listings_fast(db_path, limit)


if __name__ == "__main__":
    user_info, items = scrape_my_listings()
    if user_info:
        print(f"\n✅ Found {len(items)} items for {user_info.get('fb_name', 'Unknown')}")

