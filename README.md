# Facebook Profile & Marketplace Manager

A comprehensive Python tool for managing Facebook Marketplace seller profiles and your own marketplace listings. Features a Streamlit dashboard with real-time browser integration.

## 🚀 Project Evolution

This project evolved through several phases:

### Phase 1: URL Processor (Original)
- Simple HTTP-based URL transformer for Facebook Marketplace profile URLs
- Extracted metadata using OpenGraph tags
- SQLite storage with basic deduplication

### Phase 2: Browser Enrichment
- Added Playwright-based browser automation for deeper profile data
- Resolved numeric IDs to usernames
- Extracted profile pictures, bios, and follower counts

### Phase 3: Firefox Integration (Current)
- Switched from Chrome/Playwright to **Firefox + Selenium** for better compatibility
- Uses your existing Firefox profile (no separate login needed)
- Added **Streamlit dashboard** for visual management

### Phase 4: Marketplace Integration (Current)
- Added **My Marketplace** feature to scan your own selling items
- Extracts item details: title, price, images, status (available/pending/sold)
- Tracks bump counts and days until next bump
- Future-proofed for Facebook Graph API when access becomes available

### Phase 5: UX & Stability Improvements (Current)
- **Tab persistence** — No more jumping back to first tab on widget interaction
- **Session state management** — Proper initialization order prevents race conditions
- **Logging infrastructure** — Comprehensive debug logs for troubleshooting
- **Deprecation compliance** — Updated for Streamlit 2026+ API changes
- **Development workflow** — Hot-reload, log capture, and debug patterns

## Features

### 🎛️ Streamlit Dashboard (`dashboard_integrated.py`)
- **Visual profile management** - View, filter, and export seller profiles
- **My Marketplace** - Scan and track your own Facebook Marketplace listings
- **Image gallery** - View profile pictures and item images
- **Export options** - CSV, JSON, ZIP with images
- **Real-time enrichment** - One-click browser enrichment

### 📋 Profile Collection (`fb_profile_processor.py`)
✅ **URL Transformation** - Converts marketplace URLs to clean profile format
✅ **HTTP Metadata Extraction** - Fetches page titles and OpenGraph tags
✅ **SQLite Storage** - Structured database with deduplication
✅ **Resume Capability** - Skip already-processed URLs
✅ **Rate Limiting** - Configurable delay between requests

### 🔍 Browser Enrichment (`selenium_enricher.py`)
✅ **Firefox Integration** - Uses your existing Firefox profile (stay logged in!)
✅ **Profile Resolution** - Numeric ID → username URL
✅ **Full Profile Data** - Name, bio, location, followers, profile picture
✅ **Profile Picture Download** - Saves images locally

### 🛒 Marketplace Scanner (`marketplace_scraper.py`)
✅ **My Listings** - Scans your Facebook Marketplace selling items
✅ **Status Tracking** - Available, Pending, Sold, Draft
✅ **Bump Info** - Tracks bump count and days until next bump
✅ **Image Extraction** - Primary listing photos
✅ **API Ready** - Future-proofed for Facebook Graph API

### 🔐 Commerce API Integration
✅ **Meta Commerce Manager API** - Production-grade catalog management
✅ **Compliance Enforcement** - Hard-stop blocking for Meta policy violations
✅ **Pre-flight Checks** - One-click validation before operations
✅ **System User Gate** - Enforces production token requirements
✅ **API Deprecation Warnings** - Automatic alerts for version lifecycle
✅ **State Machine Dashboard** - Visual pipeline status (Token → Business → Commerce → Catalog)
✅ **Dry-Run Mode** - Test operations without mutations
✅ **Audit Logging** - Automatic log rotation with 30-day retention
✅ **Support Bundle Export** - One-click Meta Support debug package

