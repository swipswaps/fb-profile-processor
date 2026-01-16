#!/usr/bin/env python3
"""
Enhanced Facebook Profile Enricher with Marketplace Data Extraction
Extracts: name, username, location, profile/cover images, join date, 
listings count, response rate, seller badges
"""

import re
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


def extract_text_by_xpath(driver, xpath: str, default: str = None) -> str:
    """
    Extract text from element matching XPath.
    
    Args:
        driver: Selenium WebDriver instance
        xpath: XPath selector
        default: Default value if not found
        
    Returns:
        Extracted text or default value
    """
    try:
        elements = driver.find_elements(By.XPATH, xpath)
        for elem in elements:
            text = elem.text.strip()
            if text:
                return text
        return default
    except Exception:
        return default


def extract_profile_picture(driver) -> str:
    """
    Extract profile picture URL from page.
    
    Strategy:
    1. Look for <img> tags with specific attributes
    2. Filter by src containing 'fbcdn.net' or 'facebook.com'
    3. Prefer larger images (higher resolution)
    
    Returns:
        Profile picture URL or None
    """
    try:
        # Find all images on page
        img_elements = driver.find_elements(By.TAG_NAME, "img")
        
        candidates = []
        for img in img_elements:
            src = img.get_attribute("src")
            if not src:
                continue
                
            # Filter for Facebook CDN images
            if "fbcdn.net" in src or "facebook.com" in src:
                # Skip small icons/thumbnails (usually <100px)
                width = img.get_attribute("width")
                height = img.get_attribute("height")
                
                # Calculate priority (prefer larger images)
                priority = 0
                if width and height:
                    try:
                        priority = int(width) * int(height)
                    except ValueError:
                        priority = 0
                
                candidates.append((priority, src))
        
        # Return highest priority (largest) image
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
            
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error extracting profile picture: {e}")
        return None


def extract_cover_photo(driver) -> str:
    """
    Extract cover photo URL from page.
    
    Strategy:
    1. Look for <img> tags in cover photo container
    2. Filter by src containing 'fbcdn.net'
    3. Prefer images with 'cover' in the URL
    
    Returns:
        Cover photo URL or None
    """
    try:
        # Find all images
        img_elements = driver.find_elements(By.TAG_NAME, "img")
        
        for img in img_elements:
            src = img.get_attribute("src")
            if not src:
                continue
                
            # Look for cover photo indicators
            if "fbcdn.net" in src and any(keyword in src.lower() for keyword in ["cover", "banner"]):
                return src
        
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error extracting cover photo: {e}")
        return None


def extract_join_date(driver) -> str:
    """
    Extract Facebook join date.
    
    Looks for text like:
    - "Joined Facebook in 2018"
    - "Joined May 2020"
    
    Returns:
        Join date text or None
    """
    try:
        # Search for "Joined Facebook" text
        xpath = "//*[contains(text(), 'Joined Facebook')]"
        text = extract_text_by_xpath(driver, xpath)
        
        if text:
            # Clean up text: "Joined Facebook in 2018" -> "2018"
            match = re.search(r'Joined Facebook in (\d{4})', text)
            if match:
                return match.group(1)
            
            # Alternative: "Joined May 2020"
            match = re.search(r'Joined (\w+ \d{4})', text)
            if match:
                return match.group(1)
            
            # Return full text if no pattern match
            return text
            
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error extracting join date: {e}")
        return None


def extract_active_listings_count(driver) -> int:
    """
    Extract active listings count.
    
    Looks for text like:
    - "1 active listing"
    - "5 active listings"
    
    Returns:
        Listings count as integer or None
    """
    try:
        xpath = "//*[contains(text(), 'active listing')]"
        text = extract_text_by_xpath(driver, xpath)
        
        if text:
            # Extract number: "5 active listings" -> 5
            match = re.search(r'(\d+)\s+active listing', text)
            if match:
                return int(match.group(1))
        
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error extracting listings count: {e}")
        return None


def extract_response_info(driver) -> tuple:
    """
    Extract response rate and response time.
    
    Looks for text like:
    - "Usually responds within 1 hour"
    - "Very responsive"
    - "Responds within a few hours"
    
    Returns:
        Tuple of (response_rate, response_time) or (None, None)
    """
    try:
        # Look for response-related text
        xpath = "//*[contains(text(), 'respond')]"
        elements = driver.find_elements(By.XPATH, xpath)
        
        response_rate = None
        response_time = None
        
        for elem in elements:
            text = elem.text.strip()
            
            if "Usually responds" in text:
                response_time = text  # "Usually responds within 1 hour"
            elif "responsive" in text.lower():
                response_rate = text  # "Very responsive"
        
        return response_rate, response_time
        
    except Exception as e:
        print(f"  ⚠️  Error extracting response info: {e}")
        return None, None


