# How to Get Actual User Data

**Problem:** Database has profile IDs but NO names, usernames, locations, or bios.  
**Solution:** Run browser enrichment to fetch real Facebook profile data.

---

## QUICK START (3 Steps)

### Step 1: Start Chrome with Debugging
```bash
cd claude
./start_chrome_debug.sh
```

**What this does:**
- Launches Chrome with remote debugging enabled
- Opens Facebook login page
- Keeps debugging port 9222 active

**You will see:**
```
✅ Chrome started (PID: 12345)
✅ Debugging port: 9222
✅ Chrome debugging port is active

📋 Next steps:
  1. Log into Facebook in the Chrome window
  2. Run: python3 browser_enricher.py --database test_profiles.db
```

---

### Step 2: Log Into Facebook

1. Chrome window opens automatically
2. Go to facebook.com (if not already there)
3. **Log in with your Facebook account**
4. **Keep this Chrome window open**

**Important:** Don't close Chrome! The enrichment script needs it running.

---

### Step 3: Run Enrichment Script
```bash
cd claude
python3 browser_enricher.py --database test_profiles.db --limit 10
```

**What this does:**
- Connects to your logged-in Chrome session
- Visits each profile URL in database
- Extracts real user data:
  - ✅ Real names (not just IDs)
  - ✅ Usernames (vanity URLs)
  - ✅ Locations
  - ✅ Bios
  - ✅ Join dates
  - ✅ Profile pictures
- Updates database with actual data

**You will see:**
```
✓ Connected to Chrome session
Processing profile 1/7: 100010505562305
  ✓ Name: Kyle Young
  ✓ Username: kyle.young.123
  ✓ Location: Gilbert, Arizona
  ✓ Bio: Software engineer...
Processing profile 2/7: 100001669012324
  ✓ Name: Sarah Johnson
  ...
✅ Enrichment complete: 7 profiles updated
```

---

## Verify Data

### Check Database
```bash
cd claude
sqlite3 test_profiles.db << 'EOF'
.mode column
.headers on
SELECT id, fb_id, fb_name, fb_username, fb_location_name 
FROM profiles 
LIMIT 10;
EOF
```

**Expected output:**
```
id  fb_id              fb_name         fb_username      fb_location_name
1   100010505562305    Kyle Young      kyle.young.123   Gilbert, Arizona
2   100001669012324    Sarah Johnson   sarah.j.456      Phoenix, Arizona
```

**NOT this (empty data):**
```
id  fb_id              fb_name  fb_username  fb_location_name
1   100010505562305                          
2   100001669012324                          
```

---

### View in Dashboard

1. Open dashboard: http://localhost:8501
2. Go to "View Data" tab
3. **You should now see:**
   - ✅ Real names in `fb_name` column
   - ✅ Usernames in `fb_username` column
   - ✅ Actual data (not NULL)

4. Go to "Edit Data" tab
5. Select a profile
6. **You should see:**
   - ✅ Name: "Kyle Young" (not empty)
   - ✅ Username: "kyle.young.123" (not empty)
   - ✅ Location: "Gilbert, Arizona" (not empty)
   - ✅ Bio: "..." (actual bio text)

---

## Troubleshooting

### Problem: "Failed to connect to Chrome"
```
✗ Failed to connect to Chrome: connect ECONNREFUSED
```

**Solution:**
```bash
# Check if Chrome is running with debugging
curl http://localhost:9222/json/version

# If no response, start Chrome:
./start_chrome_debug.sh
```

---

### Problem: "Not logged into Facebook"
```
Error: Facebook login required
```

**Solution:**
1. Look at the Chrome window that opened
2. Log into Facebook
3. Keep Chrome window open
4. Run enrichment script again

---

### Problem: "No data extracted"
```
✓ Visited profile but extracted: Name=None, Username=None
```

**Possible causes:**
1. **Profile is private** - Can't access without being friends
2. **Facebook changed HTML** - Selectors need updating
3. **Rate limited** - Facebook blocking automated access

**Solutions:**
- For private profiles: Can only get limited data
- For HTML changes: Update selectors in `browser_enricher.py`
- For rate limiting: Add delays, use `--rate-limit 5` flag

---

### Problem: Playwright not installed
```
ModuleNotFoundError: No module named 'playwright'
```

**Solution:**
```bash
pip install playwright
playwright install chromium
```

---

## Advanced Options

### Enrich specific profiles
```bash
# Only enrich profiles with NULL names
python3 browser_enricher.py --database test_profiles.db --pending-only

# Enrich first 5 profiles
python3 browser_enricher.py --database test_profiles.db --limit 5

# Add delays between requests (slower but safer)
python3 browser_enricher.py --database test_profiles.db --rate-limit 5
```

### Re-enrich all profiles
```bash
# Force re-fetch even if already enriched
python3 browser_enricher.py --database test_profiles.db --force
```

---

## What Data Gets Extracted

### From Profile Page
- ✅ `fb_name` - Full name (e.g., "Kyle Young")
- ✅ `fb_username` - Vanity URL (e.g., "kyle.young.123")
- ✅ `fb_first_name` - First name
- ✅ `fb_last_name` - Last name
- ✅ `fb_bio` - About/bio text
- ✅ `fb_location_name` - Current city
- ✅ `fb_hometown_name` - Hometown
- ✅ `fb_website` - Website URL
- ✅ `fb_gender` - Gender (if public)
- ✅ `fb_relationship_status` - Relationship status

### From URL Resolution
- ✅ `fb_profile_url` - Numeric URL (facebook.com/100...)
- ✅ `fb_vanity_url` - Vanity URL (facebook.com/john.doe)
- ✅ `fb_link` - Canonical profile link

### Metadata
- ✅ `enrichment_status` - "enriched", "failed", "pending"
- ✅ `enrichment_method` - "browser"
- ✅ `enriched_at` - Timestamp
- ✅ `enrichment_error` - Error message if failed

---

## Expected Timeline

- **Step 1 (Start Chrome):** 10 seconds
- **Step 2 (Log in):** 30 seconds
- **Step 3 (Enrich 10 profiles):** 2-3 minutes
- **Total:** ~4 minutes to get real data

---

## After Enrichment

Once you have real data, you can:

1. **View in dashboard** - See actual names, locations, bios
2. **Edit profiles** - Update/correct information
3. **Export data** - Download CSV/JSON with complete profiles
4. **Search/filter** - Find profiles by name, location, etc.

---

**Status:** Ready to get actual user data  
**Next:** Run `./start_chrome_debug.sh` and follow steps above

