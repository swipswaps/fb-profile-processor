# Facebook Profile URL Processor

A production-ready Python tool that transforms Facebook Marketplace profile URLs, fetches metadata via HTTP requests, and stores results in a SQLite database.

## Features

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

## Requirements

- Python 3.8 or higher
- `requests` library (optional, falls back to stdlib `urllib`)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/fb-profile-processor.git
cd fb-profile-processor

# Install dependencies (optional but recommended)
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
# Process URLs from links.txt (default)
python3 fb_profile_processor.py

# Specify custom input file
python3 fb_profile_processor.py --input my_urls.txt

# Custom output database
python3 fb_profile_processor.py --output my_database.db
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

