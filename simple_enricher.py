#!/usr/bin/env python3
"""
Simple Facebook Profile Enricher
Uses Playwright to connect to existing Firefox/Chrome session
"""

import sqlite3
import sys
import time
from playwright.sync_api import sync_playwright

def enrich_profile(page, profile_id, fb_id):
    """Visit profile and extract visible data"""
    url = f"https://www.facebook.com/{fb_id}"
    
    try:
        print(f"  Visiting: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)  # Let page render
        
        # Extract name from page title or h1
        name = None
        try:
            title = page.title()
            if title and title != "Facebook" and "Error" not in title:
                name = title.split("|")[0].strip()
        except:
            pass
        
        # Try to get name from h1
        if not name:
            try:
                h1 = page.query_selector("h1")
                if h1:
                    name = h1.inner_text().strip()
            except:
                pass
        
        # Extract username from URL after redirect
        final_url = page.url
        username = None
        if "facebook.com/" in final_url:
            parts = final_url.split("facebook.com/")[1].split("/")[0].split("?")[0]
            if parts and not parts.isdigit():
                username = parts
        
        print(f"    Name: {name or 'Not found'}")
        print(f"    Username: {username or 'Not found'}")
        print(f"    Final URL: {final_url}")
        
        return {
            "fb_name": name,
            "fb_username": username,
            "fb_link": final_url,
            "enrichment_status": "enriched" if name else "partial",
            "enrichment_method": "playwright"
        }
        
    except Exception as e:
        print(f"    Error: {e}")
        return {
            "enrichment_status": "failed",
            "enrichment_error": str(e)
        }

def main():
    db_path = "test_profiles.db"
    
    print("🔍 Simple Facebook Profile Enricher")
    print("=" * 50)
    print()
    print("REQUIREMENTS:")
    print("  1. Firefox or Chrome must be open")
    print("  2. You must be logged into Facebook in that browser")
    print("  3. Keep browser open during enrichment")
    print()
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Get profiles to enrich
    cur.execute("""
        SELECT id, fb_id, input_url 
        FROM profiles 
        WHERE fb_id IS NOT NULL 
        AND (enrichment_status IS NULL OR enrichment_status = 'pending')
        LIMIT 10
    """)
    profiles = cur.fetchall()
    
    if not profiles:
        print("❌ No profiles to enrich")
        print("   All profiles already enriched or missing fb_id")
        return
    
    print(f"📊 Found {len(profiles)} profiles to enrich")
    print()
    
    # Ask user which browser
    print("Which browser are you using?")
    print("  1. Firefox (default)")
    print("  2. Chrome")
    choice = input("Enter 1 or 2 [1]: ").strip() or "1"
    
    browser_type = "firefox" if choice == "1" else "chromium"
    
    print()
    print(f"🌐 Connecting to {browser_type}...")
    print("   Make sure you're logged into Facebook!")
    print()
    
    with sync_playwright() as p:
        # Launch browser in headed mode (visible)
        if browser_type == "firefox":
            browser = p.firefox.launch(headless=False)
        else:
            browser = p.chromium.launch(headless=False)
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0"
        )
        page = context.new_page()
        
        # First, navigate to Facebook to check login
        print("🔐 Checking Facebook login...")
        page.goto("https://www.facebook.com", timeout=15000)
        time.sleep(3)
        
        if "login" in page.url.lower():
            print()
            print("❌ NOT LOGGED IN")
            print("   Please log into Facebook in the browser window that just opened")
            print("   Then press Enter to continue...")
            input()
        else:
            print("✅ Logged in!")
        
        print()
        print("🚀 Starting enrichment...")
        print()
        
        # Process each profile
        for i, (profile_id, fb_id, input_url) in enumerate(profiles, 1):
            print(f"[{i}/{len(profiles)}] Profile ID: {profile_id}, FB ID: {fb_id}")
            
            result = enrich_profile(page, profile_id, fb_id)
            
            # Update database
            update_fields = []
            update_values = []
            
            for key, value in result.items():
                if value is not None:
                    update_fields.append(f"{key} = ?")
                    update_values.append(value)
            
            if update_fields:
                update_values.append(profile_id)
                sql = f"UPDATE profiles SET {', '.join(update_fields)} WHERE id = ?"
                cur.execute(sql, update_values)
                conn.commit()
            
            # Rate limiting
            if i < len(profiles):
                time.sleep(2)
        
        browser.close()
    
    conn.close()
    
    print()
    print("=" * 50)
    print("✅ Enrichment complete!")
    print()
    print("📊 View results:")
    print(f"   sqlite3 {db_path} \"SELECT id, fb_name, fb_username FROM profiles WHERE fb_name IS NOT NULL;\"")

if __name__ == "__main__":
    main()

