#!/usr/bin/env python3
"""
Facebook Profile URL Processor - Production Version
Transforms Marketplace URLs, fetches metadata, stores in SQLite database

FEATURES:
- Deduplication (skip already-processed URLs)
- Resume capability (process only pending URLs)
- Proper retry logic with exponential backoff
- Command-line arguments
- Progress indicators with percentage
- File + console logging
- Comprehensive error handling
"""

import sqlite3
import time
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser
from html import unescape

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error


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
        self._title_content = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "title":
            self._in_title = True
            self._title_content = []

        if tag == "meta":
            prop = attrs.get("property", "")
            content = attrs.get("content", "")

            if prop == "og:title" and content:
                self.og_title = unescape(content.strip())
            elif prop == "og:description" and content:
                self.og_description = unescape(content.strip())

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            if self._title_content and not self.title:
                self.title = unescape(''.join(self._title_content).strip())

    def handle_data(self, data):
        if self._in_title:
            self._title_content.append(data)


# ======================
# DATABASE
# ======================

def init_db(db_file):
    """Initialize SQLite database with profiles table"""
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    # Create table matching EXACT spec from requirements
    cur.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_url TEXT NOT NULL UNIQUE,
            resolved_url TEXT,
            http_status INTEGER,
            page_title TEXT,
            og_title TEXT,
            og_description TEXT,
            fetched_at TEXT,
            error TEXT
        )
    """)

    # Create index for faster duplicate checking
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_input_url 
        ON profiles(input_url)
    """)

    conn.commit()
    return conn


def url_exists(cur, url):
    """Check if URL already processed"""
    cur.execute("SELECT id FROM profiles WHERE input_url = ?", (url,))
    return cur.fetchone() is not None


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

