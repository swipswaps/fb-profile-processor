# AI Studio Prompt: Facebook Profile URL Processor (Production-Ready)

## Context & Constraints

You are building a **data processing pipeline**, NOT a browser automation tool.

**What this is:**
- HTTP client that fetches web pages
- HTML parser that extracts metadata
- SQLite database for structured storage
- Command-line tool with batch processing

**What this is NOT:**
- Browser automation (no Playwright, Selenium, Puppeteer)
- Chrome debugging or session management
- Web scraping of private/authenticated data
- Claude API integration for inference

**Critical User Requirement:**
> "No skipped steps, evading the user's rules or repeating mistakes, proceed"

This means:
- Follow specifications EXACTLY
- Don't add features not requested
- Don't skip error handling
- Make deterministic, auditable code

---

## Problem Statement

**Input:** Text file containing Facebook Marketplace profile URLs
```
https://www.facebook.com/marketplace/profile/100034319820077/?referralSurface=messenger_banner
https://www.facebook.com/marketplace/profile/100012345678/
```

**Output:** SQLite database with metadata extracted from each profile

**Process:**
1. Transform marketplace URLs → clean profile URLs
2. Fetch each URL via HTTP
3. Parse HTML for metadata (title, OpenGraph tags)
4. Store in database
5. Support resume, deduplication, exports

---

## Database Schema (EXACT SPECIFICATION)

```sql
CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_url TEXT NOT NULL UNIQUE,    -- Original URL from file
    resolved_url TEXT,                  -- Final URL after redirects
    http_status INTEGER,                -- HTTP status code (200, 404, etc)
    page_title TEXT,                    -- <title>Content</title>
    og_title TEXT,                      -- <meta property="og:title" content="...">
    og_description TEXT,                -- <meta property="og:description" content="...">
    fetched_at TEXT,                    -- Timestamp: YYYY-MM-DD HH:MM:SS
    error TEXT                          -- Error message if fetch failed
);

CREATE INDEX IF NOT EXISTS idx_input_url ON profiles(input_url);
```

**Key points:**
- `input_url` has UNIQUE constraint (prevents duplicates)
- `error` column stores failure reasons
- `fetched_at` uses readable format, not ISO microseconds
- Index on `input_url` for fast duplicate checking

---

## URL Transformation Algorithm

### Input Format
```
https://www.facebook.com/marketplace/profile/{NUMERIC_ID}/?query=params
```

### Output Format
```
https://www.facebook.com/{NUMERIC_ID}
```

### Regex Pattern
```python
import re
match = re.search(r'marketplace/profile/(\d+)', url)
if match:
    profile_id = match.group(1)
    clean_url = f'https://www.facebook.com/{profile_id}'
```

### Validation Rules
- Profile ID MUST be numeric only (digits 0-9)
- Non-marketplace URLs should be rejected
- Malformed URLs should be logged as errors

### Edge Cases to Handle
```python
# Valid
"https://www.facebook.com/marketplace/profile/123/?ref=x" → "https://www.facebook.com/123"

# Invalid - non-numeric ID
"https://www.facebook.com/marketplace/profile/abc123/" → REJECT

# Invalid - not marketplace
"https://www.facebook.com/john.doe" → REJECT

# Invalid - completely malformed
"not a url" → REJECT
```

---

## HTTP Fetching Requirements

### Request Configuration
```python
headers = {
    "User-Agent": "Mozilla/5.0 (compatible; profile-resolver/1.0)"
}
timeout = 15  # seconds
allow_redirects = True
```

### Retry Logic (CRITICAL)
```python
max_attempts = 3
base_delay = 2  # seconds

for attempt in range(max_attempts):
    try:
        response = fetch(url)
        if success:
            break
    except Exception as e:
        if attempt < max_attempts - 1:
            delay = base_delay * (2 ** attempt)  # Exponential backoff
            time.sleep(delay)
        else:
            log_error(e)
```

**Why exponential backoff?**
- First retry: 2 seconds
- Second retry: 4 seconds
- Prevents hammering servers on temporary failures