### 🎯 UX & Stability
✅ **Tab Persistence** - No jumping back to first tab on widget interaction
✅ **Session State Management** - Proper initialization order prevents race conditions
✅ **Schema Detection** - Auto-detects Legacy/Profile/Marketplace/API-Ready schemas
✅ **Quick Actions** - Sidebar shortcuts for common operations
✅ **Search & Sort** - Filter and sort listings in Marketplace tab
✅ **View Modes** - Toggle between Table and Cards view

## 🌐 Live Demo

**Try the web interface:** [https://swipswaps.github.io/fb-profile-processor/](https://swipswaps.github.io/fb-profile-processor/)

The web interface provides instant URL transformation without any installation!

---

## 📋 Complete How-To Guide

### Prerequisites

- **Python 3.8+** installed
- **Firefox browser** with your Facebook account logged in
- **pip** package manager

### Step 1: Installation

```bash
# Clone the repository
git clone https://github.com/swipswaps/fb-profile-processor.git
cd fb-profile-processor

# Install Python dependencies
pip install -r requirements.txt
```

**Required packages:**
- `streamlit` - Dashboard UI
- `selenium` - Browser automation
- `requests` - HTTP requests
- `pandas` - Data processing
- `Pillow` - Image handling

### Step 2: Firefox Setup (One-Time)

The tool uses your existing Firefox profile to access Facebook. No separate login needed!

1. **Open Firefox** and log into Facebook
2. **Stay logged in** (check "Remember me")
3. **Close Firefox** before running the dashboard

The tool will automatically find your Firefox profile and use your existing session.

### Step 3: Run the Dashboard

```bash
# Start the Streamlit dashboard (recommended for development)
streamlit run dashboard_integrated.py --server.port 8501 --server.runOnSave=true 2>&1 | tee /tmp/streamlit.log
```

**Command breakdown:**
- `--server.port 8501` — Predictable port access
- `--server.runOnSave=true` — Hot-reload on file save (no manual restart needed)
- `2>&1 | tee /tmp/streamlit.log` — Captures logs for troubleshooting

The dashboard opens at: **http://localhost:8501**

**Alternative (simple start):**
```bash
streamlit run dashboard_integrated.py
```

### Step 4: Using the Dashboard

The dashboard has 8 tabs plus a sidebar with quick actions:

---

#### Sidebar Features (Always Visible)

**Database Selection:**
- Select from available `.db` files in the project
- Schema version indicator (Legacy/Profile/Marketplace/API-Ready)
- One-click schema migration button

**Quick Stats:**
- Total records, successful extractions, images collected
- For Marketplace: available, sold, ready to bump counts

**Quick Actions:**
- ⚡ **Enrich All Pending** — One-click batch enrichment (when Firefox ready)
- 🔄 **Scan My Listings** — Refresh marketplace items

**Marketplace Status:**
- Shows logged-in user name when Firefox is ready
- Listing count with direct scan button

---

#### Tab 1: 📤 Upload & Process
1. Paste Facebook Marketplace profile URLs (one per line)
2. Or upload a `.txt` file with URLs
3. Click **"Process URLs"** to add to database
4. **Stage 2: Browser Enrichment** — Enrich profiles with Firefox

Example URLs:
```
https://www.facebook.com/marketplace/profile/123456789/
https://www.facebook.com/marketplace/profile/987654321/?ref=share
```

**Two-Stage Processing:**
- **Stage 1:** HTTP metadata extraction (fast, no login required)
- **Stage 2:** Firefox enrichment for full profile data (requires Facebook login)

---

#### Tab 2: 📊 View Data
- View all collected profiles in **Table** or **Card** view
- Search by name, location, or any field
- Sort by date, name, or enrichment status
- Click any profile row to see full details and image

**View Modes:**
- 📋 **Table** — Spreadsheet-style with sortable columns
- 🃏 **Cards** — Visual cards with profile images

---

#### Tab 3: ✏️ Edit Records
- **Edit** any profile's details (name, bio, location)
- **Delete** individual records or bulk delete
- **Mark as enriched** — Manual override for enrichment status
- Changes saved immediately to database

---

#### Tab 4: 📈 Analytics
- View statistics on collected profiles
- Charts showing processing status
- Database size and health info
- Schema version and migration status

---

#### Tab 5: 💾 Export
- **CSV** — Spreadsheet format for Excel/Google Sheets
- **JSON** — Developer-friendly structured data
- **ZIP** — Complete package with profile images included

**Export Options:**
- Export all records or filtered selection
- Include/exclude specific columns
- Download directly to browser

---

#### Tab 6: ⚙️ Settings
- Configure default database location
- Set up Facebook API credentials (optional)
- View Firefox profile detection status
- Debug logging options

---

#### Tab 7: 🛒 Marketplace
Your personal Facebook Marketplace listing manager.

**Getting Started:**
1. Click **"Scan My Listings"** in sidebar (or button in tab)
2. Firefox opens briefly to scan your selling items
3. View your listings with full details

**Listing Features:**
- Title, price, status badges (Available/Pending/Sold/Draft)
- Bump count and days until next bump
- Primary listing image
- Direct links to Facebook

**View Options:**
- 📋 **Table View** — Spreadsheet with all columns, click row for detail panel
- 🃏 **Cards View** — Visual cards with images

**Search & Sort:**
- 🔍 **Search** — Filter listings by title
- **Sort by** — Newest, Price (Low/High), Title

**Incomplete Data Warning:**
- Shows if fewer listings found than previous scan
- Prompts to configure API for reliable data

---

#### Tab 8: 🔧 API Config
Meta Commerce API integration with compliance enforcement.

**Compliance Status Section:**
- **State Machine Pipeline** — Visual status: Token ✅ → Business ✅ → Commerce ⚠️ → Catalog ❌
- **Blocking Issues** — Hard stops with "Why Meta requires this" and "How to fix" links
- **Warnings** — Non-blocking advisories (API deprecation, zero products)

**Mode Selector:**
- **Setup/Diagnostic Mode** — Human tokens allowed for testing
- **Production Mode** — System User tokens required (enforced)

**Pre-flight Check:**
- Click "🛫 Run Pre-flight Compliance Check" before major operations
- Validates all Meta requirements
- Shows pass/fail per requirement

**Dry-Run Mode:**
- Test API calls without making actual changes
- Verify permissions and connectivity safely

---

## 🔐 Commerce API Setup (Meta-Aligned)

### Prerequisites for API Access

1. **Facebook Business Manager** account at [business.facebook.com](https://business.facebook.com)
2. **Commerce Account** in Commerce Manager
3. **Product Catalog** created and linked to Commerce Account
4. **System User** with required permissions (for production use)

### Step 1: Create a Facebook App

1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Click "My Apps" → "Create App"
3. Select "Business" type
4. Connect to your Business Manager

### Step 2: Set Up System User (Required for Production)

Meta requires System User tokens for background/production operations. Human tokens can be revoked without notice.

1. Go to **Business Settings** → **System Users**
2. Click **Add** → Create new System User
3. Assign to your app with **Admin** role
4. Click **Generate Token** with these permissions:
   - `catalog_management` - Read/write product catalogs
   - `business_management` - Manage business assets

### Step 3: Link Catalog to Commerce Account

Meta requires this linkage for Marketplace listing visibility:

1. Go to **Commerce Manager** → **Settings**
2. Click **Business Assets** → **Link Product Catalog**
3. Select your catalog

### Step 4: Configure Environment Variables

```bash
# Required for API operations
export FB_ACCESS_TOKEN="your_system_user_token"
export FB_CATALOG_ID="your_catalog_id"
```

Or set them in the dashboard's API Config tab.

### Step 5: Verify Setup

In the dashboard, go to **API Config** tab and check:

| Status | Meaning |
|--------|---------|
| Token Valid ✅ | Access token is valid and not expired |
| Business Accessible ✅ | Can access Business Manager |
| Commerce Account ✅ | Commerce Account is linked |
| Catalog Accessible ✅ | Catalog is readable |
| Capabilities Detected ✅ | Write permissions confirmed |

If any show ❌, click the expander for fix instructions.

---

## 🔒 Compliance Enforcement

The system enforces Meta requirements through **hard stops** (not warnings):

### Blocking Conditions (Operations Disabled)

| Condition | Why Meta Requires | How to Fix |
|-----------|-------------------|------------|
| TOKEN_INVALID | Authentication required for API | Generate new token in Developer Portal |
| MISSING_SCOPES | catalog_management + business_management required | Business Settings → System Users → Add Assets |
| CATALOG_NOT_LINKED | Commerce linkage for Marketplace visibility | Commerce Manager → Settings → Link Catalog |
| NO_BUSINESS_ACCESS | Business Manager access required | Business Settings → People → Add yourself |
| SYSTEM_USER_REQUIRED | Production ops need System User tokens | Business Settings → System Users → Generate Token |

### Warning Conditions (Operations Allowed)

| Condition | Advisory |
|-----------|----------|
| API_DEPRECATION | API version nearing 2-year deprecation |
| ZERO_PRODUCTS | Catalog has no products |
| HUMAN_TOKEN_INTERACTIVE | Human token OK for testing only |
| TOKEN_EXPIRING | Token expires in <14 days |

---

## 🛠️ Command-Line Usage

### Profile Collection (HTTP-only)

```bash
# Process URLs from links.txt
python3 fb_profile_processor.py

# Custom input file
python3 fb_profile_processor.py --input my_urls.txt

# Export results
python3 fb_profile_processor.py --export-json results.json
```

### Browser Enrichment (Firefox)

```bash
# Enrich pending profiles
python3 selenium_enricher.py --database facebook_profiles.db --limit 10
```

### Marketplace Scanning

```bash
# Scan your marketplace listings
python3 marketplace_scraper.py --scan --limit 50
```

---

## 📁 Database Schema

### Profiles Table (`facebook_profiles.db`)

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_url TEXT NOT NULL UNIQUE,
    resolved_url TEXT,
    profile_id TEXT,
    username TEXT,
    display_name TEXT,
    profile_picture_url TEXT,
    local_image_path TEXT,
    bio TEXT,
    location TEXT,
    join_date TEXT,
    enriched INTEGER DEFAULT 0,
    enriched_at TEXT,
    error TEXT
);
```

### Marketplace Items Table (`marketplace.db`)

```sql
CREATE TABLE marketplace_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id TEXT UNIQUE,
    title TEXT,
    price TEXT,
    status TEXT DEFAULT 'available',
    is_sold INTEGER DEFAULT 0,
    is_pending INTEGER DEFAULT 0,
    is_draft INTEGER DEFAULT 0,
    bump_count INTEGER DEFAULT 0,
    days_until_next_bump INTEGER,
    max_bump_count INTEGER DEFAULT 5,
    image_urls TEXT,
    local_image_paths TEXT,
    seller_id TEXT,
    seller_name TEXT,
    item_url TEXT,
    scraped_at TEXT,
    updated_at TEXT
);
```

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Streamlit Dashboard                               │
│                      (dashboard_integrated.py)                            │
├──────────────────────────────────────────────────────────────────────────┤
│  Add URLs │ Profiles │ Enrichment │ Analytics │ Marketplace │ API Config │
└──────────────────────────────────────────────────────────────────────────┘
        │           │           │           │               │
        ▼           ▼           ▼           ▼               ▼
┌───────────┐ ┌───────────┐ ┌─────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   HTTP    │ │  SQLite   │ │   Firefox   │ │   Marketplace   │ │  Commerce API   │
│ Processor │ │ Database  │ │  Selenium   │ │    Scraper      │ │  (Meta Graph)   │
└───────────┘ └───────────┘ └─────────────┘ └─────────────────┘ └─────────────────┘
                                                                        │
                                                    ┌───────────────────┼───────────────────┐
                                                    ▼                   ▼                   ▼
                                            ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
                                            │ Compliance  │     │   Audit     │     │    Rate     │
                                            │    Gate     │     │   Logger    │     │   Limiter   │
                                            └─────────────┘     └─────────────┘     └─────────────┘
```