def fetch_profile(url, timeout=15):
    """Fetch URL and extract metadata with retry logic"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; profile-resolver/1.0)"
    }

    max_attempts = 3
    base_delay = 2  # seconds

    for attempt in range(max_attempts):
        try:
            if HAS_REQUESTS:
                r = requests.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    allow_redirects=True
                )
                html_content = r.text
                resolved_url = r.url
                http_status = r.status_code
            else:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    html_content = response.read().decode('utf-8', errors='ignore')
                    resolved_url = response.geturl()
                    http_status = response.getcode()

            # Parse HTML metadata
            parser = MetaParser()
            try:
                parser.feed(html_content)
            except Exception as parse_error:
                logging.warning(f"HTML parsing error: {parse_error}")

            return {
                "resolved_url": resolved_url,
                "http_status": http_status,
                "page_title": parser.title,
                "og_title": parser.og_title,
                "og_description": parser.og_description,
                "fetched_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                "error": None
            }

        except Exception as e:
            error_msg = str(e)

            # Check if we should retry
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logging.warning(f"Attempt {attempt + 1} failed: {error_msg}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logging.error(f"All {max_attempts} attempts failed: {error_msg}")
                return {
                    "resolved_url": None,
                    "http_status": None,
                    "page_title": None,
                    "og_title": None,
                    "og_description": None,
                    "fetched_at": datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                    "error": error_msg
                }


# ======================
# MAIN
# ======================

def main():
    """Main processing loop"""
    # Parse arguments
    parser = argparse.ArgumentParser(
        description='Facebook Profile URL Processor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use defaults
  %(prog)s --input urls.txt --output db.db   # Custom files
  %(prog)s --rate-limit 2.0                   # 2 second delay
  %(prog)s --timeout 30                       # 30 second timeout
        """
    )
    parser.add_argument('--input', '-i', 
                       default='links.txt',
                       help='Input file with URLs (default: links.txt)')
    parser.add_argument('--output', '-o',
                       default='facebook_profiles.db',
                       help='Output SQLite database (default: facebook_profiles.db)')
    parser.add_argument('--rate-limit', '-r',
                       type=float,
                       default=1.0,
                       help='Delay between requests in seconds (default: 1.0)')
    parser.add_argument('--timeout', '-t',
                       type=int,
                       default=15,
                       help='HTTP request timeout in seconds (default: 15)')
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--log-file',
                       default='processing.log',
                       help='Log file path (default: processing.log)')

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(args.log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Validate input file
    input_file = Path(args.input)
    if not input_file.exists():
        logging.error(f"Input file not found: {input_file}")
        sys.exit(1)

    # Read URLs from file
    logging.info(f"Reading URLs from {input_file}")
    urls = []
    with open(input_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            if line.startswith('http'):
                urls.append(line)
            else:
                logging.warning(f"Line {line_num}: Invalid URL format, skipping: {line}")

    if not urls:
        logging.error("No valid URLs found in input file")
        sys.exit(1)

    logging.info(f"Found {len(urls)} URLs to process")

    # Initialize database
    db_file = Path(args.output)
    conn = init_db(db_file)
    cur = conn.cursor()

    # Check for duplicates and filter
    urls_to_process = []
    skipped = 0
    for url in urls:
        if url_exists(cur, url):
            logging.debug(f"Skipping already-processed URL: {url}")
            skipped += 1
        else:
            urls_to_process.append(url)

    if skipped > 0:
        logging.info(f"Skipped {skipped} already-processed URLs")

    if not urls_to_process:
        logging.info("No new URLs to process")
        conn.close()
        return

    logging.info(f"Processing {len(urls_to_process)} new URLs")

    # Process each URL
    success_count = 0
    error_count = 0

    for i, url in enumerate(urls_to_process, 1):
        percent = (i / len(urls_to_process)) * 100
        logging.info(f"[{i}/{len(urls_to_process)}] ({percent:.1f}%) Processing: {url}")

        # Transform URL
        transformed = transform_url(url)

        if not transformed['valid']:
            logging.warning(f"Invalid URL format (not a marketplace URL): {url}")
            # Store as error
            cur.execute("""
                INSERT INTO profiles (
                    input_url, resolved_url, http_status,
                    page_title, og_title, og_description,
                    fetched_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url, None, None, None, None, None,
                datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
                'Invalid URL format: not a marketplace profile URL'
            ))
            conn.commit()
            error_count += 1
            continue

        clean_url = transformed['clean']
        profile_id = transformed['id']

        logging.debug(f"Transformed to: {clean_url} (ID: {profile_id})")

        # Fetch profile data
        data = fetch_profile(clean_url, timeout=args.timeout)

        # Store in database
        cur.execute("""
            INSERT INTO profiles (
                input_url,
                resolved_url,
                http_status,
                page_title,
                og_title,
                og_description,
                fetched_at,
                error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url,
            data["resolved_url"],
            data["http_status"],
            data["page_title"],
            data["og_title"],
            data["og_description"],
            data["fetched_at"],
            data["error"]
        ))

        conn.commit()

        # Log results
        if data["error"]:
            logging.error(f"Failed: {data['error']}")
            error_count += 1
        else:
            logging.info(f"Success: Status {data['http_status']}, Title: {data.get('page_title', 'N/A')}")
            success_count += 1

        # Rate limiting
        if i < len(urls_to_process):
            time.sleep(args.rate_limit)

    conn.close()

    # Final summary
    logging.info("=" * 60)
    logging.info("PROCESSING COMPLETE")
    logging.info(f"Database: {db_file}")
    logging.info(f"Total processed: {len(urls_to_process)}")
    logging.info(f"Successful: {success_count}")
    logging.info(f"Errors: {error_count}")
    logging.info(f"Success rate: {(success_count / len(urls_to_process) * 100):.1f}%")
    logging.info("=" * 60)
    logging.info("\nTo view results:")
    logging.info(f"  sqlite3 {db_file}")
    logging.info("  SELECT * FROM profiles;")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.exception("Fatal error")
        sys.exit(1)