### Error Types to Handle
| Error Type | HTTP Status | Action |
|------------|-------------|--------|
| Success | 200 | Parse and store |
| Not Found | 404 | Store with error |
| Rate Limited | 429 | Back off, retry |
| Timeout | - | Retry with backoff |
| Network Error | - | Retry with backoff |
| Parse Error | 200 | Store partial data |

---

## HTML Metadata Extraction

### What to Extract
```html
<!-- Page Title -->
<title>John Doe | Facebook</title>

<!-- OpenGraph Metadata -->
<meta property="og:title" content="John Doe" />
<meta property="og:description" content="Lives in New York" />
```

### HTML Parser Implementation
```python
from html.parser import HTMLParser
from html import unescape

class MetaParser(HTMLParser):
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
            
            if prop == "og:title":
                self.og_title = unescape(content.strip())
            elif prop == "og:description":
                self.og_description = unescape(content.strip())
    
    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
            if self._title_content:
                self.title = unescape(''.join(self._title_content).strip())
    
    def handle_data(self, data):
        if self._in_title:
            self._title_content.append(data)
```

**Why this approach?**
- Handles nested tags: `<title><span>Name</span></title>`
- Decodes HTML entities: `John&#39;s` → `John's`
- Robust to malformed HTML

### Important Constraint
Facebook does NOT expose full profile data over unauthenticated HTTP. You can reliably extract:
- ✅ Page title
- ✅ OpenGraph title
- ✅ OpenGraph description
- ✅ HTTP status codes
- ❌ Follower counts (requires authentication)
- ❌ Friend lists (requires authentication)
- ❌ Full bio (often requires authentication)

**Do not pretend you can extract data that requires login.**

---

## Deduplication & Resume Logic

### Check Before Processing
```python
def url_exists(cursor, url):
    cursor.execute("SELECT id FROM profiles WHERE input_url = ?", (url,))
    return cursor.fetchone() is not None

# In main loop
if url_exists(cur, url):
    logging.info(f"Skipping already-processed: {url}")
    continue
```

### Why This Matters
- User may run script multiple times
- Prevents duplicate HTTP requests
- Saves time and respects rate limits
- Allows resume after interruption

### Resume Capability
The UNIQUE constraint on `input_url` provides automatic resume:
1. Script reads ALL URLs from file
2. Checks each against database
3. Processes only new/unprocessed URLs
4. Can be interrupted and re-run safely

---

## Command-Line Interface

### Required Arguments
```python
import argparse

parser = argparse.ArgumentParser(description='Facebook Profile URL Processor')
parser.add_argument('--input', '-i', default='links.txt',
                   help='Input file with URLs')
parser.add_argument('--output', '-o', default='facebook_profiles.db',
                   help='Output SQLite database')
parser.add_argument('--rate-limit', '-r', type=float, default=1.0,
                   help='Delay between requests (seconds)')
parser.add_argument('--timeout', '-t', type=int, default=15,
                   help='HTTP timeout (seconds)')
parser.add_argument('--verbose', '-v', action='store_true',
                   help='Enable verbose logging')
parser.add_argument('--log-file', default='processing.log',
                   help='Log file path')
args = parser.parse_args()
```

### Example Usage
```bash
# Default behavior
python3 fb_processor.py

# Custom files
python3 fb_processor.py --input urls.txt --output results.db

# Slower rate (2 seconds between requests)
python3 fb_processor.py --rate-limit 2.0

# Verbose output with custom log file
python3 fb_processor.py -v --log-file debug.log

# Longer timeout for slow connections
python3 fb_processor.py --timeout 30
```

---

## Logging Requirements

