# AI Studio Prompt: Facebook Profile URL Processor

## Objective
Create a production-ready tool that transforms Facebook Marketplace profile URLs, fetches actual HTTP responses, extracts metadata from HTML, and stores results in a SQLite database. This is NOT a browser automation task - it's HTTP-based metadata extraction.

## What You Are Building

A script/application that:
1. Reads a list of Facebook Marketplace profile URLs from a text file
2. Transforms URLs from `https://www.facebook.com/marketplace/profile/{ID}/?params...` to `https://www.facebook.com/{ID}`
3. Fetches each URL via HTTP requests
4. Extracts metadata from the HTML response (page title, OpenGraph tags)
5. Stores all data in a SQLite database with proper schema
6. Exports results in multiple formats (JSON, CSV, SQL)

## Critical Architecture Requirements

### What This Is
- HTTP client that fetches pages
- HTML parser that extracts metadata
- Database writer that stores structured data
- URL transformer using regex pattern matching

### What This Is NOT
- Browser automation (no Playwright, Puppeteer, Selenium)
- Chrome remote debugging
- Session/cookie management
- UI scraping or screenshot capture
- Claude API integration for "guessing" data

## Core Functionality

### 1. URL Transformation
```python
# Input format
https://www.facebook.com/marketplace/profile/100034319820077/?referralSurface=messenger_banner&referralCode=4

# Output format
https://www.facebook.com/100034319820077

# Pattern to extract
marketplace/profile/(\d+)
```

**Implementation requirements:**
- Use regex to extract numeric profile ID
- Validate that ID is purely numeric
- Handle malformed URLs gracefully
- Skip non-marketplace URLs

### 2. HTTP Fetching & Metadata Extraction

**Fetch requirements:**
- Use standard HTTP GET requests
- Set User-Agent header: `Mozilla/5.0 (compatible; profile-resolver/1.0)`
- Follow redirects (allow_redirects=True)
- Timeout: 15 seconds
- Handle network errors gracefully

**Metadata to extract from HTML:**
```html
<!-- Page Title -->
<title>Page Title Here</title>

<!-- OpenGraph Title -->
<meta property="og:title" content="Profile Name" />

<!-- OpenGraph Description -->
<meta property="og:description" content="Bio or description" />
```

**Important constraint:**
Facebook does NOT expose full profile data over unauthenticated HTTP. What you can reliably get:
- Final resolved URL (after redirects)
- HTTP status code
- Page title (sometimes)
- OpenGraph metadata (when present)
- You CANNOT reliably get: follower counts, friend lists, detailed bio, profile pictures

### 3. Database Schema

**SQLite table structure:**
```sql
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_url TEXT NOT NULL,           -- Original marketplace URL
    clean_url TEXT,                     -- Transformed clean URL
    profile_id TEXT,                    -- Extracted numeric ID
    resolved_url TEXT,                  -- Final URL after redirects
    http_status INTEGER,                -- HTTP status code (200, 404, etc)
    page_title TEXT,                    -- <title> tag content
    og_title TEXT,                      -- OpenGraph title
    og_description TEXT,                -- OpenGraph description
    fetched_at TEXT,                    -- ISO timestamp
    error TEXT                          -- Error message if fetch failed
);
```

### 4. Processing Flow

```
1. Read links.txt file
2. For each URL:
   a. Transform marketplace URL → clean URL
   b. Extract profile ID
   c. Fetch via HTTP GET request
   d. Parse HTML for metadata
   e. Insert into database
   f. Wait 1 second (rate limiting)
3. Close database connection
4. Report results
```

## Implementation Options

### Option A: Python Script (Recommended)

**Dependencies:**
- `requests` library (or stdlib `urllib` as fallback)
- `sqlite3` (built-in)
- `html.parser` (built-in)

**Key features:**
- Minimal dependencies
- Deterministic execution
- Real database output
- No browser required
- Production-ready error handling

**Example structure:**
```python
#!/usr/bin/env python3

import sqlite3
import requests
import time
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

# Config
INPUT_FILE = "links.txt"
DB_FILE = "facebook_profiles.db"
REQUEST_TIMEOUT = 15

# HTML Parser class
class MetaParser(HTMLParser):
    # Extract title and og: tags
    pass

# Database functions
def init_db():
    # Create table if not exists
    pass

def transform_url(url):
    # Regex to transform URL
    pass

def fetch_profile(url):
    # HTTP GET + parse HTML
    pass

def main():
    # Main processing loop
    pass
```

### Option B: React Application (Limited by CORS)

**Important limitation:** Browser-based JavaScript CANNOT directly fetch Facebook URLs due to CORS (Cross-Origin Resource Sharing) restrictions. A React app can:
- Demonstrate the UI/UX
- Show the architecture
- Handle file uploads and exports
- But CANNOT actually fetch Facebook pages

**Use case:** UI prototype or client-side data management, but server-side fetching required for production.

