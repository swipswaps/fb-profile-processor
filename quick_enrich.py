#!/usr/bin/env python3
"""
Quick enrichment using simple HTTP requests
Extracts whatever data is publicly available
"""
import sqlite3
import requests
import time
import re
from html.parser import HTMLParser

class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()

def fetch_profile(fb_id):
    """Fetch profile and extract name from title"""
    url = f"https://www.facebook.com/{fb_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    try:
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)

        # Parse title
        parser = TitleParser()
        parser.feed(r.text)

        # Extract name from title (usually "Name | Facebook" or just "Name")
        name = None
        if parser.title:
            # Remove " | Facebook" suffix
            name = parser.title.replace(" | Facebook", "").strip()
            # If it's just "Facebook" or "Error", it's not a real name
            if name in ["Facebook", "Error", "Log In", "Sign Up"]:
                name = None

        # Try to extract username from final URL
        username = None
        if "facebook.com/" in r.url:
            parts = r.url.split("facebook.com/")[1].split("/")[0].split("?")[0]
            if parts and not parts.isdigit() and parts not in ["login", "home", "error"]:
                username = parts

        return {
            "fb_name": name,
            "fb_username": username,
            "fb_link": r.url,
            "http_status": r.status_code,
            "enrichment_status": "enriched" if name else "partial",
            "enrichment_method": "http"
        }

    except Exception as e:
        return {
            "enrichment_status": "failed",
            "enrichment_error": str(e),
            "http_status": None
        }

def main():
    db_path = "test_profiles.db"

    print("🔍 Quick Profile Enrichment")
    print("=" * 60)

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
        return

    print(f"📊 Found {len(profiles)} profiles to enrich\n")

    success_count = 0

    for i, (profile_id, fb_id, input_url) in enumerate(profiles, 1):
        print(f"[{i}/{len(profiles)}] Profile ID: {profile_id}, FB ID: {fb_id}")

        result = fetch_profile(fb_id)

        print(f"  Status: {result.get('enrichment_status', 'unknown')}")
        if result.get('fb_name'):
            print(f"  Name: {result['fb_name']}")
            success_count += 1
        if result.get('fb_username'):
            print(f"  Username: {result['fb_username']}")
        if result.get('enrichment_error'):
            print(f"  Error: {result['enrichment_error']}")

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

    conn.close()

    print("=" * 60)
    print(f"✅ Complete: {success_count}/{len(profiles)} profiles enriched with names")
    print()
    print("📊 Verify results:")
    print(f"   sqlite3 {db_path} \"SELECT id, fb_name, fb_username FROM profiles WHERE fb_name IS NOT NULL;\"")

if __name__ == "__main__":
    main()

