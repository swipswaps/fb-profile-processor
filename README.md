# Facebook Profile URL Processor

A production-ready Python tool that transforms Facebook Marketplace profile URLs, fetches metadata, and stores results in a SQLite database.

## Two-Stage Architecture

### Stage 1: HTTP Collection (`fb_profile_processor.py`)
Fast bulk URL collection using HTTP requests - no authentication required.

### Stage 2: Browser Enrichment (`browser_enricher.py`)
Resolves numeric IDs to usernames and extracts full profile data using Playwright.

## Features

### Stage 1 (HTTP Collection)
✅ **URL Transformation** - Converts marketplace URLs to clean profile format
✅ **HTTP Metadata Extraction** - Fetches page titles and OpenGraph tags
✅ **SQLite Storage** - Structured database with deduplication
✅ **Resume Capability** - Skip already-processed URLs
✅ **Retry Logic** - Exponential backoff for failed requests
✅ **Rate Limiting** - Configurable delay between requests (default: 1 req/sec)
✅ **Export Formats** - JSON, CSV, and SQL dump
✅ **Progress Tracking** - Real-time percentage indicators
✅ **Dual Logging** - Console + file output
✅ **Error Handling** - Comprehensive exception management

### Stage 2 (Browser Enrichment)
✅ **Profile Resolution** - Numeric ID → username URL (e.g., `100000563858165` → `kristi.sutphin.9`)
✅ **Full Profile Data** - Name, bio, location, followers, profile picture
✅ **Existing Session** - Connects to your logged-in Chrome (no new login needed)
✅ **Incremental Enrichment** - Process profiles in batches, resume anytime
✅ **Human-like Delays** - Random delays (2-4 seconds) to avoid detection

## 🌐 Live Demo

**Try the web interface:** [https://swipswaps.github.io/fb-profile-processor/](https://swipswaps.github.io/fb-profile-processor/)

The web interface provides instant URL transformation without any installation!

## Requirements

- Python 3.8 or higher
- `requests` library (optional for Stage 1, falls back to stdlib `urllib`)
- `playwright` library (required for Stage 2)

## Installation

```bash
# Clone the repository
git clone https://github.com/swipswaps/fb-profile-processor.git
cd fb-profile-processor

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for Stage 2)
playwright install chromium
```

## Usage

### Stage 1: HTTP Collection (Fast Bulk Processing)

```bash
# Process URLs from links.txt (default)
python3 fb_profile_processor.py

# Specify custom input file
python3 fb_profile_processor.py --input my_urls.txt

# Custom output database
python3 fb_profile_processor.py --output my_database.db

# Export results
python3 fb_profile_processor.py --export-json results.json --export-csv results.csv
```

### Stage 2: Browser Enrichment (Detailed Profile Data)

**Step 1: Launch Chrome with Remote Debugging**

```bash
# Close ALL Chrome windows first, then:

# Linux:
google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.config/google-chrome"

# macOS:
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome"

# Windows:
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%USERPROFILE%\AppData\Local\Google\Chrome\User Data"
```

**Step 2: Log into Facebook** in that Chrome window (normal login, stays logged in)

**Step 3: Run Browser Enrichment**

```bash
# Enrich all pending profiles
python3 browser_enricher.py --database test_profiles.db

# Limit to first 10 profiles (for testing)
python3 browser_enricher.py --database test_profiles.db --limit 10

# Custom delay between requests (default: 3 seconds)
python3 browser_enricher.py --database test_profiles.db --delay 5.0

# Verbose logging
python3 browser_enricher.py --database test_profiles.db --verbose
```

### Advanced Options

```bash
# Adjust rate limiting (2 seconds between requests)
python3 fb_profile_processor.py --rate-limit 2.0

# Increase timeout for slow connections
python3 fb_profile_processor.py --timeout 30

# Enable verbose logging
python3 fb_profile_processor.py --verbose

# Export results to JSON
python3 fb_profile_processor.py --export-json results.json

# Export results to CSV
python3 fb_profile_processor.py --export-csv results.csv

# Export database to SQL dump
python3 fb_profile_processor.py --export-sql dump.sql
```

### Complete Example

```bash
python3 fb_profile_processor.py \
  --input links.txt \
  --output profiles.db \
  --rate-limit 1.5 \
  --timeout 20 \
  --verbose \
  --export-json output.json \
  --log-file processing.log
```

## Input Format

Create a text file (e.g., `links.txt`) with one URL per line:

```
https://www.facebook.com/marketplace/profile/123456789/?ref=share
https://www.facebook.com/marketplace/profile/987654321/?param=value
# Comments are supported
https://www.facebook.com/marketplace/profile/555555555/
```

## Database Schema

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_url TEXT NOT NULL UNIQUE,
    resolved_url TEXT,
    http_status INTEGER,
    page_title TEXT,
    og_title TEXT,
    og_description TEXT,
    fetched_at TEXT,
    error TEXT
);
```

## Querying Results

```bash
# Open database
sqlite3 facebook_profiles.db

# View all profiles
SELECT * FROM profiles;

# View successful fetches only
SELECT input_url, page_title, og_title FROM profiles WHERE error IS NULL;

# View errors
SELECT input_url, error FROM profiles WHERE error IS NOT NULL;

# Count statistics
SELECT 
  COUNT(*) as total,
  SUM(CASE WHEN error IS NULL THEN 1 ELSE 0 END) as successful,
  SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as failed
FROM profiles;
```

## Architecture

### URL Transformation (Rule 27)
- Uses regex pattern: `r'facebook\.com/marketplace/profile/(\d+)'`
- Extracts profile ID and creates clean URL
- Validates before HTTP requests

### HTTP Safety (Rule 12)
- 15-second default timeout
- 1 req/sec rate limiting (configurable)
- 3 retry attempts with exponential backoff
- Proper error handling for connection/timeout/HTTP errors

### SQLite Safety (Rule 11)
- Schema matches specification exactly
- PRAGMA verification on initialization
- Transactions for data integrity
- Indexed for fast duplicate checking

### HTML Metadata Extraction (Rule 19)
- Parses OpenGraph tags (og:title, og:description)
- Extracts `<title>` tag
- Unescapes HTML entities
- Handles malformed HTML gracefully

### Logging (Rule 25)
- Uses Python `logging` module
- Dual output (console + file)
- Timestamps and log levels
- Progress indicators for batch operations

## Limitations

- **No Browser Automation** - Uses HTTP requests only (Rule 35)
- **Public Data Only** - No authentication or private profile access
- **Rate Limiting Required** - Respects ethical scraping practices
- **CORS in Browser** - React UI is prototype only; Python script is production solution

## 🚀 GitHub Pages Setup

To enable the web interface on GitHub Pages:

1. Go to repository **Settings** → **Pages**
2. Under **Source**, select:
   - Branch: `main`
   - Folder: `/docs`
3. Click **Save**
4. Wait 1-2 minutes for deployment
5. Access at: `https://swipswaps.github.io/fb-profile-processor/`

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please ensure:
- Python 3.8+ compatibility
- All tests pass
- Code follows project style
- Documentation updated

## Support

For issues or questions, please open a GitHub issue.