### Dual Output (Console + File)
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('processing.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
```

### Log Levels
- `DEBUG`: Detailed info (transformed URLs, HTML parsing details)
- `INFO`: Progress updates, success messages
- `WARNING`: Skipped URLs, retry attempts
- `ERROR`: Failed fetches, invalid URLs
- `CRITICAL`: Fatal errors

### Progress Indicators
```python
for i, url in enumerate(urls_to_process, 1):
    percent = (i / len(urls_to_process)) * 100
    logging.info(f"[{i}/{len(urls_to_process)}] ({percent:.1f}%) Processing: {url}")
```

**Output:**
```
[1/100] (1.0%) Processing: https://...
[2/100] (2.0%) Processing: https://...
...
[100/100] (100.0%) Processing: https://...
```

---

## Input File Format

### Specification
```
# Comments start with #
# Blank lines are ignored

https://www.facebook.com/marketplace/profile/100034319820077/?ref=banner
https://www.facebook.com/marketplace/profile/100012345678/

# Another section
https://www.facebook.com/marketplace/profile/999888777/
```

### Parsing Rules
- One URL per line
- UTF-8 encoding
- Lines starting with `#` are comments (ignored)
- Empty lines are ignored
- Non-HTTP lines are rejected with warning
- Trailing/leading whitespace is stripped

---

## Export Formats

### 1. JSON Export
```json
[
  {
    "id": 1,
    "input_url": "https://www.facebook.com/marketplace/profile/123/",
    "resolved_url": "https://www.facebook.com/123",
    "http_status": 200,
    "page_title": "John Doe",
    "og_title": "John Doe",
    "og_description": "Lives in NYC",
    "fetched_at": "2025-01-10 12:34:56",
    "error": null
  }
]
```

### 2. CSV Export
```csv
id,input_url,resolved_url,http_status,page_title,og_title,og_description,fetched_at,error
1,"https://www.facebook.com/marketplace/profile/123/","https://www.facebook.com/123",200,"John Doe","John Doe","Lives in NYC","2025-01-10 12:34:56",
```

**CSV Requirements:**
- Double quotes around all fields
- Escape internal quotes: `"` → `""`
- Include header row

### 3. SQL Dump Export
```sql
-- facebook_profiles_dump.sql
CREATE TABLE IF NOT EXISTS profiles (...);

BEGIN TRANSACTION;
INSERT INTO profiles (input_url, resolved_url, http_status, ...) VALUES ('https://...', 'https://...', 200, ...);
INSERT INTO profiles (input_url, resolved_url, http_status, ...) VALUES ('https://...', 'https://...', 404, ...);
COMMIT;
```

---

## Testing & Validation

### Test Input File (test_urls.txt)
```
# Valid marketplace URLs
https://www.facebook.com/marketplace/profile/100034319820077/?ref=test
https://www.facebook.com/marketplace/profile/123456789/

# Invalid - already clean
https://www.facebook.com/100034319820077

# Invalid - non-numeric ID
https://www.facebook.com/marketplace/profile/abc123/

# Invalid - not a URL
this is not a url

# Empty line follows

# Valid
https://www.facebook.com/marketplace/profile/999888777/
```

### Expected Results
| URL | Should | Reason |
|-----|--------|--------|
| marketplace/profile/100034319820077/ | ✅ Process | Valid format |
| marketplace/profile/123456789/ | ✅ Process | Valid format |
| /100034319820077 | ❌ Reject | Not marketplace URL |
| marketplace/profile/abc123/ | ❌ Reject | Non-numeric ID |
| "this is not a url" | ❌ Reject | Invalid format |
| marketplace/profile/999888777/ | ✅ Process | Valid format |

### Success Criteria
- All valid URLs transformed correctly
- Database created with correct schema
- Duplicates prevented by UNIQUE constraint
- Errors logged, not crashed
- Resume works after interruption
- Exports produce well-formed files

---

## Performance Specifications

### Small Dataset (100 URLs)
- **Time:** ~2 minutes (1 request/sec + overhead)
- **Memory:** <50MB
- **Disk:** <1MB database

### Medium Dataset (1,000 URLs)
- **Time:** ~20 minutes
- **Memory:** <100MB
- **Disk:** ~5MB database

### Large Dataset (10,000 URLs)
- **Time:** ~3 hours
- **Memory:** <200MB (streaming processing)
- **Disk:** ~50MB database

### Optimizations
- ✅ Streaming processing (don't load all into memory)
- ✅ Commit after each URL (no data loss on crash)
- ✅ Index on input_url (fast duplicate checks)
- ❌ Do NOT use batch processing (violates rate limiting)
- ❌ Do NOT parallelize (violates rate limiting)

---

## Rate Limiting & Ethics

### Requirements
```python
time.sleep(rate_limit)  # Default: 1.0 second
```

### Why This Matters
- Respects server resources
- Prevents IP bans
- Complies with terms of service
- Good internet citizenship

### HTTP 429 Handling
```python
if response.status_code == 429:
    retry_after = response.headers.get('Retry-After', 60)
    logging.warning(f"Rate limited. Waiting {retry_after}s...")
    time.sleep(int(retry_after))
    # Retry request
```

---

## Final Deliverables Checklist

### Minimum Viable Product (MVP)
- [ ] URL transformation with regex
- [ ] HTTP fetching with error handling
- [ ] HTML metadata parsing
- [ ] SQLite database with correct schema
- [ ] Basic logging to console
- [ ] Rate limiting (1 req/sec)
- [ ] At least one export format

### Production-Ready Version
- [ ] All MVP features PLUS:
- [ ] Command-line arguments
- [ ] Deduplication logic
- [ ] Resume capability
- [ ] Retry logic with exponential backoff
- [ ] Progress indicators (percentage)
- [ ] Dual logging (console + file)
- [ ] All three export formats (JSON, CSV, SQL)
- [ ] Comprehensive error handling
- [ ] Input file validation
- [ ] Graceful keyboard interrupt handling
- [ ] Final summary statistics

---

## Example Complete Output

```bash
$ python3 fb_processor.py --input urls.txt --verbose

2025-01-10 14:23:10 [INFO] Reading URLs from urls.txt
2025-01-10 14:23:10 [INFO] Found 5 URLs to process
2025-01-10 14:23:10 [INFO] Skipped 0 already-processed URLs
2025-01-10 14:23:10 [INFO] Processing 5 new URLs
2025-01-10 14:23:10 [INFO] [1/5] (20.0%) Processing: https://www.facebook.com/marketplace/profile/100034319820077/
2025-01-10 14:23:10 [DEBUG] Transformed to: https://www.facebook.com/100034319820077 (ID: 100034319820077)
2025-01-10 14:23:12 [INFO] Success: Status 200, Title: Facebook Profile
2025-01-10 14:23:13 [INFO] [2/5] (40.0%) Processing: https://www.facebook.com/marketplace/profile/123456789/
2025-01-10 14:23:13 [DEBUG] Transformed to: https://www.facebook.com/123456789 (ID: 123456789)
2025-01-10 14:23:14 [WARNING] Attempt 1 failed: Connection timeout. Retrying in 2s...
2025-01-10 14:23:18 [INFO] Success: Status 200, Title: John Doe
2025-01-10 14:23:19 [INFO] [3/5] (60.0%) Processing: https://www.facebook.com/100034319820077
2025-01-10 14:23:19 [WARNING] Invalid URL format (not a marketplace URL)
2025-01-10 14:23:19 [INFO] [4/5] (80.0%) Processing: https://www.facebook.com/marketplace/profile/abc123/
2025-01-10 14:23:19 [WARNING] Invalid URL format (not a marketplace URL)
2025-01-10 14:23:20 [INFO] [5/5] (100.0%) Processing: https://www.facebook.com/marketplace/profile/999888777/
2025-01-10 14:23:20 [DEBUG] Transformed to: https://www.facebook.com/999888777 (ID: 999888777)
2025-01-10 14:23:22 [ERROR] Failed: HTTP 404 Not Found
2025-01-10 14:23:22 [INFO] ============================================================
2025-01-10 14:23:22 [INFO] PROCESSING COMPLETE
2025-01-10 14:23:22 [INFO] Database: facebook_profiles.db
2025-01-10 14:23:22 [INFO] Total processed: 5
2025-01-10 14:23:22 [INFO] Successful: 2
2025-01-10 14:23:22 [INFO] Errors: 3
2025-01-10 14:23:22 [INFO] Success rate: 40.0%
2025-01-10 14:23:22 [INFO] ============================================================
2025-01-10 14:23:22 [INFO]
2025-01-10 14:23:22 [INFO] To view results:
2025-01-10 14:23:22 [INFO]   sqlite3 facebook_profiles.db
2025-01-10 14:23:22 [INFO]   SELECT * FROM profiles;
```

---

## Implementation Checklist

Before submitting code, verify:

**Architecture:**
- [ ] Uses `requests` library (or `urllib` fallback)
- [ ] Uses `sqlite3` for database
- [ ] Uses `html.parser.HTMLParser` for parsing
- [ ] Uses `argparse` for CLI
- [ ] Uses `logging` for output

**Database:**
- [ ] Schema matches specification EXACTLY
- [ ] UNIQUE constraint on `input_url`
- [ ] Index created for performance
- [ ] Commits after each insert (durability)

**URL Processing:**
- [ ] Regex correctly extracts numeric IDs
- [ ] Non-marketplace URLs rejected
- [ ] Malformed URLs logged as errors

**HTTP Fetching:**
- [ ] User-Agent header set
- [ ] 15-second timeout
- [ ] Follows redirects
- [ ] Retry logic with exponential backoff (3 attempts)

**HTML Parsing:**
- [ ] Extracts page title
- [ ] Extracts og:title
- [ ] Extracts og:description
- [ ] Handles HTML entities (unescape)

**Features:**
- [ ] Deduplication (skip existing URLs)
- [ ] Resume capability (automatic via UNIQUE)
- [ ] Progress indicators (percentage)
- [ ] Rate limiting (1 req/sec default)
- [ ] Graceful error handling
- [ ] Keyboard interrupt handling

**Logging:**
- [ ] Console output
- [ ] File output
- [ ] Proper log levels (DEBUG/INFO/WARN/ERROR)
- [ ] Final summary statistics

**Exports:**
- [ ] JSON export function
- [ ] CSV export function
- [ ] SQL export function

**CLI:**
- [ ] --input argument
- [ ] --output argument
- [ ] --rate-limit argument
- [ ] --timeout argument
- [ ] --verbose argument
- [ ] --log-file argument
- [ ] Help text with examples

---

## Common Mistakes to Avoid

### ❌ WRONG: Adding unrequested features
```python
# Don't add features not in spec
def download_profile_picture(url):
    ...
```

### ❌ WRONG: Pretending to get unavailable data
```python
# Don't claim you can get data that requires login
"follower_count": "Unable to access without authentication"
```

### ❌ WRONG: Poor error handling
```python
# Don't crash on errors
data = fetch_url(url)  # No try/except
```

### ❌ WRONG: No deduplication
```python
# Don't process duplicates
for url in urls:
    # Missing: if url_exists(url): continue
    process(url)
```

### ❌ WRONG: Weak retry logic
```python
# Don't retry without backoff
for attempt in range(3):
    try:
        result = fetch()
        break  # This always breaks on first attempt!
    except:
        pass
```

### ✅ CORRECT: Proper retry logic
```python
for attempt in range(3):
    try:
        result = fetch()
        if result.status_code == 200:
            break  # Success
    except Exception as e:
        if attempt < 2:
            time.sleep(2 ** attempt)  # Exponential backoff
        else:
            log_error(e)
```

---

## Summary

Build a production-ready HTTP client that:

1. **Transforms** marketplace URLs to clean format
2. **Fetches** pages with proper error handling and retries
3. **Extracts** metadata from HTML (title, OpenGraph)
4. **Stores** everything in SQLite with deduplication
5. **Exports** to JSON/CSV/SQL formats
6. **Logs** progress with percentages
7. **Respects** rate limits and ethics
8. **Resumes** after interruption

**Keep it simple, deterministic, and production-ready.**

No browser automation. No Claude API. No speculation about unavailable data. Just clean, working code that processes URLs reliably.