def extract_seller_badges(driver) -> str:
    """
    Extract seller badges.
    
    Looks for badges like:
    - "Recommended seller"
    - "Fast responder"
    - "Top seller"
    
    Returns:
        JSON array string of badges or None
    """
    try:
        badge_keywords = [
            "Recommended seller",
            "Fast responder",
            "Top seller",
            "Verified",
            "Trusted seller"
        ]
        
        badges = []
        
        for keyword in badge_keywords:
            xpath = f"//*[contains(text(), '{keyword}')]"
            if extract_text_by_xpath(driver, xpath):
                badges.append(keyword)
        
        if badges:
            return json.dumps(badges)
        
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error extracting seller badges: {e}")
        return None


def extract_location(driver) -> str:
    """
    Extract location/city from profile.
    
    Looks for text like:
    - "Lives in Largo, Florida"
    - "From Miami, FL"
    
    Returns:
        Location text or None
    """
    try:
        # Check for "Lives in" text
        xpath = "//*[contains(text(), 'Lives in')]"
        text = extract_text_by_xpath(driver, xpath)
        
        if text:
            # Clean up: "Lives in Largo, Florida" -> "Largo, Florida"
            match = re.search(r'Lives in (.+)', text)
            if match:
                return match.group(1)
            return text
        
        # Alternative: "From XYZ"
        xpath = "//*[contains(text(), 'From')]"
        text = extract_text_by_xpath(driver, xpath)
        
        if text:
            match = re.search(r'From (.+)', text)
            if match:
                return match.group(1)
            return text
        
        return None
        
    except Exception as e:
        print(f"  ⚠️  Error extracting location: {e}")
        return None


def enrich_profile(driver, profile_url: str) -> dict:
    """
    Navigate to Facebook Marketplace profile and extract all available data.
    
    Args:
        driver: Selenium WebDriver instance
        profile_url: Facebook marketplace profile URL
        
    Returns:
        Dictionary with extracted profile data
    """
    print(f"\n🔍 Enriching: {profile_url}")
    
    result = {
        "fb_name": None,
        "fb_username": None,
        "fb_link": None,
        "fb_location_name": None,
        "fb_picture_url": None,
        "fb_cover_url": None,
        "fb_join_date": None,
        "fb_active_listings_count": None,
        "fb_response_rate": None,
        "fb_response_time": None,
        "fb_seller_badges": None,
    }
    
    try:
        # Navigate to profile
        driver.get(profile_url)
        
        # Wait for page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Extract name from page title or h1
        try:
            title = driver.title
            if title:
                # Clean up title: "Olivia C. Adamson | Facebook" -> "Olivia C. Adamson"
                result["fb_name"] = title.split("|")[0].strip()
        except Exception:
            pass
        
        # Extract username from URL
        try:
            current_url = driver.current_url
            result["fb_link"] = current_url
            
            # Parse username from URL
            # https://www.facebook.com/olivia.c.adamson.2025
            match = re.search(r'facebook\.com/([^/?]+)', current_url)
            if match:
                username = match.group(1)
                if username not in ["marketplace", "profile"]:
                    result["fb_username"] = username
        except Exception:
            pass
        
        # Extract all marketplace fields
        result["fb_location_name"] = extract_location(driver)
        result["fb_picture_url"] = extract_profile_picture(driver)
        result["fb_cover_url"] = extract_cover_photo(driver)
        result["fb_join_date"] = extract_join_date(driver)
        result["fb_active_listings_count"] = extract_active_listings_count(driver)
        
        response_rate, response_time = extract_response_info(driver)
        result["fb_response_rate"] = response_rate
        result["fb_response_time"] = response_time
        
        result["fb_seller_badges"] = extract_seller_badges(driver)
        
        # Print summary
        print(f"  ✅ Name: {result['fb_name']}")
        print(f"  ✅ Username: {result['fb_username']}")
        print(f"  ✅ Location: {result['fb_location_name']}")
        print(f"  ✅ Profile Pic: {result['fb_picture_url'][:50] + '...' if result['fb_picture_url'] else None}")
        print(f"  ✅ Join Date: {result['fb_join_date']}")
        print(f"  ✅ Active Listings: {result['fb_active_listings_count']}")
        print(f"  ✅ Response Rate: {result['fb_response_rate']}")
        print(f"  ✅ Badges: {result['fb_seller_badges']}")
        
    except TimeoutException:
        print(f"  ❌ Timeout loading page")
    except Exception as e:
        print(f"  ❌ Error: {e}")
    
    return result


if __name__ == "__main__":
    print("Enhanced Facebook Profile Enricher")
    print("This module is meant to be imported, not run directly.")
    print("\nExample usage:")
    print("  from selenium_enricher_enhanced import enrich_profile")
    print("  data = enrich_profile(driver, 'https://www.facebook.com/marketplace/profile/...')")