## Error Handling Requirements

### Network Errors
- Retry logic: 3 attempts with 2-second delays
- Timeout handling: Fail gracefully after 15 seconds
- Log error messages to database

### Data Validation
- Verify profile IDs are numeric only
- Check for duplicate URLs before processing
- Validate HTTP status codes (200, 301, 404, etc.)

### Edge Cases
- Non-existent profiles (404 errors)
- Rate limiting (429 errors)
- Malformed HTML
- Missing metadata tags
- Empty responses

## Output Formats

### 1. SQLite Database (Primary)
- File: `facebook_profiles.db`
- Queryable with: `sqlite3 facebook_profiles.db`
- Supports incremental updates

### 2. JSON Export
```json
[
  {
    "profile_id": "100034319820077",
    "clean_url": "https://www.facebook.com/100034319820077",
    "resolved_url": "https://www.facebook.com/...",
    "http_status": 200,
    "page_title": "...",
    "og_title": "...",
    "og_description": "...",
    "fetched_at": "2025-01-10T12:00:00Z"
  }
]
```

### 3. CSV Export
```csv
Profile ID,Clean URL,Resolved URL,HTTP Status,Page Title,OG Title,OG Description,Fetched At
100034319820077,https://www.facebook.com/100034319820077,...,200,...,...,...,2025-01-10T12:00:00Z
```

### 4. SQL Dump
```sql
INSERT INTO profiles (input_url, clean_url, profile_id, ...) VALUES (...);
INSERT INTO profiles (input_url, clean_url, profile_id, ...) VALUES (...);
```

## Testing & Validation

### Test cases to handle:
1. Valid marketplace URL with query parameters
2. Already-clean profile URL
3. Non-marketplace Facebook URL
4. Completely invalid URL
5. Non-existent profile (404)
6. Duplicate URLs in input file
7. Empty input file
8. Network timeout scenario

### Success criteria:
- All valid URLs are transformed correctly
- Database schema matches specification
- HTTP errors are logged, not crashed
- Rate limiting prevents overwhelming servers
- Output files are well-formatted
- No data loss on interruption

## Rate Limiting & Ethics

**Requirements:**
- 1 request per second minimum delay
- Polite User-Agent string
- Respect HTTP status codes (429 = back off)
- No attempt to bypass authentication
- No circumvention of rate limits
- Only extract publicly visible metadata

## Performance Considerations

### For 100 URLs:
- Expected time: ~2 minutes (1 request/sec + processing)
- Memory usage: Minimal (streaming processing)
- Disk space: <1MB for database

### For 1000+ URLs:
- Consider batch processing
- Add progress indicators
- Implement checkpoint/resume capability
- Log failures for retry

## Deliverables

### Minimum Viable Product:
1. Working script that processes URLs
2. SQLite database with correct schema
3. Basic error handling
4. At least one export format (JSON or CSV)

### Production-Ready Version:
1. All of the above PLUS:
2. Comprehensive error handling
3. Progress indicators
4. Resume capability after interruption
5. Multiple export formats
6. Deduplication logic
7. Detailed logging
8. Command-line arguments for configuration

## Example Usage

```bash
# Setup
echo "https://www.facebook.com/marketplace/profile/100034319820077/?ref=banner" > links.txt
echo "https://www.facebook.com/marketplace/profile/100012345678/" >> links.txt

# Run
python3 fb_links_to_db.py

# Output
[INFO] Found 2 URLs in links.txt
[INFO] Processing 1/2: https://www.facebook.com/marketplace/profile/100034319820077/?ref=banner
[INFO] Transformed to: https://www.facebook.com/100034319820077 (ID: 100034319820077)
[SUCCESS] Status: 200, Title: Facebook Profile
[INFO] Processing 2/2: https://www.facebook.com/marketplace/profile/100012345678/
[INFO] Transformed to: https://www.facebook.com/100012345678 (ID: 100012345678)
[ERROR] Connection timeout
[SUCCESS] Database written to facebook_profiles.db

# Query results
sqlite3 facebook_profiles.db "SELECT profile_id, http_status, page_title FROM profiles;"
```

## What NOT to Include

❌ Browser automation (Playwright, Selenium, Puppeteer)
❌ Chrome remote debugging
❌ Cookie/session management
❌ Login workflows
❌ Claude API calls to "guess" data
❌ Web scraping beyond public metadata
❌ Attempts to bypass authentication
❌ Complex JavaScript rendering
❌ Screenshot capture
❌ Profile picture downloading (out of scope)

## Summary

Build a straightforward HTTP client that:
1. Transforms URLs with regex
2. Fetches pages with standard HTTP requests
3. Extracts metadata from HTML
4. Stores everything in SQLite
5. Exports to multiple formats
6. Handles errors gracefully
7. Respects rate limits

This is a data processing pipeline, not a browser automation task. Keep it simple, deterministic, and production-ready.
