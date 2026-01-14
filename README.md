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
# Start the Streamlit dashboard
streamlit run dashboard_integrated.py

# Or with custom port
streamlit run dashboard_integrated.py --server.port 8502
```

The dashboard opens at: **http://localhost:8501**

### Step 4: Using the Dashboard

#### Tab 1: 📥 Add URLs
1. Paste Facebook Marketplace profile URLs (one per line)
2. Or upload a `.txt` file with URLs
3. Click **"Process URLs"** to add to database

Example URLs:
```
https://www.facebook.com/marketplace/profile/123456789/
https://www.facebook.com/marketplace/profile/987654321/?ref=share
```

#### Tab 2: 👤 Profiles
- View all collected profiles in table or card view
- Filter by name, location, or status
- Click profile to see details and image

#### Tab 3: 🔍 Enrichment
1. Click **"🦊 Enrich with Firefox"**
2. Firefox opens briefly to collect profile data
3. Watch progress in real-time
4. Results saved automatically

#### Tab 4: 📈 Analytics
- View statistics on collected profiles
- Charts showing processing status
- Database size and health info

#### Tab 5: 💾 Export
- **CSV** - Spreadsheet format
- **JSON** - Developer-friendly
- **ZIP** - Includes profile images

#### Tab 6: ⚙️ Settings
- Configure database location
- Set up Facebook API token (optional, for future use)

#### Tab 7: 🛒 Marketplace
1. Click **"Scan My Listings"** in sidebar
2. Firefox opens to scan your selling items
3. View your listings with:
   - Title, price, status badges
   - Bump count and days until next bump
   - Direct links to Facebook

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
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                       │
│                  (dashboard_integrated.py)                   │
├─────────────────────────────────────────────────────────────┤
│  Add URLs │ Profiles │ Enrichment │ Analytics │ Marketplace │
└─────────────────────────────────────────────────────────────┘
        │           │           │                    │
        ▼           ▼           ▼                    ▼
┌───────────┐ ┌───────────┐ ┌─────────────┐ ┌─────────────────┐
│   HTTP    │ │  SQLite   │ │   Firefox   │ │   Marketplace   │
│ Processor │ │ Database  │ │  Selenium   │ │    Scraper      │
└───────────┘ └───────────┘ └─────────────┘ └─────────────────┘
```

### Key Components

| File | Purpose |
|------|---------|
| `dashboard_integrated.py` | Main Streamlit UI |
| `fb_profile_processor.py` | HTTP-based URL collection |
| `selenium_enricher.py` | Firefox browser enrichment |
| `marketplace_scraper.py` | Personal marketplace scanner |
| `docs/index.html` | GitHub Pages static demo |

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

