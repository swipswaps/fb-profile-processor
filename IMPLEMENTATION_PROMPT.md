# PROMPT: Update FB Profile Processor Repository with Docker Support

## Context
The fb-profile-processor repository needs updated configuration files to support Docker deployment with an interactive GitHub Pages setup guide.

## Required Changes

### 1. Update requirements.txt
**Current state:** Uses minimal dependencies (Playwright + Streamlit only)
**Required state:** Complete dependencies for full dashboard functionality

**Action:** Replace `requirements.txt` with merged version that includes:
- Streamlit + Pandas (UI/data)
- Both Playwright AND Selenium (browser automation)
- BeautifulSoup4 (HTML parsing)
- openpyxl (Excel export)
- pytesseract + Pillow (OCR)
- python-dotenv (configuration)

### 2. Update Dockerfile
**Current state:** May not exist or be incomplete
**Required state:** Production-ready Dockerfile with both browsers

**Action:** Create/replace `Dockerfile` with:
- Python 3.11-slim base
- Firefox + geckodriver (for Selenium)
- Chromium (for Playwright)
- Tesseract OCR
- All system dependencies
- Proper health checks
- Streamlit on port 8501

### 3. Ensure docker-compose.yml exists
**Required state:** Working docker-compose configuration

**Action:** Create/verify `docker-compose.yml` with:
- Service: fb-profile-processor
- Port mapping: 8501:8501
- Volume mounts: ./data (database persistence)
- Environment variables (BROWSER_TYPE, ENABLE_API)
- Health checks
- Restart policy

### 4. Create .dockerignore
**Required state:** Optimize Docker image size

**Action:** Create `.dockerignore` with:
- Python cache files (__pycache__, *.pyc)
- Virtual environments
- Git files
- Documentation
- Temporary files
- IDE files

### 5. Update docs/index.html (GitHub Pages)
**Current state:** Simple static URL transformer
**Required state:** Interactive Docker setup guide

**Action:** Replace `docs/index.html` with:
- Real-time Docker detection
- Step-by-step setup guide (4 steps)
- Progress bar
- Copy-to-clipboard buttons
- Platform-specific install links
- App status checking
- Management commands section

## Implementation Steps

1. **Backup existing files:**
   ```bash
   mv requirements.txt requirements.txt.bak
   mv Dockerfile Dockerfile.bak (if exists)
   mv docs/index.html docs/index.html.bak
   ```

2. **Add new files to repository:**
   - requirements.txt (merged version)
   - Dockerfile (updated version)
   - docker-compose.yml
   - .dockerignore
   - docs/index.html (interactive guide)

3. **Commit changes:**
   ```bash
   git add requirements.txt Dockerfile docker-compose.yml .dockerignore docs/index.html
   git commit -m "Add Docker support with interactive GitHub Pages setup guide"
   git push origin main
   ```

4. **Verify GitHub Pages:**
   - Visit https://swipswaps.github.io/fb-profile-processor/
   - Should show Docker detection and setup guide
   - Should guide users through: Install Docker → Clone → Start → Access

## Expected Results

**For users visiting GitHub Pages:**
1. Page loads and checks for Docker
2. If Docker not installed: Shows installation links
3. If Docker installed: Shows clone/start commands
4. If app running: Shows "Open Dashboard" button
5. Copy buttons make all commands one-click

**For users with Docker:**
```bash
git clone https://github.com/swipswaps/fb-profile-processor.git
cd fb-profile-processor
docker-compose up -d
# Access at http://localhost:8501
```

## Success Criteria

✅ requirements.txt includes all dependencies (Selenium, Excel, OCR)
✅ Dockerfile builds successfully
✅ docker-compose up -d starts application
✅ Dashboard accessible at localhost:8501
✅ GitHub Pages detects Docker status
✅ GitHub Pages guides users through setup
✅ All commands have copy buttons
✅ Database persists in ./data volume

## Files to Generate

1. **requirements.txt** - Complete dependencies
2. **Dockerfile** - Production-ready container
3. **docker-compose.yml** - Orchestration config
4. **.dockerignore** - Build optimization
5. **docs/index.html** - Interactive setup guide

All files should be production-ready, tested, and fully documented.