### Key Components

| File | Purpose |
|------|---------|
| `dashboard_integrated.py` | Main Streamlit UI |
| `dashboard.py` | Alternate dashboard with API Config tab |
| `fb_profile_processor.py` | HTTP-based URL collection |
| `selenium_enricher.py` | Firefox browser enrichment |
| `marketplace_scraper.py` | Marketplace scanner + Commerce API |
| `docs/index.html` | GitHub Pages static demo |

### Commerce API Classes

| Class | Purpose |
|-------|---------|
| `FacebookCommerceAPI` | Production-grade Commerce Manager API wrapper |
| `ComplianceGate` | Compliance enforcement with blocking/warning logic |
| `TokenHealth` | Token validity and expiry monitoring |
| `CatalogCapabilities` | Catalog permission probing |
| `APIAuditLogger` | Audit logging with rotation and retention |
| `RateLimitState` | Exponential backoff rate limiting |

---

## 🚀 GitHub Pages Setup

The `/docs` folder contains a static HTML demo for URL transformation.

1. Go to repository **Settings** → **Pages**
2. Under **Source**, select:
   - Branch: `main`
   - Folder: `/docs`
3. Click **Save**
4. Access at: `https://swipswaps.github.io/fb-profile-processor/`

---

## ⚠️ Troubleshooting

