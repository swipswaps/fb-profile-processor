#!/usr/bin/env python3
"""
Facebook Profile URL Processor
Transforms Marketplace URLs, fetches metadata, stores in SQLite database
"""

import sqlite3
import time
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

# ======================
# CONFIG
# ======================

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "links.txt"
DB_FILE = BASE_DIR / "facebook_profiles.db"
REQUEST_TIMEOUT = 15


# ======================
# HTML METADATA PARSER
# ======================

class MetaParser(HTMLParser):
    """Parse HTML to extract page title and OpenGraph metadata"""
    def __init__(self):
        super().__init__()
        self.title = None
        self.og_title = None
        self.og_description = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self._in_title = True

        if tag == "meta":
            if attrs.get("property") == "og:title":
                self.og_title = attrs.get("content")
            if attrs.get("property") == "og:description":
                self.og_description = attrs.get("content")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


# ======================
# DATABASE
# ======================

def init_db():
    """Initialize SQLite database with profiles table"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_url TEXT NOT NULL,
            clean_url TEXT,
            profile_id TEXT,
            resolved_url TEXT,
            http_status INTEGER,
            page_title TEXT,
            og_title TEXT,
            og_description TEXT,
            fetched_at TEXT,
            error TEXT
        )
    """)
    conn.commit()
    return conn


# ======================
# URL TRANSFORMATION
# ======================

def transform_url(url):
    """Transform marketplace URL to clean profile URL"""
    import re
    match = re.search(r'marketplace/profile/(\d+)', url)
    if match:
        profile_id = match.group(1)
        return {
            'clean': f'https://www.facebook.com/{profile_id}',
            'id': profile_id,
            'valid': True
        }
    return {'clean': None, 'id': None, 'valid': False}


# ======================
# FETCH + RESOLVE
# ======================

def fetch_profile(url):
    """Fetch URL and extract metadata"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; profile-resolver/1.0)"
    }

    try:
        if HAS_REQUESTS:
            # Use requests library if available
            r = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )
            html_content = r.text
            resolved_url = r.url
            http_status = r.status_code
        else:
            # Fallback to urllib
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                html_content = response.read().decode('utf-8')
                resolved_url = response.geturl()
                http_status = response.getcode()

    except Exception as e:
        return {
            "input_url": url,
            "resolved_url": None,
            "http_status": None,
            "page_title": None,
            "og_title": None,
            "og_description": None,
            "error": str(e)
        }

    # Parse HTML metadata
    parser = MetaParser()
    try:
        parser.feed(html_content)
    except Exception:
        pass

    return {
        "input_url": url,
        "resolved_url": resolved_url,
        "http_status": http_status,
        "page_title": parser.title,
        "og_title": parser.og_title,
        "og_description": parser.og_description,
        "fetched_at": datetime.utcnow().isoformat(),
        "error": None
    }


# ======================
# MAIN
# ======================

def main():
    """Main processing loop"""
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    # Read URLs from file
    urls = [l.strip() for l in INPUT_FILE.read_text().splitlines() if l.strip()]

    print(f"[INFO] Found {len(urls)} URLs in {INPUT_FILE}")

    # Initialize database
    conn = init_db()
    cur = conn.cursor()

    # Process each URL
    for i, url in enumerate(urls, 1):
        print(f"[INFO] Processing {i}/{len(urls)}: {url}")

        # Transform URL
        transformed = transform_url(url)

        if not transformed['valid']:
            print(f"[WARN] Invalid URL format, skipping: {url}")
            continue

        clean_url = transformed['clean']
        profile_id = transformed['id']

        print(f"[INFO] Transformed to: {clean_url} (ID: {profile_id})")

        # Fetch profile data
        data = fetch_profile(clean_url)

        # Store in database
        cur.execute("""
            INSERT INTO profiles (
                input_url,
                clean_url,
                profile_id,
                resolved_url,
                http_status,
                page_title,
                og_title,
                og_description,
                fetched_at,
                error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            clean_url,
            profile_id,
            data.get("resolved_url"),
            data.get("http_status"),
            data.get("page_title"),
            data.get("og_title"),
            data.get("og_description"),
            data.get("fetched_at"),
            data.get("error")
        ))

        conn.commit()

        # Log results
        if data.get("error"):
            print(f"[ERROR] {data['error']}")
        else:
            print(f"[SUCCESS] Status: {data['http_status']}, Title: {data.get('page_title', 'N/A')}")

        # Rate limiting: 1 request per second
        if i < len(urls):
            time.sleep(1)

    conn.close()
    print(f"\n[SUCCESS] Database written to {DB_FILE}")
    print(f"[INFO] Processed {len(urls)} URLs")
    print(f"\nTo view results:")
    print(f"  sqlite3 {DB_FILE}")
    print(f"  .tables")
    print(f"  SELECT * FROM profiles;")


if __name__ == "__main__":
    main()
