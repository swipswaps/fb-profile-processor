# Facebook Profile Processor - Upgrade Plan & Rules Compliance

## Rules Analysis

### Critical Rules Applied

#### Rule 0 - Mandatory Workflow Pattern (META-RULE) 🔴
- **Status:** COMPLIANT
- **Actions:** BEFORE states saved to `/tmp/before_*.txt`
- **Evidence:** Terminal outputs captured

#### Rule 11 - SQLite Database Safety 🟠
- **Current Issues:**
  - ❌ No transaction handling for batch operations
  - ❌ Column names not reserved-word safe
  - ✅ Schema verification with PRAGMA
- **Fixes Required:**
  - Add `BEGIN TRANSACTION` / `COMMIT` wrappers
  - Prefix all columns with `fb_` for Graph API fields

#### Rule 12 - HTTP Request Safety 🟠
- **Current Status:**
  - ✅ Timeout values set (15 seconds default)
  - ✅ Rate limiting implemented (1 req/sec)
  - ✅ Separate error handling for connection/timeout/HTTP errors
  - ⚠️ Timeout hardcoded in some places
- **Improvements:** Make timeout configurable via environment variables

#### Rule 17 - Data Format Compatibility 🟠
- **Critical Issue:** Current schema NOT Facebook Graph API compatible
- **Impact:** Cannot migrate to official API without data restructuring
- **Solution:** Implement `schema_upgrade_v2.py`

#### Rule 25 - Logging Requirements 🟠
- **Current Status:**
  - ✅ `fb_profile_processor.py` - Proper logging module usage
  - ✅ `browser_enricher.py` - Proper logging module usage
  - ❌ `dashboard_integrated.py` - Imports logging but doesn't configure
- **Fix:** Add logging configuration to dashboard

#### Rule 27 - URL Transformation Accuracy 🔴
- **Current Status:** ✅ COMPLIANT
- **Evidence:** Regex pattern matching in `fb_profile_processor.py` lines 160-180

#### Rule 28 - Database Schema Compliance 🟠
- **Critical Issue:** Schema does NOT match Facebook Graph API specification
- **Current Schema:** Custom fields (`browser_profile_name`, `browser_profile_bio`)
- **Required Schema:** Graph API v24.0 standard fields (`name`, `first_name`, `last_name`, `bio`)

---

## Coding Techniques & Best Practices

### 1. **Context Managers for Database Operations**
```python
# BEFORE (risky)
conn = sqlite3.connect(db_file)
cur = conn.cursor()
cur.execute("INSERT ...")
conn.commit()
conn.close()

# AFTER (safe)
with sqlite3.connect(db_file) as conn:
    with conn:  # Auto-commit/rollback
        cur = conn.cursor()
        cur.execute("INSERT ...")
```

### 2. **Transaction Batching**
```python
# BEFORE (slow, no atomicity)
for url in urls:
    conn = sqlite3.connect(db)
    process_one(url)
    conn.commit()

# AFTER (fast, atomic)
with sqlite3.connect(db) as conn:
    conn.execute("BEGIN TRANSACTION")
    try:
        for url in urls:
            process_one(url, conn)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
```

### 3. **Dependency Injection for Testability**
```python
# BEFORE (hard to test)
def process_url(url):
    conn = sqlite3.connect('hardcoded.db')
    ...

# AFTER (testable)
def process_url(url, conn=None):
    if conn is None:
        conn = sqlite3.connect(get_db_path())
    ...
```

### 4. **Configuration via Environment Variables**
```python
import os

HTTP_TIMEOUT = int(os.getenv('FB_HTTP_TIMEOUT', '15'))
RATE_LIMIT = float(os.getenv('FB_RATE_LIMIT', '1.0'))
DB_PATH = os.getenv('FB_DB_PATH', 'facebook_profiles.db')
```

### 5. **Structured Logging**
```python
# BEFORE
print(f"Processing {url}")

# AFTER
logging.info("Processing URL", extra={
    'url': url,
    'profile_id': profile_id,
    'attempt': retry_count
})
```

### 6. **Type Hints for Clarity**
```python
from typing import Optional, Dict, List

def process_url(
    url: str, 
    db_path: str, 
    timeout: int = 15
) -> Dict[str, any]:
    """Process a single Facebook profile URL"""
    ...
```

---

## Database Schema Upgrade

### Current Schema Issues
1. **Non-standard field names** - Cannot map to Graph API
2. **Missing standard fields** - `first_name`, `last_name`, `email`, `gender`, `birthday`
3. **Flat structure** - Location should be structured (name + id)
4. **No versioning** - Cannot track schema changes

### New Graph API v24.0 Compatible Schema

**Core Identity Fields:**
- `fb_id` - User ID (Graph API: `id`)
- `fb_username` - Username (Graph API: `username`)
- `fb_name` - Full name (Graph API: `name`)
- `fb_first_name` - First name (Graph API: `first_name`)
- `fb_last_name` - Last name (Graph API: `last_name`)

**Contact & Demographics:**
- `fb_email` - Email (Graph API: `email`)
- `fb_gender` - Gender (Graph API: `gender`)
- `fb_birthday` - Birthday (Graph API: `birthday`)
- `fb_age_range_min/max` - Age range (Graph API: `age_range`)

**Location (Structured):**
- `fb_location_name` - Location name (Graph API: `location.name`)
- `fb_location_id` - Location ID (Graph API: `location.id`)
- `fb_hometown_name` - Hometown (Graph API: `hometown.name`)

**Media:**
- `fb_picture_url` - Profile picture (Graph API: `picture.data.url`)
- `fb_cover_source` - Cover photo (Graph API: `cover.source`)
- `local_picture_path` - Downloaded image path

**Migration Path:**
1. Run `schema_upgrade_v2.py --database <db_file>`
2. Old table backed up as `profiles_old_backup`
3. New table becomes active `profiles`
4. All existing data migrated with field mapping

---

## Testing Plan

### 1. Unit Tests
- Database operations (CRUD)
- URL transformation
- HTTP error handling
- Schema migration

### 2. Integration Tests
- End-to-end URL processing
- Browser enrichment workflow
- Export functionality

### 3. Performance Tests
- Batch processing (1000+ URLs)
- Database query performance
- Memory usage during enrichment

---

## Next Steps

1. ✅ Save BEFORE state
2. ⏳ Run schema migration
3. ⏳ Update code to use new schema
4. ⏳ Add transaction handling
5. ⏳ Configure logging in dashboard
6. ⏳ Add environment variable support
7. ⏳ Write tests
8. ⏳ Run full E2E test
9. ⏳ Deploy