### Tab jumps back to first tab
This issue has been fixed in Phase 5. If you're experiencing this:
- Update to the latest version of `dashboard_integrated.py`
- Clear browser cache and refresh
- The fix uses `st.radio()` with session state instead of `st.tabs()` which has a known Streamlit bug

### Firefox not detected
- Ensure Firefox is installed
- Log into Facebook in Firefox first
- Close Firefox before running dashboard

### Enrichment fails
- Check Firefox profile exists: `~/.mozilla/firefox/*.default-release`
- Ensure Facebook session is valid (not expired)
- Try logging into Facebook again

### Marketplace scan empty
- Verify you have active listings on Facebook Marketplace
- Check Firefox is logged into the correct Facebook account

### API: "TOKEN_INVALID" error
- Token may have expired - generate a new one
- Verify token at: [developers.facebook.com/tools/debug/accesstoken](https://developers.facebook.com/tools/debug/accesstoken)
- Ensure token has `catalog_management` and `business_management` scopes

### API: "MISSING_SCOPES" error
- Go to **Business Settings** → **System Users**
- Click on your System User → **Add Assets**
- Grant `catalog_management` and `business_management` permissions

### API: "CATALOG_NOT_LINKED" error
- Go to **Commerce Manager** → **Settings** → **Business Assets**
- Click **Link Product Catalog**
- Select your catalog

### API: "SYSTEM_USER_REQUIRED" error
- Production mode requires System User tokens (not human tokens)
- Create System User in **Business Settings** → **System Users**
- Generate token with required permissions

### API: "Cannot switch to Production Mode"
- Your current token is a human user token
- System User tokens are required for production operations
- Human tokens can be revoked by Meta without notice

### API: Rate limited
- Wait for cooldown period (shown in dashboard)
- Reduce request frequency
- Check if you're hitting Meta's rate limits

### Pre-flight check fails
- Run the pre-flight check in API Config tab
- Each failing requirement shows "How to fix" instructions
- Fix blocking issues before proceeding

---

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please ensure:
- Python 3.8+ compatibility
- Code follows project style
- Documentation updated

## 📞 Support

For issues or questions, please open a GitHub issue.

