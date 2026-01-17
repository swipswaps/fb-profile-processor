#!/usr/bin/env python3
"""
Facebook Profile Processor - Integrated Dashboard
Full-featured dashboard with URL upload, processing, CRUD operations, and export

USAGE:
    streamlit run dashboard_integrated.py
"""

import streamlit as st
import pandas as pd
import sqlite3
import fb_profile_processor as processor
import selenium_enricher  # Firefox-based enricher (works with existing profile)
import marketplace_scraper  # Marketplace items scraper
from pathlib import Path
from datetime import datetime
import io
import zipfile
import requests
from PIL import Image
import logging
import time
import sys

# ======================
# LOGGING CONFIGURATION
# ======================
# Comprehensive logging per Rule 25: timestamps, levels, console + file
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),  # Console output
        logging.FileHandler("/tmp/dashboard.log", mode="a"),  # File output
    ]
)

# Dashboard-specific logger
logger = logging.getLogger("dashboard")
logger.setLevel(logging.DEBUG)  # Capture all levels

# Log startup
logger.info("=" * 60)
logger.info("DASHBOARD STARTUP")
logger.info(f"Python: {sys.version}")
logger.info(f"Working dir: {Path.cwd()}")
logger.info("=" * 60)

# Commerce API imports for compliance enforcement
try:
    from marketplace_scraper import (
        get_commerce_api, FacebookCommerceAPI, run_preflight_compliance_check,
        ComplianceGate, get_api_version_status,
        COMPLIANCE_REQUIREMENTS, get_compliance_status, is_globally_compliant,
        run_live_diagnostics
    )
    COMMERCE_API_AVAILABLE = True
except ImportError:
    COMMERCE_API_AVAILABLE = False
    COMPLIANCE_REQUIREMENTS = []
    def get_compliance_status(): return {"requirements": [], "total": 0, "complete": 0, "can_proceed": False}
    def is_globally_compliant(): return False, "Commerce API not available", []
    def run_live_diagnostics(api=None): return {"checks": [], "can_proceed": False, "live_checked": False}

# Future-proofing: Provider pattern for API support
try:
    from provider_manager import ProviderManager
    from data_providers import FacebookConfig, DataSource
    PROVIDER_SUPPORT = True
except ImportError:
    PROVIDER_SUPPORT = False


# ======================
# SCHEMA COMPATIBILITY
# ======================

def detect_schema_version(db_path):
    """Detect if database uses old or new schema"""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(profiles)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()

        return 'new' if 'fb_id' in columns else 'old'
    except Exception as e:
        logging.error(f"Schema detection failed: {e}")
        return 'unknown'


def check_api_schema_version(db_path: str) -> int:
    """
    Check database API schema version (from schema_version table).

    Returns:
        0 = Legacy (no schema_version table or no API support tables)
        1-5 = Schema version with API support
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if schema_version table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        if not cursor.fetchone():
            conn.close()
            return 0  # Legacy - no version tracking

        # Get max version
        cursor.execute("SELECT MAX(version) FROM schema_version")
        result = cursor.fetchone()
        conn.close()

        return result[0] if result and result[0] else 0
    except Exception as e:
        logging.error(f"API schema version check failed: {e}")
        return 0


def is_api_ready(db_path: str) -> bool:
    """Check if database supports API features (schema v5+)"""
    return check_api_schema_version(db_path) >= 5


def detect_schema_type(db_path: str) -> tuple:
    """
    Detect database schema type by inspecting tables and columns.
    Improved version that handles both marketplace and profile databases.

    Returns:
        (schema_type, table_name, column_list)
        schema_type: 'profile', 'marketplace', or 'unknown'
    """
    logger.debug(f"Detecting schema for: {db_path}")
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            conn.close()
            logger.info(f"Empty database: {db_path}")
            return 'empty', None, []

        # Check for known tables
        if 'marketplace_items' in tables:
            cursor.execute("PRAGMA table_info(marketplace_items)")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()
            logger.info(f"Detected marketplace schema: {len(columns)} columns")
            return 'marketplace', 'marketplace_items', columns

        if 'profiles' in tables:
            cursor.execute("PRAGMA table_info(profiles)")
            columns = [row[1] for row in cursor.fetchall()]
            conn.close()
            logger.info(f"Detected profile schema: {len(columns)} columns")
            return 'profile', 'profiles', columns

        # Unknown - use first table
        table = tables[0]
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        logger.warning(f"Unknown schema in table '{table}': {columns}")
        return 'unknown', table, columns

    except Exception as e:
        logger.error(f"Schema detection failed: {e}")
        return 'error', None, []


def safe_col(df: pd.DataFrame, col: str, default=None):
    """Safely get column from dataframe, return default if missing."""
    return df[col] if col in df.columns else default


def get_database_with_schema_info(db_path: str) -> str:
    """Get database display name with schema info"""
    if not Path(db_path).exists():
        return f"📄 {db_path} (new)"

    api_version = check_api_schema_version(db_path)
    base_schema = detect_schema_version(db_path)

    if api_version >= 5:
        return f"📊 {db_path} (v{api_version} - API Ready)"
    elif api_version > 0:
        return f"🔧 {db_path} (v{api_version} - Partial)"
    elif base_schema == 'new':
        return f"🔧 {db_path} (needs API migration)"
    else:
        return f"⚠️ {db_path} (legacy)"


def run_api_migration(db_path: str) -> tuple:
    """
    Run API support migration on database.

    Returns:
        (success: bool, message: str)
    """
    import subprocess
    try:
        result = subprocess.run(
            ['python3', 'migrate_for_api_support.py', '--database', db_path],
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return True, result.stdout
        else:
            return False, result.stderr or "Migration failed"
    except subprocess.TimeoutExpired:
        return False, "Migration timed out"
    except FileNotFoundError:
        return False, "migrate_for_api_support.py not found"
    except Exception as e:
        return False, str(e)


def get_display_columns(schema_version):
    """Get column names for display based on schema version"""
    if schema_version == 'new':
        return {
            'id': 'id',
            'fb_id': 'fb_id',
            'name': 'fb_name',
            'username': 'fb_username',
            'profile_url': 'fb_profile_url',
            'error': 'http_error',
            'status': 'enrichment_status',
            'picture': 'fb_picture_url',
            'bio': 'fb_bio',
            'location': 'fb_location_name',
            'fetched_at': 'http_fetched_at'
        }
    else:  # old schema
        return {
            'id': 'id',
            'fb_id': 'profile_id',
            'name': 'page_title',
            'username': 'browser_resolved_username',
            'profile_url': 'clean_url',
            'error': 'error',
            'status': 'enrichment_status',
            'picture': 'browser_profile_pic_url',
            'bio': 'browser_profile_bio',
            'location': 'browser_profile_location',
            'fetched_at': 'fetched_at'
        }

# Page configuration
st.set_page_config(
    page_title="FB Profile Processor - Full Dashboard",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state EARLY (before any rendering)
# Per Rule 25: Log session state initialization
logger.debug("Initializing session state")
if 'processing' not in st.session_state:
    st.session_state.processing = False
    logger.debug("session_state.processing initialized to False")
if 'last_processed' not in st.session_state:
    st.session_state.last_processed = None
if 'selected_db' not in st.session_state:
    st.session_state.selected_db = 'facebook_profiles.db'
    logger.info(f"session_state.selected_db initialized to: facebook_profiles.db")
if 'firefox_ready' not in st.session_state:
    st.session_state.firefox_ready = None
if 'fb_logged_in_user' not in st.session_state:
    st.session_state.fb_logged_in_user = None
if 'marketplace_items' not in st.session_state:
    st.session_state.marketplace_items = []

# CRITICAL: Initialize active_tab BEFORE any UI rendering
# This prevents tab jumping on first widget interaction (known Streamlit pattern)
# See: https://discuss.streamlit.io/t/st-tabs-how-to-prevent-rerun-and-jumping-back-to-tab-1/30202
if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0  # Default to first tab (Upload & Process)
    logger.info("session_state.active_tab initialized to: 0 (Upload & Process)")

# Check Firefox readiness EARLY (before sidebar renders)
if st.session_state.firefox_ready is None:
    logger.debug("Checking Firefox readiness...")
    try:
        profile_path = selenium_enricher.get_firefox_profile_path()
        st.session_state.firefox_ready = profile_path is not None
        logger.info(f"Firefox ready: {st.session_state.firefox_ready}, profile: {profile_path}")
    except Exception as e:
        st.session_state.firefox_ready = False
        logger.error(f"Firefox readiness check failed: {e}")


def check_firefox_ready():
    """Check if Firefox profile exists and Selenium can use it"""
    try:
        profile_path = selenium_enricher.get_firefox_profile_path()
        if profile_path:
            return True
        return False
    except Exception as e:
        return False


def download_profile_image(profile_id, image_url, images_dir='profile_images'):
    """Download and store profile image locally"""
    images_path = Path(images_dir)
    images_path.mkdir(exist_ok=True)

    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            ext = image_url.split('.')[-1].split('?')[0] or 'jpg'
            if ext not in ['jpg', 'jpeg', 'png', 'gif']:
                ext = 'jpg'
            filename = f"{profile_id}.{ext}"
            filepath = images_path / filename
            filepath.write_bytes(response.content)
            return str(filepath)
    except Exception as e:
        logging.error(f"Failed to download image for {profile_id}: {e}")
    return None


@st.cache_data
def load_data(db_path):
    """Load data from SQLite database with caching"""
    logger.debug(f"load_data() called for: {db_path}")
    try:
        if not Path(db_path).exists():
            logger.warning(f"Database not found: {db_path}")
            return pd.DataFrame()
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        # Check if profiles table exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'")
        if not cursor.fetchone():
            conn.close()
            return pd.DataFrame()
        df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
        conn.close()
        return df
    except Exception as e:
        logging.warning(f"Could not load database {db_path}: {e}")
        return pd.DataFrame()


def get_database_stats(df, schema_type: str = 'profile') -> dict:
    """
    Calculate database statistics based on schema type.

    Args:
        df: DataFrame with data
        schema_type: 'profile', 'marketplace', or 'unknown'

    Returns:
        dict with schema-appropriate statistics
    """
    logger.debug(f"Calculating stats for schema: {schema_type}, rows: {len(df)}")

    if df.empty:
        return {'total_records': 0}

    stats = {'total_records': len(df)}

    if schema_type == 'profile':
        # Profile schema stats (original logic, improved)
        error_col = 'http_error' if 'http_error' in df.columns else 'error'
        pic_col = 'fb_picture_url' if 'fb_picture_url' in df.columns else 'browser_profile_pic_url'

        if error_col in df.columns:
            stats['successful'] = len(df[df[error_col].isna()])
            stats['errors'] = len(df[df[error_col].notna()])
        else:
            stats['successful'] = len(df)
            stats['errors'] = 0

        if 'enrichment_status' in df.columns:
            stats['pending_enrichment'] = len(df[df['enrichment_status'] == 'pending'])
            stats['enriched'] = len(df[df['enrichment_status'] == 'enriched'])
            stats['failed_enrichment'] = len(df[df['enrichment_status'] == 'failed'])
        else:
            stats['pending_enrichment'] = 0
            stats['enriched'] = 0
            stats['failed_enrichment'] = 0

        if pic_col in df.columns:
            stats['with_images'] = len(df[df[pic_col].notna()])

    elif schema_type == 'marketplace':
        # Marketplace schema stats (new)
        if 'status' in df.columns:
            stats['available'] = len(df[df['status'] == 'available'])
            stats['sold'] = len(df[df['status'] == 'sold'])
            stats['pending'] = len(df[df['status'] == 'pending'])
            stats['draft'] = len(df[df['status'] == 'draft'])

        if 'price' in df.columns:
            valid_prices = df['price'].notna() & ~df['price'].isin(['', 'See on Facebook'])
            stats['with_price'] = len(df[valid_prices])

        if 'title' in df.columns:
            stats['with_title'] = len(df[df['title'].notna() & (df['title'] != '')])

        if 'bump_count' in df.columns:
            stats['total_bumps'] = int(df['bump_count'].sum()) if df['bump_count'].notna().any() else 0

        if 'days_until_next_bump' in df.columns:
            bumpable = df['days_until_next_bump'].notna() & (df['days_until_next_bump'] <= 0)
            stats['ready_to_bump'] = len(df[bumpable])

    logger.debug(f"Stats calculated: {stats}")
    return stats


def process_urls_ui(urls, db_file, rate_limit=1.0, timeout=15):
    """Process URLs with HTTP only (Stage 1)"""
    logger.info(f"process_urls_ui() called: {len(urls)} URLs, db={db_file}, rate={rate_limit}s, timeout={timeout}s")
    # DEBUG
    st.write(f"🔍 process_urls_ui called with {len(urls)} URLs")
    st.write(f"   Database: {db_file}")

    st.session_state.processing = True

    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    # DEBUG
    st.write("🔍 About to call processor.process_urls_batch...")

    def progress_callback(current, total, url, result):
        progress_bar.progress(current / total)
        status_text.text(f"Processing {current}/{total}: {url[:50]}...")

        with results_container:
            if result['success']:
                st.success(f"✓ {url[:60]} - Profile ID: {result['profile_id']}")
            elif result['error'] == 'URL already processed':
                st.info(f"⊘ {url[:60]} - Already processed")
            else:
                st.error(f"✗ {url[:60]} - Error: {result['error']}")

    # Process batch
    batch_result = processor.process_urls_batch(
        urls,
        db_file,
        rate_limit=rate_limit,
        timeout=timeout,
        progress_callback=progress_callback
    )

    # Summary
    st.success(f"""
    **HTTP Processing Complete!**
    - Total: {batch_result['total']}
    - Success: {batch_result['success']}
    - Errors: {batch_result['errors']}
    - Skipped: {batch_result['skipped']}
    """)

    st.session_state.processing = False
    st.session_state.last_processed = datetime.now()

    # Clear cache to reload data
    load_data.clear()

    return batch_result


def enrich_with_browser_ui(db_file, rate_limit=3.0):
    """Enrich pending profiles with Firefox browser (Stage 2)"""
    st.session_state.processing = True

    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()
    driver = None
    temp_profile_dir = None

    try:
        # Create Firefox driver with existing profile
        status_text.text("Starting Firefox with your profile (includes FB login)...")
        driver, temp_profile_dir = selenium_enricher.create_firefox_driver()

        if not driver:
            st.error("Failed to create Firefox driver")
            st.session_state.processing = False
            return

        # Get pending profiles (supports both old and new schema)
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()

        # Check which columns exist
        cur.execute("PRAGMA table_info(profiles)")
        columns = {row[1] for row in cur.fetchall()}

        # Use fb_id (new schema) or profile_id (old schema)
        if 'fb_id' in columns:
            cur.execute("""
                SELECT id, fb_id, input_url
                FROM profiles
                WHERE fb_id IS NOT NULL
                AND (enrichment_status IS NULL OR enrichment_status = 'pending' OR enrichment_status = 'partial')
            """)
        else:
            cur.execute("""
                SELECT id, profile_id, clean_url
                FROM profiles
                WHERE enrichment_status = 'pending'
                AND profile_id IS NOT NULL
            """)
        pending = cur.fetchall()
        conn.close()

        if not pending:
            st.info("No pending profiles to enrich")
            st.session_state.processing = False
            return

        total = len(pending)
        success_count = 0
        error_count = 0

        # Process each profile
        for i, (db_id, fb_id, input_url) in enumerate(pending, 1):
            progress_bar.progress(i / total)
            status_text.text(f"Enriching {i}/{total}: {fb_id}...")

            try:
                # Enrich profile using Selenium (pass db_id as profile_id, fb_id for URL)
                enrichment_data = selenium_enricher.enrich_profile(driver, db_id, fb_id)

                # Download profile image if available
                local_image_path = None
                pic_url = enrichment_data.get('fb_picture_url') or enrichment_data.get('browser_profile_pic_url')
                if pic_url:
                    local_image_path = download_profile_image(fb_id, pic_url)
                    if local_image_path:
                        enrichment_data['local_image_path'] = local_image_path

                # Update database
                logger.info(f"DB UPDATE: profile {db_id} ({fb_id}) with enrichment data")
                conn = sqlite3.connect(db_file)
                selenium_enricher.update_profile_in_db(conn, db_id, enrichment_data)
                conn.close()
                logger.debug(f"DB UPDATE successful for profile {db_id}")

                username = enrichment_data.get('fb_username') or enrichment_data.get('browser_resolved_username', 'N/A')
                with results_container:
                    st.success(f"✓ {fb_id} - {username}")

                success_count += 1
                logger.info(f"Enrichment SUCCESS: {fb_id} -> {username}")

            except Exception as e:
                logger.error(f"Enrichment FAILED: {profile_id} - {e}")
                with results_container:
                    st.error(f"✗ {profile_id} - Error: {str(e)}")
                error_count += 1

            # Rate limiting
            if i < total:
                time.sleep(rate_limit)

        # Summary
        logger.info(f"ENRICHMENT COMPLETE: total={total}, success={success_count}, errors={error_count}")
        st.success(f"""
        **Firefox Enrichment Complete!**
        - Total: {total}
        - Success: {success_count}
        - Errors: {error_count}
        """)

    except Exception as e:
        logger.exception(f"Firefox enrichment failed: {e}")
        st.error(f"Firefox enrichment failed: {e}")
        import traceback
        st.code(traceback.format_exc())
        st.info("""
        **To enable Firefox enrichment:**
        1. Log into Facebook in your regular Firefox browser
        2. Refresh this dashboard

        The enricher uses your existing Firefox profile with cookies.
        No special setup required!
        """)

    finally:
        # Cleanup
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logger.debug(f"Driver cleanup error (ignored): {e}")
        if temp_profile_dir:
            selenium_enricher.cleanup_temp_profile()
        st.session_state.processing = False
        load_data.clear()


def display_profile_image(url, width=100):
    """Display profile image from URL"""
    if pd.isna(url) or not url:
        return None

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            img = Image.open(io.BytesIO(response.content))
            return img
    except Exception as e:
        logger.debug(f"Failed to load profile image: {e}")
    return None


def is_placeholder_title(title: str, item_id: str) -> bool:
    """Check if title is a placeholder (just contains the item ID)."""
    if not title or not item_id:
        return True
    # Placeholder pattern: "Item {item_id}" or just the item_id
    title_str = str(title).strip()
    item_id_str = str(item_id).strip()
    return (
        title_str == f"Item {item_id_str}" or
        title_str == item_id_str or
        title_str.lower() == 'untitled' or
        title_str == 'N/A'
    )

def format_display_title(title: str, item_id: str) -> str:
    """Format title for display, handling placeholders gracefully."""
    if is_placeholder_title(title, item_id):
        # Show truncated ID with indicator
        short_id = str(item_id)[-8:] if len(str(item_id)) > 8 else str(item_id)
        return f"📦 Listing ...{short_id}"
    return str(title)[:60]

def format_display_price(price) -> str:
    """Format price for display, handling 'See on Facebook' and other edge cases."""
    if pd.isna(price) or price in ['', None, 'N/A']:
        return "💰 Price on FB"
    price_str = str(price).strip()
    if price_str.lower() == 'see on facebook':
        return "💰 Price on FB"
    if price_str.startswith('$'):
        return price_str
    try:
        return f"${float(price_str):,.0f}"
    except (ValueError, TypeError):
        return price_str


def render_listing_card(row: pd.Series):
    """
    Render a single marketplace listing as a visual card.
    Used in the Marketplace tab for grid display.
    """
    item_id = row.get('item_id', row.get('id', 'N/A'))
    raw_title = str(row.get('title', 'Untitled'))
    title = format_display_title(raw_title, item_id)
    price = row.get('price', 'N/A')
    status = row.get('status', 'unknown')

    # Status badge colors
    status_colors = {
        'available': '🟢',
        'sold': '🔴',
        'pending': '🟡',
        'draft': '⚪',
    }
    status_icon = status_colors.get(status, '⚫')

    # Card container
    with st.container():
        # Try to show image
        local_img = row.get('local_image_path') or row.get('local_image_paths')
        remote_img = row.get('image_url') or row.get('image_urls')
        image_path = Path(f"marketplace_images/{item_id}.jpg")

        if local_img and Path(str(local_img)).exists():
            st.image(str(local_img), width="stretch")
        elif image_path.exists():
            st.image(str(image_path), width="stretch")
        elif remote_img:
            try:
                st.image(str(remote_img), width="stretch")
            except Exception as e:
                logger.debug(f"Failed to load remote image for {item_id}: {e}")
                st.markdown("📷 *No image*")
        else:
            st.markdown("📷 *No image*")

        # Title and status
        st.markdown(f"**{title}**")

        # Format price display using helper function
        price_display = format_display_price(price)

        st.markdown(f"{status_icon} {status.title()} | **{price_display}**")

        # Bump info
        bump_count = row.get('bump_count', 0)
        days_until = row.get('days_until_next_bump')
        if pd.notna(bump_count):
            if pd.notna(days_until) and days_until <= 0:
                st.caption(f"🔄 Bumps: {int(bump_count)} | **Ready to bump!**")
            elif pd.notna(days_until):
                st.caption(f"🔄 Bumps: {int(bump_count)} | {int(days_until)} days until next")
            else:
                st.caption(f"🔄 Bumps: {int(bump_count)}")

        # Link to Facebook
        st.markdown(f"[View on Facebook](https://facebook.com/marketplace/item/{item_id})")
        st.markdown("---")


def main():
    logger.info("main() called - rendering dashboard")

    # Title
    st.title("🔗 Facebook Profile Processor - Full Dashboard")
    st.markdown("Upload URLs, process profiles, manage data, and export with images")
    
    # Sidebar - Database selection
    st.sidebar.header("⚙️ Database")

    db_files = list(Path('.').glob('*.db'))
    db_options = [str(f) for f in db_files] if db_files else []

    # Add option to create new database
    db_options.insert(0, "facebook_profiles.db")
    db_options = list(set(db_options))  # Remove duplicates

    # Create display labels with schema info
    db_labels = {db: get_database_with_schema_info(db) for db in db_options}

    selected_db = st.sidebar.selectbox(
        "Select Database",
        db_options,
        index=0,
        format_func=lambda x: db_labels.get(x, x)
    )

    # Detect and display schema version with API status
    if Path(selected_db).exists():
        schema_version = detect_schema_version(selected_db)
        api_version = check_api_schema_version(selected_db)
        api_ready = is_api_ready(selected_db)

        # Store in session state for use elsewhere
        st.session_state.api_schema_version = api_version
        st.session_state.api_ready = api_ready

        if schema_version == 'new':
            if api_ready:
                st.sidebar.success(f"✅ API Ready (v{api_version})")
            else:
                st.sidebar.info("📋 FB Schema OK")
                # Show migration option
                with st.sidebar.expander("🔄 Enable API Features"):
                    st.write("""
                    **Current:** Basic Facebook schema

                    **Upgrade to:** API-ready schema with:
                    - Provider switching
                    - Rate limit tracking
                    - API credential storage
                    """)
                    if st.button("🚀 Upgrade Schema", key="sidebar_migrate"):
                        with st.spinner("Running migration..."):
                            success, msg = run_api_migration(selected_db)
                            if success:
                                st.success("✅ Migration complete!")
                                st.rerun()
                            else:
                                st.error(f"Migration failed: {msg}")
        elif schema_version == 'old':
            st.sidebar.warning("⚠️ Legacy Schema")
            with st.sidebar.expander("ℹ️ About Schema Versions"):
                st.write(f"""
                **Legacy Schema**: Original column names

                **To upgrade column names:**
                ```bash
                python3 schema_upgrade_v2.py --database {selected_db}
                ```

                **To add API support:**
                ```bash
                python3 migrate_for_api_support.py --database {selected_db}
                ```
                """)
        else:
            st.sidebar.error("❌ Unknown schema")

    st.session_state.selected_db = selected_db
    
    # Initialize database if it doesn't exist
    if not Path(selected_db).exists():
        processor.init_db(selected_db)
        st.sidebar.success(f"Created new database: {selected_db}")

    # Load data with schema detection
    df = load_data(selected_db)

    # Detect schema type for adaptive display
    schema_type, table_name, columns = detect_schema_type(selected_db)
    logger.debug(f"Sidebar schema detection: {schema_type} ({table_name})")

    # Calculate schema-aware stats
    stats = get_database_stats(df, schema_type)

    # Sidebar stats - schema-adaptive
    st.sidebar.markdown("---")

    if schema_type == 'marketplace':
        # Marketplace schema stats
        st.sidebar.success("🛒 **Marketplace Schema**")
        st.sidebar.metric("Total Records", stats.get('total_records', 0))
        st.sidebar.metric("Available", stats.get('available', 0))
        st.sidebar.metric("Sold", stats.get('sold', 0))
        if stats.get('ready_to_bump', 0) > 0:
            st.sidebar.metric("Ready to Bump", stats.get('ready_to_bump', 0))
    else:
        # Profile schema stats (default)
        if schema_type == 'profile':
            st.sidebar.info("👤 **Profile Schema**")
        st.sidebar.metric("Total Records", stats.get('total_records', 0))
        st.sidebar.metric("Successful", stats.get('successful', 0))
        st.sidebar.metric("With Images", stats.get('with_images', 0))

    # ========== QUICK ACTIONS (UX Improvement) ==========
    pending_count = stats.get('pending_enrichment', 0)
    if pending_count > 0:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚡ Quick Actions")
        st.sidebar.warning(f"**{pending_count} profiles** need Firefox enrichment to get images & full data")

        # Check Firefox status for quick action button
        if st.session_state.firefox_ready:
            if st.sidebar.button(
                f"🚀 Enrich All {pending_count} Pending",
                width="stretch",
                type="primary"
            ):
                enrich_with_browser_ui(selected_db, rate_limit=3.0)
                st.rerun()
        else:
            st.sidebar.button(
                f"🚀 Enrich All {pending_count} Pending",
                width="stretch",
                disabled=True,
                help="Log into Facebook in Firefox first"
            )
            st.sidebar.info("💡 Log into Facebook in Firefox to enable enrichment")

    # ========== MARKETPLACE SECTION ==========
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🛒 My Marketplace")

    # Load cached user data from database (for name/details)
    # But Firefox ready status is the source of truth for LOGIN state
    db_user = None
    try:
        if Path("marketplace.db").exists():
            conn = sqlite3.connect("marketplace.db")
            cur = conn.cursor()
            cur.execute("SELECT fb_id, fb_name, fb_username, profile_picture_url FROM logged_in_user WHERE id=1")
            row = cur.fetchone()
            conn.close()
            if row and (row[0] or row[1] or row[2]):  # Has ID, name, or username
                db_user = {
                    'fb_id': row[0],
                    'fb_name': row[1],
                    'fb_username': row[2],
                    'profile_picture_url': row[3]
                }
                # Update session state with DB data if we have it
                if st.session_state.fb_logged_in_user is None:
                    st.session_state.fb_logged_in_user = db_user

                # Also load cached items if not already loaded
                if not st.session_state.marketplace_items:
                    conn = sqlite3.connect("marketplace.db")
                    items_df = pd.read_sql("SELECT * FROM marketplace_items", conn)
                    conn.close()
                    st.session_state.marketplace_items = items_df.to_dict('records') if not items_df.empty else []
    except Exception:
        pass  # No cached data available

    # Firefox ready = user IS logged in to Facebook
    if st.session_state.firefox_ready:
        # Use session state user if available, otherwise use db_user, otherwise show as logged in
        user = st.session_state.fb_logged_in_user or db_user

        # Firefox ready = user IS logged in to Facebook
        # Show user info if we have it, otherwise show as "Logged In"
        if user:
            user_name = user.get('fb_name') or user.get('fb_username') or 'Facebook User'
        else:
            user_name = "Logged In"  # We know they're logged in (Firefox ready), just don't have name yet

        st.sidebar.success(f"👤 **{user_name}**")

        # Show items count
        item_count = len(st.session_state.marketplace_items)
        st.sidebar.metric("Listings", item_count, help="Number of items you're selling on Facebook Marketplace")

        # Scan button - always available when Firefox ready
        if st.sidebar.button(
            f"🔄 Scan My Listings",
            width="stretch",
            type="primary",
            help="Scan Facebook Marketplace for your selling items. Opens Firefox briefly.",
            key="sidebar_scan_listings"
        ):
            st.session_state.run_marketplace_scan = True
            st.rerun()

        st.sidebar.caption("👆 Click to scan, then see 🛒 Marketplace tab")
    else:
        st.sidebar.warning("🦊 Open Firefox & log into Facebook")
        st.sidebar.caption("Then refresh this page")

    # ========== PROVIDER STATUS (Future-proofing for API) ==========
    if PROVIDER_SUPPORT:
        st.sidebar.markdown("---")
        api_ready = st.session_state.get('api_ready', False)
        api_version = st.session_state.get('api_schema_version', 0)

        with st.sidebar.expander("🔌 Data Provider", expanded=False):
            if not api_ready:
                st.warning(f"⚠️ Limited Mode (Schema v{api_version})")
                st.caption("API features require schema upgrade")
                st.markdown("Go to **⚙️ Settings** tab to upgrade")
            else:
                try:
                    config = FacebookConfig.from_env()
                    provider_icons = {'scraper': '🌐', 'api': '📡', 'hybrid': '🔀'}
                    icon = provider_icons.get(config.provider_type, '❓')
                    st.success(f"{icon} **{config.provider_type.upper()}** Mode")
                    st.markdown(f"**Browser:** `{config.browser_type}`")

                    if config.has_api_credentials():
                        st.success("✅ API credentials configured")
                    else:
                        st.info("ℹ️ Using browser scraper (no API)")

                    st.markdown("""
                    ---
                    **Available Modes:**
                    - 🌐 Scraper (browser-based)
                    - 📡 API (Graph API)
                    - 🔀 Hybrid (API + fallback)
                    """)
                except Exception as e:
                    st.warning(f"Provider info unavailable: {e}")

    # Main tabs with session state persistence
    # Using st.radio for tab navigation to prevent jump-back behavior on rerun
    # See: https://discuss.streamlit.io/t/st-tabs-how-to-prevent-rerun-and-jumping-back-to-tab-1/30202
    TAB_LABELS = [
        "📤 Upload & Process",
        "📊 View Data",
        "✏️ Edit Records",
        "📈 Analytics",
        "💾 Export",
        "⚙️ Settings",
        "🛒 Marketplace",
        "🔧 API Config"
    ]

    # Tab navigation using st.radio (maintains state across reruns)
    def on_tab_change():
        """Callback when tab changes - logs for debugging per Rule 25"""
        new_tab = TAB_LABELS.index(st.session_state.tab_selector)
        old_tab = st.session_state.active_tab
        if new_tab != old_tab:
            logger.info(f"TAB CHANGE: {TAB_LABELS[old_tab]} → {TAB_LABELS[new_tab]}")
            st.session_state.active_tab = new_tab

    # Use st.radio styled as tabs for persistence
    selected_tab_label = st.radio(
        "Navigation",
        TAB_LABELS,
        index=st.session_state.active_tab,
        horizontal=True,
        key="tab_selector",
        on_change=on_tab_change,
        label_visibility="collapsed"
    )

    # Update active_tab from selection (in case callback didn't fire)
    current_tab_index = TAB_LABELS.index(selected_tab_label)
    if current_tab_index != st.session_state.active_tab:
        logger.debug(f"Syncing active_tab to {current_tab_index}")
        st.session_state.active_tab = current_tab_index

    st.markdown("---")  # Visual separator after tabs

    # Create placeholder containers for each tab (conditional rendering)
    # This replaces st.tabs() with explicit conditional blocks

    # ========== MARKETPLACE AUTO-ACTIONS ==========
    # Handle FB detection flag
    if st.session_state.get('run_fb_detection'):
        logger.info("EVENT: run_fb_detection triggered")
        st.session_state.run_fb_detection = False
        try:
            with st.spinner("Detecting Facebook login..."):
                is_logged_in, user_info = marketplace_scraper.check_facebook_login_status()
                if is_logged_in and user_info:
                    st.session_state.fb_logged_in_user = user_info
                    logger.info(f"FB detection SUCCESS: {user_info.get('fb_name', 'unknown')}")
                    st.toast(f"✅ Logged in as: {user_info.get('fb_name', 'Facebook User')}")
                else:
                    logger.warning("FB detection: Not logged in")
                    st.toast("⚠️ Not logged into Facebook", icon="⚠️")
        except Exception as e:
            logger.exception(f"FB detection ERROR: {e}")
            st.toast(f"Detection error: {e}", icon="❌")
        st.rerun()

    # Handle marketplace scan flag
    if st.session_state.get('run_marketplace_scan'):
        logger.info("EVENT: run_marketplace_scan triggered")
        st.session_state.run_marketplace_scan = False
        try:
            with st.spinner("Scanning your marketplace listings..."):
                user_info, items = marketplace_scraper.scrape_my_listings(
                    db_path="marketplace.db",
                    limit=50
                )
                logger.info(f"Marketplace scan returned: user={user_info.get('fb_name') if user_info else None}, items={len(items) if items else 0}")
                if user_info:
                    # Only update session if scan returned valid data
                    # Don't overwrite good data with "Facebook User" default
                    current_user = st.session_state.fb_logged_in_user
                    new_name = user_info.get('fb_name', '')

                    if new_name and new_name != 'Facebook User':
                        # Scan got a real name - use it
                        st.session_state.fb_logged_in_user = user_info
                        logger.info(f"Updated fb_logged_in_user: {new_name}")
                    elif current_user and current_user.get('fb_name') and current_user.get('fb_name') != 'Facebook User':
                        # Keep existing good name, but update items
                        logger.debug("Keeping existing user info")
                        pass  # Don't overwrite user info
                    else:
                        # No good data anywhere - use what we got
                        st.session_state.fb_logged_in_user = user_info

                    st.session_state.marketplace_items = items
                    logger.info(f"Marketplace items loaded: {len(items)}")
                    st.toast(f"✅ Found {len(items)} listings", icon="📦")
                else:
                    # Scan failed - DON'T clear existing login, just show error
                    logger.warning("Marketplace scan failed - no user_info returned")
                    st.toast("Could not access Facebook", icon="❌")
        except Exception as e:
            # Error - DON'T clear existing login
            logger.exception(f"Marketplace scan ERROR: {e}")
            st.toast(f"Scan error: {e}", icon="❌")
        st.rerun()

    # ========== PENDING PROFILES BANNER (UX Improvement) ==========
    pending_count = stats.get('pending_enrichment', 0)
    total_count = stats.get('total_records', 0)
    with_images = stats.get('with_images', 0)

    if pending_count > 0 and total_count > 0:
        missing_images = total_count - with_images
        pct_complete = ((total_count - pending_count) / total_count * 100) if total_count > 0 else 0

        st.info(f"""
        📊 **Data Completeness: {pct_complete:.0f}%** — {pending_count} of {total_count} profiles need browser enrichment

        | Status | Count | Notes |
        |--------|-------|-------|
        | ✅ Enriched | {stats.get('enriched', 0)} | Full data + images |
        | ⏳ Pending | {pending_count} | HTTP only, no images |
        | 📷 Missing Images | {missing_images} | Need browser enrichment |

        **👈 Use Quick Actions in sidebar** or go to **Upload & Process** tab → **Stage 2: Browser Enrichment**
        """)

    # ========== TAB 1: Upload & Process ==========
    if current_tab_index == 0:
        logger.debug("Rendering TAB 1: Upload & Process")
        st.header("Upload & Process Facebook Profile URLs")

        # Check Firefox readiness
        if st.session_state.firefox_ready is None:
            st.session_state.firefox_ready = check_firefox_ready()

        # Firefox status indicator
        col_status1, col_status2 = st.columns([3, 1])
        with col_status1:
            if st.session_state.firefox_ready:
                st.success("✅ Firefox Ready - Full enrichment available (uses your existing FB login)")
            else:
                st.warning("⚠️ Firefox profile not found - HTTP processing only")
        with col_status2:
            if st.button("🔄 Recheck", help="Check if Firefox profile is available for enrichment"):
                st.session_state.firefox_ready = check_firefox_ready()
                st.rerun()

        st.markdown("---")

        st.markdown("""
        **Instructions:**
        1. Paste URLs directly or upload a .txt file
        2. URLs should be Facebook marketplace profile URLs
        3. Choose processing mode and click the button
        """)

        # URL input methods
        col1, col2 = st.columns([2, 1])

        with col1:
            url_text = st.text_area(
                "Paste URLs here (one per line)",
                height=200,
                placeholder="https://www.facebook.com/marketplace/profile/123456789\nhttps://www.facebook.com/marketplace/profile/987654321",
                key="url_input_area"
            )

        with col2:
            uploaded_file = st.file_uploader(
                "Or upload .txt file",
                type=['txt'],
                help="Upload a text file with one URL per line"
            )

            st.markdown("**Processing Options**")
            with st.expander("⚙️ Advanced Settings"):
                rate_limit = st.slider(
                    "Rate Limit (seconds)",
                    0.5, 5.0, 1.0, 0.5,
                    help="Time between requests. Higher = safer but slower"
                )
                timeout = st.slider(
                    "Timeout (seconds)",
                    5, 60, 15, 5,
                    help="Max time to wait for each request"
                )

        # Collect URLs from both sources
        urls = []
        invalid_lines = []

        if url_text:
            for line in url_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                # Case-insensitive check for http/https
                if line.lower().startswith('http'):
                    urls.append(line)
                else:
                    invalid_lines.append(line)

        if uploaded_file:
            content = uploaded_file.read().decode('utf-8')
            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith('http'):
                    urls.append(line)
                else:
                    invalid_lines.append(line)

        # Remove duplicates
        urls = list(set(urls))

        # Show URL status
        if urls:
            st.success(f"✅ Found {len(urls)} valid URL(s) ready to process")

            with st.expander("📋 Preview URLs"):
                for i, url in enumerate(urls[:10], 1):
                    st.text(f"{i}. {url}")
                if len(urls) > 10:
                    st.text(f"... and {len(urls) - 10} more")
        else:
            st.warning("⚠️ No valid URLs found. Paste URLs above (must start with http:// or https://)")

        # Show invalid lines if any
        if invalid_lines:
            with st.expander(f"⚠️ {len(invalid_lines)} invalid line(s) ignored"):
                for line in invalid_lines[:5]:
                    st.text(f"❌ {line}")
                if len(invalid_lines) > 5:
                    st.text(f"... and {len(invalid_lines) - 5} more")

        st.markdown("---")
        st.subheader("Processing Mode")

        # Two-column layout for processing buttons
        col_http, col_browser = st.columns(2)

        with col_http:
            st.markdown("**Stage 1: HTTP Collection**")
            st.caption("Fast • Basic metadata • No login required")

            # Show button status
            button_disabled = st.session_state.processing or len(urls) == 0
            if button_disabled and len(urls) == 0:
                st.info("👆 Paste URLs above to enable processing")

            if st.button(
                "🚀 Process with HTTP",
                disabled=button_disabled,
                width="stretch",
                type="primary",
                help="Process URLs using HTTP requests only (no browser required)",
                key="http_process_button"
            ):
                logger.info(f"BUTTON: Process with HTTP - {len(urls)} URLs, db={selected_db}")
                # DEBUG: Show what we're processing
                st.info(f"🔍 DEBUG: Button clicked! Processing {len(urls)} URLs")
                st.write(f"Database: {selected_db}")
                st.write(f"Rate limit: {rate_limit}s")
                st.write(f"Timeout: {timeout}s")

                try:
                    # Process URLs
                    result = process_urls_ui(urls, selected_db, rate_limit, timeout)

                    # Show result
                    logger.info(f"HTTP processing complete: {result}")
                    st.success(f"✅ Processing complete! Result: {result}")

                    # Force refresh
                    st.rerun()

                except Exception as e:
                    logger.exception(f"HTTP processing FAILED: {e}")
                    st.error(f"❌ Processing failed: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        with col_browser:
            st.markdown("**Stage 2: Firefox Enrichment**")
            st.caption("Full data • Uses your existing Firefox profile (no special setup!)")

            if not st.session_state.firefox_ready:
                st.button(
                    "⚡ Enrich with Firefox",
                    disabled=True,
                    width="stretch",
                    help="Firefox profile not found. See setup instructions below."
                )

                with st.expander("🔧 Firefox Setup Instructions"):
                    st.markdown("""
                    **To enable Firefox enrichment:**

                    1. Open Firefox (your regular browser)
                    2. Log into Facebook at facebook.com
                    3. Click "🔄 Recheck" button above
                    4. Return here and click "Enrich with Firefox"

                    ✅ **No special setup needed!** Uses your existing Firefox profile.

                    **What Firefox enrichment provides:**
                    - Resolved usernames (e.g., `100000563858165` → `kristi.sutphin.9`)
                    - Real profile names
                    - Bio/description text
                    - Location data
                    - Profile pictures (downloaded locally)
                    """)
            else:
                if st.button(
                    "⚡ Enrich Pending Profiles",
                    disabled=st.session_state.processing,
                    width="stretch",
                    type="secondary"
                ):
                    logger.info(f"BUTTON: Enrich Pending Profiles - db={selected_db}")
                    enrich_with_browser_ui(selected_db, rate_limit=3.0)
                    st.rerun()

        if st.session_state.processing:
            st.warning("⏳ Processing in progress...")

    # ========== TAB 2: View Data ==========
    if current_tab_index == 1:
        logger.debug("Rendering TAB 2: View Data")
        st.header("View Profile Data")

        if df.empty:
            st.info("No data in database. Upload and process URLs in the 'Upload & Process' tab.")
        else:
            # ========== QUICK FILTER BUTTONS (UX Improvement) ==========
            pending_count = stats.get('pending_enrichment', 0)
            if pending_count > 0:
                st.markdown("#### 🔍 Quick Filters")
                qf_col1, qf_col2, qf_col3, qf_col4 = st.columns(4)
                with qf_col1:
                    show_pending = st.button(f"⏳ Show {pending_count} Pending", width="stretch")
                with qf_col2:
                    show_enriched = st.button(f"✅ Show Enriched ({stats.get('enriched', 0)})", width="stretch")
                with qf_col3:
                    show_no_images = st.button(f"📷 Without Images", width="stretch")
                with qf_col4:
                    show_all = st.button("📋 Show All", width="stretch")

                # Handle quick filter clicks
                if show_pending:
                    st.session_state['quick_filter'] = 'pending'
                elif show_enriched:
                    st.session_state['quick_filter'] = 'enriched'
                elif show_no_images:
                    st.session_state['quick_filter'] = 'no_images'
                elif show_all:
                    st.session_state['quick_filter'] = 'all'

                st.markdown("---")

            # Filters
            col1, col2, col3 = st.columns(3)

            # Apply quick filter if set
            quick_filter = st.session_state.get('quick_filter', 'all')

            with col1:
                status_options = ['All'] + list(df['enrichment_status'].dropna().unique())
                default_status = 0
                if quick_filter == 'pending' and 'pending' in status_options:
                    default_status = status_options.index('pending')
                elif quick_filter == 'enriched' and 'enriched' in status_options:
                    default_status = status_options.index('enriched')
                status_filter = st.selectbox("Enrichment Status", status_options, index=default_status)

            with col2:
                error_filter = st.selectbox("Error Status", ['All', 'Success Only', 'Errors Only'])

            with col3:
                image_options = ['All', 'With Images', 'Without Images']
                default_image = 0
                if quick_filter == 'no_images':
                    default_image = 2  # 'Without Images'
                image_filter = st.selectbox("Images", image_options, index=default_image)

            # Apply filters
            filtered_df = df.copy()

            if status_filter != 'All':
                filtered_df = filtered_df[filtered_df['enrichment_status'] == status_filter]

            if error_filter == 'Success Only':
                filtered_df = filtered_df[filtered_df['error'].isna()]
            elif error_filter == 'Errors Only':
                filtered_df = filtered_df[filtered_df['error'].notna()]

            if image_filter == 'With Images':
                filtered_df = filtered_df[filtered_df['browser_profile_pic_url'].notna()]
            elif image_filter == 'Without Images':
                filtered_df = filtered_df[filtered_df['browser_profile_pic_url'].isna()]

            st.info(f"Showing {len(filtered_df)} of {len(df)} records")

            # Column selection
            all_columns = list(df.columns)
            default_columns = ['id', 'input_url', 'profile_id', 'http_status',
                              'page_title', 'browser_profile_name', 'enrichment_status']
            default_columns = [col for col in default_columns if col in all_columns]

            selected_columns = st.multiselect(
                "Select Columns",
                all_columns,
                default=default_columns
            )

            if selected_columns:
                st.dataframe(filtered_df[selected_columns], width="stretch", height=500)

            # Detailed view
            st.markdown("---")
            st.subheader("Detailed Record View")

            if not filtered_df.empty:
                record_id = st.selectbox(
                    "Select Record ID",
                    filtered_df['id'].tolist()
                )

                record = filtered_df[filtered_df['id'] == record_id].iloc[0]

                col1, col2 = st.columns([1, 2])

                with col1:
                    # Display profile image
                    if pd.notna(record.get('browser_profile_pic_url')):
                        st.markdown("**Profile Picture:**")
                        try:
                            st.image(record['browser_profile_pic_url'], width=200)
                        except Exception as e:
                            logger.debug(f"Profile image load failed: {e}")
                            st.text("Image unavailable")

                with col2:
                    st.markdown("**Profile Details:**")
                    for col in record.index:
                        if pd.notna(record[col]) and record[col] != '':
                            st.text(f"{col}: {record[col]}")

    # ========== TAB 3: Edit Records ==========
    if current_tab_index == 2:
        logger.debug("Rendering TAB 3: Edit Records")
        st.header("Edit & Delete Records")

        if df.empty:
            st.info("No data to edit.")
        else:
            # Select record to edit
            record_id = st.selectbox(
                "Select Record ID to Edit/Delete",
                df['id'].tolist(),
                key='edit_record_id'
            )

            record = df[df['id'] == record_id].iloc[0]

            # Display current data
            st.subheader(f"Editing Record #{record_id}")

            col1, col2 = st.columns([1, 2])

            with col1:
                if pd.notna(record.get('browser_profile_pic_url')):
                    try:
                        st.image(record['browser_profile_pic_url'], width=150)
                    except Exception as e:
                        logger.debug(f"Profile image load failed: {e}")
                        st.text("Image unavailable")

            with col2:
                st.text(f"URL: {record['input_url']}")
                st.text(f"Profile ID: {record.get('profile_id', 'N/A')}")
                st.text(f"Status: {record.get('enrichment_status', 'N/A')}")

            st.markdown("---")

            # Edit form
            with st.form("edit_form"):
                st.markdown("**Edit Fields:**")

                col1, col2 = st.columns(2)

                with col1:
                    new_page_title = st.text_input(
                        "Page Title",
                        value=record.get('page_title', '') or ''
                    )
                    new_og_title = st.text_input(
                        "OG Title",
                        value=record.get('og_title', '') or ''
                    )
                    new_og_description = st.text_area(
                        "OG Description",
                        value=record.get('og_description', '') or ''
                    )

                with col2:
                    new_browser_name = st.text_input(
                        "Browser Profile Name",
                        value=record.get('browser_profile_name', '') or ''
                    )
                    new_browser_bio = st.text_area(
                        "Browser Bio",
                        value=record.get('browser_profile_bio', '') or ''
                    )
                    new_enrichment_status = st.selectbox(
                        "Enrichment Status",
                        ['pending', 'enriched', 'failed'],
                        index=['pending', 'enriched', 'failed'].index(record.get('enrichment_status', 'pending'))
                    )

                submitted = st.form_submit_button("💾 Save Changes")

                if submitted:
                    updates = {
                        'page_title': new_page_title,
                        'og_title': new_og_title,
                        'og_description': new_og_description,
                        'browser_profile_name': new_browser_name,
                        'browser_profile_bio': new_browser_bio,
                        'enrichment_status': new_enrichment_status
                    }

                    if processor.update_profile(selected_db, record_id, updates):
                        st.success("✅ Record updated successfully!")
                        load_data.clear()
                        st.rerun()
                    else:
                        st.error("❌ Failed to update record")

            # Delete button
            st.markdown("---")
            st.markdown("**Danger Zone:**")

            if st.button("🗑️ Delete This Record", type="secondary", help="Permanently delete this profile record from database"):
                logger.warning(f"BUTTON: Delete record {record_id} from {selected_db}")
                if processor.delete_profile(selected_db, record_id):
                    logger.info(f"DELETE SUCCESS: record {record_id}")
                    st.success("✅ Record deleted successfully!")
                    load_data.clear()
                    st.rerun()
                else:
                    logger.error(f"DELETE FAILED: record {record_id}")
                    st.error("❌ Failed to delete record")

    # ========== TAB 4: Analytics ==========
    if current_tab_index == 3:
        logger.debug("Rendering TAB 4: Analytics")
        st.header("Analytics & Insights")

        if df.empty:
            st.info("No data for analytics.")
        else:
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Records", stats['total_records'])
            col2.metric("Success Rate", f"{stats['successful']/stats['total_records']*100:.1f}%")
            col3.metric("With Images", stats['with_images'])
            col4.metric("Pending Enrichment", stats['pending_enrichment'])

            st.markdown("---")

            # Charts
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("HTTP Status Distribution")
                if 'http_status' in df.columns:
                    status_counts = df['http_status'].value_counts()
                    st.bar_chart(status_counts)

            with col2:
                st.subheader("Enrichment Status")
                if 'enrichment_status' in df.columns:
                    enrichment_counts = df['enrichment_status'].value_counts()
                    st.bar_chart(enrichment_counts)

            # Timeline
            st.markdown("---")
            st.subheader("Processing Timeline")
            if 'fetched_at' in df.columns:
                df_timeline = df.copy()
                df_timeline['fetched_at'] = pd.to_datetime(df_timeline['fetched_at'], errors='coerce')
                df_timeline = df_timeline.dropna(subset=['fetched_at'])

                if not df_timeline.empty:
                    df_timeline['date'] = df_timeline['fetched_at'].dt.date
                    timeline_counts = df_timeline.groupby('date').size()
                    st.line_chart(timeline_counts)

    # ========== TAB 5: Export ==========
    if current_tab_index == 4:
        logger.debug("Rendering TAB 5: Export")
        st.header("Export Data")

        if df.empty:
            st.info("No data to export.")
        else:
            st.markdown("Export your data in various formats, optionally including profile images.")

            # Export options
            col1, col2 = st.columns(2)

            with col1:
                export_format = st.radio(
                    "Export Format",
                    ['CSV', 'JSON', 'Excel', 'Text (.txt)', 'SQL (.sql)', 'ZIP with Images']
                )

            with col2:
                include_all = st.checkbox("Include all records", value=True)
                if not include_all:
                    st.info("Will export only filtered data from 'View Data' tab")

            # Prepare export data
            export_df = df if include_all else filtered_df if 'filtered_df' in locals() else df

            st.markdown("---")
            st.subheader("Export Preview")
            st.write(f"**Records to export:** {len(export_df)}")
            st.write(f"**Columns:** {len(export_df.columns)}")
            st.dataframe(export_df.head(3), width="stretch")

            st.markdown("---")

            # Export buttons
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

            if export_format == 'CSV':
                csv = export_df.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"fb_profiles_{timestamp}.csv",
                    mime="text/csv"
                )

            elif export_format == 'JSON':
                json_str = export_df.to_json(orient='records', indent=2)
                st.download_button(
                    label="📥 Download JSON",
                    data=json_str,
                    file_name=f"fb_profiles_{timestamp}.json",
                    mime="application/json"
                )

            elif export_format == 'Excel':
                try:
                    buffer = io.BytesIO()
                    export_df.to_excel(buffer, index=False, engine='openpyxl')
                    st.download_button(
                        label="📥 Download Excel",
                        data=buffer.getvalue(),
                        file_name=f"fb_profiles_{timestamp}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except ImportError:
                    st.error("Install openpyxl: pip install openpyxl")

            elif export_format == 'Text (.txt)':
                from export_functionality import create_txt_download
                txt_data = create_txt_download(export_df)
                st.download_button(
                    label="📥 Download TXT",
                    data=txt_data,
                    file_name=f"fb_profiles_{timestamp}.txt",
                    mime="text/plain"
                )
                with st.expander("📄 Preview TXT"):
                    preview = txt_data[:1500] + "\n..." if len(txt_data) > 1500 else txt_data
                    st.code(preview, language="text")

            elif export_format == 'SQL (.sql)':
                from export_functionality import create_sql_download
                sql_data = create_sql_download(export_df, table_name="facebook_profiles")
                st.download_button(
                    label="📥 Download SQL",
                    data=sql_data,
                    file_name=f"fb_profiles_{timestamp}.sql",
                    mime="text/plain"
                )
                with st.expander("💾 Preview SQL"):
                    preview = sql_data[:1500] + "\n..." if len(sql_data) > 1500 else sql_data
                    st.code(preview, language="sql")

            elif export_format == 'ZIP with Images':
                st.info("Creating ZIP file with data and images...")

                # Create ZIP
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    # Add CSV data
                    csv_data = export_df.to_csv(index=False)
                    zf.writestr('profiles.csv', csv_data)

                    # Add JSON data
                    json_data = export_df.to_json(orient='records', indent=2)
                    zf.writestr('profiles.json', json_data)

                    # Add images from local storage first
                    images_dir = Path('profile_images')
                    local_images_added = 0
                    if images_dir.exists():
                        for img_file in images_dir.glob('*'):
                            if img_file.is_file():
                                zf.write(img_file, f'images/{img_file.name}')
                                local_images_added += 1

                    # Download and add images from URLs (for profiles without local images)
                    downloaded_images = 0
                    progress_text = st.empty()

                    for idx, row in export_df.iterrows():
                        # Check if we already have local image
                        profile_id = row.get('profile_id', row['id'])
                        has_local = any(images_dir.glob(f"{profile_id}.*")) if images_dir.exists() else False

                        if not has_local and pd.notna(row.get('browser_profile_pic_url')):
                            progress_text.text(f"Downloading image {downloaded_images + 1}...")
                            try:
                                response = requests.get(row['browser_profile_pic_url'], timeout=10)
                                if response.status_code == 200:
                                    # Determine file extension
                                    content_type = response.headers.get('content-type', '')
                                    if 'jpeg' in content_type or 'jpg' in content_type:
                                        ext = 'jpg'
                                    elif 'png' in content_type:
                                        ext = 'png'
                                    elif 'gif' in content_type:
                                        ext = 'gif'
                                    else:
                                        ext = 'jpg'

                                    img_filename = f"images/{profile_id}.{ext}"
                                    zf.writestr(img_filename, response.content)
                                    downloaded_images += 1
                            except Exception as e:
                                logging.error(f"Failed to download image for {profile_id}: {e}")

                    progress_text.empty()

                    total_images = local_images_added + downloaded_images

                    # Add README
                    readme = f"""Facebook Profile Export
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Contents:
- profiles.csv: Profile data in CSV format
- profiles.json: Profile data in JSON format
- images/: Profile pictures ({total_images} images)
  - From local storage: {local_images_added}
  - Downloaded from URLs: {downloaded_images}

Total Records: {len(export_df)}

Image Sources:
- Local images are from browser enrichment (stored in profile_images/)
- Downloaded images are fetched from browser_profile_pic_url column
"""
                    zf.writestr('README.txt', readme)

                st.success(f"✅ ZIP created with {total_images} images ({local_images_added} local + {downloaded_images} downloaded)")

                st.download_button(
                    label="📥 Download ZIP",
                    data=zip_buffer.getvalue(),
                    file_name=f"fb_profiles_{timestamp}.zip",
                    mime="application/zip"
                )

    # ========== TAB 6: Settings & API Config ==========
    if current_tab_index == 5:
        logger.debug("Rendering TAB 6: Settings & API Config")
        st.header("⚙️ Settings & API Configuration")

        # =================================================================
        # UNIFIED BLOCKING BANNER (per ChatGPT UX directive)
        # Single, deduplicated status message at top
        # =================================================================
        current_token = marketplace_scraper.get_access_token()
        current_catalog = marketplace_scraper.get_catalog_id()
        api = marketplace_scraper.get_facebook_api()
        api_status = api.get_api_status()

        blocking_issues = []
        if not current_token:
            blocking_issues.append(("TOKEN_MISSING", "Access token not configured"))
        elif not api_status.get('api_available', False):
            blocking_issues.append(("TOKEN_INVALID", "Token validation failed"))

        if current_token and api_status.get('api_available') and not current_catalog:
            blocking_issues.append(("CATALOG_MISSING", "Catalog ID not configured"))
        elif current_token and api_status.get('api_available') and current_catalog and not api_status.get('catalog_available'):
            blocking_issues.append(("CATALOG_INVALID", "Catalog access failed"))

        # Display single blocking banner
        if blocking_issues:
            primary_issue = blocking_issues[0]
            remaining = len(blocking_issues) - 1

            if primary_issue[0] in ("TOKEN_MISSING", "TOKEN_INVALID"):
                st.error(f"🚫 **Operations Blocked:** {primary_issue[1]}" +
                        (f" (+{remaining} more)" if remaining > 0 else "") +
                        " — Configure below to enable API access")
            else:
                st.warning(f"⚠️ **Limited Mode:** {primary_issue[1]}" +
                          (f" (+{remaining} more)" if remaining > 0 else ""))

            logger.info(f"API Config blocking issues: {[b[0] for b in blocking_issues]}")
        else:
            st.success("✅ **API Ready** — All systems operational")
            logger.info("API Config: All checks passed")

        st.markdown("---")

        # Get API readiness status
        api_ready = st.session_state.get('api_ready', False)
        api_version = st.session_state.get('api_schema_version', 0)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🔌 Data Provider Configuration")

            # Check schema status first
            if not api_ready:
                st.warning(f"⚠️ Database Schema: v{api_version} (API features require v5+)")
                st.markdown("""
                **Current database needs migration to enable:**
                - 🔀 Provider switching (scraper/API/hybrid)
                - 📊 Rate limit tracking
                - 🔑 API credential storage
                - 📈 Usage analytics
                """)

                st.markdown("---")
                if st.button("🚀 Upgrade Database Schema", type="primary", key="settings_migrate"):
                    with st.spinner("Running migration..."):
                        success, msg = run_api_migration(selected_db)
                        if success:
                            st.success("✅ Migration complete! Refreshing...")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Migration failed: {msg}")

                st.markdown("---")
                st.caption("Or run manually:")
                st.code(f"python3 migrate_for_api_support.py --database {selected_db}", language="bash")

            elif PROVIDER_SUPPORT:
                try:
                    config = FacebookConfig.from_env()

                    # Provider status with visual feedback
                    st.markdown("**Current Provider:**")
                    provider_icons = {
                        'scraper': '🌐',
                        'api': '📡',
                        'hybrid': '🔀'
                    }
                    st.success(f"{provider_icons.get(config.provider_type, '❓')} **{config.provider_type.upper()}** Mode Active")

                    # Provider selector
                    st.markdown("---")
                    st.markdown("**Switch Provider:**")
                    current_idx = ['scraper', 'api', 'hybrid'].index(config.provider_type) if config.provider_type in ['scraper', 'api', 'hybrid'] else 0

                    provider_choice = st.radio(
                        "Select data source:",
                        options=['scraper', 'api', 'hybrid'],
                        index=current_idx,
                        format_func=lambda x: {
                            'scraper': '🌐 Browser Scraper (No API needed)',
                            'api': '📡 Facebook Graph API (Requires credentials)',
                            'hybrid': '🔀 Hybrid (API + Scraper fallback)'
                        }[x],
                        key="provider_selector"
                    )

                    if provider_choice != config.provider_type:
                        st.info(f"To switch to **{provider_choice}**, set: `export DATA_PROVIDER={provider_choice}`")

                    # Current config display
                    st.markdown("---")
                    with st.expander("📋 Full Configuration"):
                        st.json({
                            "provider_type": config.provider_type,
                            "browser_type": config.browser_type,
                            "scraper_enabled": config.scraper_enabled,
                            "cache_enabled": config.cache_enabled,
                            "cache_ttl_seconds": config.cache_ttl,
                            "max_requests_per_minute": config.max_requests_per_minute,
                            "api_credentials_configured": config.has_api_credentials(),
                        })

                    # API Credentials section
                    if provider_choice in ['api', 'hybrid']:
                        st.markdown("---")
                        st.markdown("**🔑 API Credentials:**")
                        if config.has_api_credentials():
                            st.success("✅ API credentials configured")
                        else:
                            st.warning("⚠️ No API credentials")
                            st.code("""
# Set these environment variables:
export FACEBOOK_APP_ID=your_app_id
export FACEBOOK_APP_SECRET=your_secret
export FACEBOOK_ACCESS_TOKEN=your_token
                            """, language="bash")

                except Exception as e:
                    st.error(f"Provider error: {e}")
            else:
                st.warning("Provider support not available")
                st.info("Install data_providers.py and provider_manager.py for API support")

        with col2:
            st.subheader("🔑 Facebook API Access")

            st.markdown("""
            **Connect via Facebook Graph API for faster, more reliable access.**

            When API is configured, the tool will use it instead of browser automation.
            """)

            # Load current token status
            current_token = marketplace_scraper.get_access_token()
            api = marketplace_scraper.get_facebook_api()

            if api.api_available:
                st.success("✅ Facebook API Connected")
                config = marketplace_scraper.load_fb_config()
                if config.get('fb_name'):
                    st.info(f"👤 Connected as: **{config.get('fb_name')}**")

                # Token Health Indicator (traffic light)
                try:
                    token_health = marketplace_scraper.get_token_health(current_token)
                    health_status = token_health.get_status()

                    health_emoji = health_status.get('health_emoji', '⚪')
                    health_level = health_status.get('health', 'UNKNOWN')

                    st.markdown(f"**Token Health:** {health_emoji} {health_level}")

                    # Show warnings
                    for warning in health_status.get('warnings', []):
                        st.warning(f"⚠️ {warning}")

                    # Show critical issues
                    for issue in health_status.get('issues', []):
                        st.error(f"❌ {issue}")

                    # Show token expiration
                    if health_status.get('expires_at'):
                        st.caption(f"Token expires: {health_status.get('expires_at')}")

                except Exception as e:
                    st.caption(f"Could not check token health: {e}")
            else:
                st.warning("⚠️ API not configured")

            # Token input (no instructions - link to docs only)
            st.markdown("---")
            col_input, col_help = st.columns([4, 1])
            with col_input:
                new_token = st.text_input(
                    "Access Token",
                    value="",
                    type="password",
                    placeholder="Paste token from Graph API Explorer...",
                )
            with col_help:
                st.link_button("Get Token →", "https://developers.facebook.com/tools/explorer/")

            col_test, col_save, col_remove = st.columns(3)
            with col_test:
                if st.button("🧪 Test", disabled=not new_token):
                    is_valid, result = marketplace_scraper.test_access_token(new_token)
                    if is_valid:
                        st.success(f"✅ {result.get('fb_name')}")
                    else:
                        st.error(f"❌ {result}")
            with col_save:
                if st.button("💾 Save", disabled=not new_token, type="primary"):
                    is_valid, result = marketplace_scraper.test_access_token(new_token)
                    if is_valid:
                        marketplace_scraper.set_access_token(new_token)
                        config = marketplace_scraper.load_fb_config()
                        config.update(result)
                        marketplace_scraper.save_fb_config(config)
                        st.rerun()
                    else:
                        st.error(f"❌ {result}")
            with col_remove:
                if current_token and st.button("🗑️ Remove"):
                    config = marketplace_scraper.load_fb_config()
                    config.pop('access_token', None)
                    marketplace_scraper.save_fb_config(config)
                    st.rerun()

            # ========== PRODUCT CATALOG CONFIGURATION ==========
            st.markdown("---")
            st.subheader("📦 Product Catalog (Commerce Manager)")

            st.markdown("""
            **For Marketplace API access**, you need a Product Catalog in Commerce Manager.
            This is the official way to manage Marketplace listings via API.
            """)

            current_catalog = marketplace_scraper.get_catalog_id()
            api = marketplace_scraper.get_facebook_api()

            # Status display
            if api.catalog_available:
                st.success(f"✅ Catalog Connected: `{current_catalog}`")

                # Show catalog capabilities
                try:
                    caps = marketplace_scraper.probe_catalog(current_catalog)
                    cap_status = caps.get_status()

                    if cap_status.get('probed'):
                        col_cap1, col_cap2 = st.columns(2)
                        with col_cap1:
                            st.caption(f"**Name:** {cap_status.get('name', 'Unknown')}")
                            st.caption(f"**Vertical:** {cap_status.get('vertical', 'commerce')}")
                        with col_cap2:
                            st.caption(f"**Products:** {cap_status.get('product_count', 0)}")
                            capabilities = cap_status.get('capabilities', {})
                            if capabilities.get('can_read_products'):
                                st.caption("✅ Can read products")
                            if capabilities.get('supports_price'):
                                st.caption("✅ Supports pricing")
                except Exception as e:
                    st.caption(f"Could not probe catalog: {e}")

            elif current_catalog:
                st.warning(f"⚠️ Catalog ID set but not accessible: `{current_catalog}`")
            else:
                st.info("ℹ️ No catalog configured")

            # Fetch available catalogs button
            if api.api_available:
                with st.expander("🔍 Find My Catalogs"):
                    if st.button("Fetch Available Catalogs", key="fetch_catalogs"):
                        with st.spinner("Fetching catalogs from Commerce Manager..."):
                            catalogs = marketplace_scraper.get_available_catalogs()
                            if catalogs:
                                st.success(f"Found {len(catalogs)} catalog(s):")
                                for cat in catalogs:
                                    col_info, col_use = st.columns([3, 1])
                                    with col_info:
                                        st.write(f"**{cat.get('name', 'Unnamed')}**")
                                        st.caption(f"ID: `{cat.get('id')}` | Products: {cat.get('product_count', 0)}")
                                    with col_use:
                                        if st.button("Use", key=f"use_cat_{cat.get('id')}"):
                                            marketplace_scraper.set_catalog_id(cat.get('id'))
                                            st.success("Catalog set!")
                                            st.rerun()
                            else:
                                st.warning("No catalogs found. Create one in Commerce Manager.")
                                st.markdown("[Open Commerce Manager](https://business.facebook.com/commerce)")

            # Manual catalog ID input
            new_catalog_id = st.text_input(
                "Catalog ID",
                value=current_catalog or "",
                placeholder="Enter your Product Catalog ID...",
                help="Your Facebook Product Catalog ID from Commerce Manager"
            )

            col_test_cat, col_save_cat = st.columns(2)
            with col_test_cat:
                if st.button("🧪 Test Catalog", disabled=not new_catalog_id, key="test_catalog"):
                    token = marketplace_scraper.get_access_token()
                    if not token:
                        st.error("Set an access token first")
                    else:
                        with st.spinner("Testing catalog access..."):
                            is_valid, result = marketplace_scraper.test_catalog_access(token, new_catalog_id)
                            if is_valid:
                                st.success(f"✅ Valid! Name: {result.get('name')}, Products: {result.get('product_count', 0)}")
                            else:
                                st.error(f"❌ Cannot access: {result}")

            with col_save_cat:
                if st.button("💾 Save Catalog", disabled=not new_catalog_id, type="primary", key="save_catalog"):
                    token = marketplace_scraper.get_access_token()
                    if not token:
                        st.error("Set an access token first")
                    else:
                        with st.spinner("Saving..."):
                            is_valid, result = marketplace_scraper.test_catalog_access(token, new_catalog_id)
                            if is_valid:
                                marketplace_scraper.set_catalog_id(new_catalog_id)
                                st.success(f"✅ Saved! Catalog: {result.get('name')}")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ Cannot save invalid catalog: {result}")

            # Test API button
            if api.catalog_available:
                st.markdown("---")
                if st.button("🧪 Test Catalog Products API", key="test_products_api"):
                    with st.spinner("Fetching products from catalog..."):
                        products = api.get_catalog_products(limit=5)
                        if products:
                            st.success(f"✅ Found {len(products)} products")
                            st.json(products[:3])  # Show first 3
                        else:
                            st.warning("No products found in catalog")

            with st.expander("📋 How to set up Commerce Manager"):
                st.markdown("""
                1. Go to [Business Manager](https://business.facebook.com)
                2. Navigate to **Commerce Manager**
                3. Create a **Product Catalog** if you don't have one
                4. Copy the **Catalog ID** from the catalog settings
                5. Paste it above and save

                **Required Permissions:**
                - `catalog_management` - Read/write product catalogs
                - `business_management` - Manage business assets

                **Note:** This is the official way to manage Marketplace listings via API.
                Personal Marketplace listings are NOT accessible via API.
                """)

            # Meta Support Debug Bundle Export (3.2)
            st.markdown("---")
            st.subheader("🔧 Troubleshooting & Support")

            st.markdown("""
            If you're having issues with the Meta API, you can export a debug bundle
            for Meta Support tickets. This bundle contains:
            - App ID, Business ID, Catalog ID
            - Token scopes (NOT the token itself)
            - Recent API call history with error codes
            - Rate limit state
            """)

            col_bundle1, col_bundle2 = st.columns(2)
            with col_bundle1:
                if st.button("📦 Export Support Bundle", help="Generate a support bundle for Meta tickets"):
                    try:
                        commerce_api = marketplace_scraper.get_commerce_api()
                        bundle_path = commerce_api.save_support_bundle()
                        st.success(f"✅ Bundle saved to: `{bundle_path}`")

                        # Show bundle preview
                        with open(bundle_path, 'r') as f:
                            bundle_data = json.load(f)
                        with st.expander("Preview Bundle Contents"):
                            st.json(bundle_data)
                    except Exception as e:
                        st.error(f"Failed to export bundle: {e}")

            with col_bundle2:
                if st.button("📋 View Audit Log", help="View recent API call history"):
                    try:
                        audit_log = marketplace_scraper.get_audit_logger()
                        recent = audit_log.get_recent_entries(20)
                        if recent:
                            st.markdown("**Recent API Calls:**")
                            for entry in recent[:10]:
                                status_icon = "✅" if entry.get("status_code") == 200 else "❌"
                                st.text(f"{status_icon} {entry.get('method')} {entry.get('endpoint')} [{entry.get('status_code')}]")
                        else:
                            st.info("No API calls logged yet")
                    except Exception as e:
                        st.error(f"Failed to load audit log: {e}")

            st.markdown("---")
            st.subheader("📊 Database Configuration")

            # Show provider_config table if it exists
            try:
                conn = sqlite3.connect(selected_db)
                cur = conn.cursor()

                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='provider_config'")
                if cur.fetchone():
                    cur.execute("SELECT config_key, config_value, description FROM provider_config ORDER BY config_key")
                    config_rows = cur.fetchall()

                    st.markdown("**Provider Configuration (from database):**")
                    for key, value, desc in config_rows:
                        st.text(f"{key}: {value}")
                        if desc:
                            st.caption(desc)
                else:
                    st.info("Run `python migrate_for_api_support.py` to add API support tables")

                conn.close()
            except Exception as e:
                st.warning(f"Could not load database config: {e}")

            st.markdown("---")
            st.subheader("📖 Architecture")
            st.markdown("""
            **Future-Proofing Strategy:**

            | Phase | Status | Description |
            |-------|--------|-------------|
            | 1. Scraper | ✅ Active | Browser automation |
            | 2. Hybrid | 🔜 Ready | API + Scraper fallback |
            | 3. Full API | 🔮 Planned | When FB opens access |

            **Key Files:**
            - `data_providers.py` - Provider interface
            - `provider_manager.py` - Provider lifecycle
            - `migrate_for_api_support.py` - DB migration
            - `FACEBOOK_API_ARCHITECTURE.md` - Full docs
            """)

    # ========== TAB 7: Marketplace ==========
    if current_tab_index == 6:
        logger.debug("Rendering TAB 7: Marketplace")
        st.header("🛒 My Marketplace Listings")

        # Compliance gate - show diagnostic status (not instructions)
        mp_diag = run_live_diagnostics()
        if not mp_diag["can_proceed"] and COMMERCE_API_AVAILABLE:
            st.warning(f"⚠️ **API Limited** — {mp_diag['failed']} check(s) failed. Browser scanning available. → 🔧 API Config")

        user = st.session_state.fb_logged_in_user
        items = st.session_state.marketplace_items

        if not st.session_state.firefox_ready:
            st.warning("🦊 Firefox required for marketplace features")
            st.info("Open Firefox, log into Facebook, then refresh this page")
        elif not user:
            st.info("🔍 Detecting your Facebook login...")
            if st.button("🔄 Detect Now", type="primary", help="Open Firefox to detect your Facebook login"):
                st.session_state.run_fb_detection = True
                st.rerun()
        else:
            # User is logged in - show their info and listings
            user_name = user.get('fb_name') or user.get('fb_username') or 'Facebook User'

            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.success(f"👤 Logged in as: **{user_name}**")
            with col2:
                st.metric("Total Listings", len(items))
            with col3:
                if st.button("🔄 Refresh Listings", type="secondary", help="Rescan Facebook Marketplace for your current listings"):
                    st.session_state.run_marketplace_scan = True
                    st.rerun()

            # UX ENFORCEMENT: API config check and data completeness warning
            import os
            fb_api_configured = bool(os.environ.get('FB_ACCESS_TOKEN')) and bool(os.environ.get('FB_CATALOG_ID'))

            # Track historical baseline in session state
            if 'max_listings_seen' not in st.session_state:
                st.session_state.max_listings_seen = len(items)
            else:
                st.session_state.max_listings_seen = max(st.session_state.max_listings_seen, len(items))

            current_count = len(items)
            historical_max = st.session_state.max_listings_seen

            # Show warning if data may be incomplete
            if not fb_api_configured:
                if current_count < historical_max:
                    st.warning(
                        f"⚠️ **Incomplete Data Warning**: Found {current_count} listings, "
                        f"but previously saw {historical_max}. Facebook's lazy loading may have "
                        f"missed items. Configure API credentials for complete data. "
                        f"See `.env.example` for setup instructions."
                    )
                elif current_count < 10:
                    st.info(
                        "ℹ️ **API Not Configured**: DOM scraping is active. For reliable, "
                        "complete listing data, configure `FB_ACCESS_TOKEN` and `FB_CATALOG_ID` "
                        "environment variables. See `.env.example`."
                    )

            st.markdown("---")

            if not items:
                st.info("No listings found. Click 'Refresh Listings' to scan your marketplace.")
                if st.button("📦 Scan My Listings Now", type="primary", width="stretch", help="Open Firefox and scan your Facebook Marketplace selling items"):
                    st.session_state.run_marketplace_scan = True
                    st.rerun()
            else:
                # Create DataFrame from items for stats
                items_df = pd.DataFrame(items)

                # Metrics row (matching dashboard.py)
                mp_stats = get_database_stats(items_df, 'marketplace')
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Total", mp_stats.get('total_records', 0))
                col2.metric("Available", mp_stats.get('available', 0))
                col3.metric("Sold", mp_stats.get('sold', 0))
                col4.metric("Drafts", mp_stats.get('draft', 0))
                col5.metric("With Prices", mp_stats.get('with_price', 0))

                st.markdown("---")

                # Display listings header
                st.subheader(f"📦 Your {len(items)} Listings")

                # View mode toggle
                view_mode = st.radio("View", ["📋 Table", "🃏 Cards"], horizontal=True, label_visibility="collapsed")

                # Filter options - RESTORED: search + status + sort
                col1, col2, col3 = st.columns(3)
                with col1:
                    search = st.text_input("🔍 Search", placeholder="Type to filter by title...", key="mp_search", label_visibility="collapsed")
                with col2:
                    # Status dropdown (instant filter, no Enter needed)
                    status_options = ["All"] + sorted(items_df['status'].dropna().unique().tolist()) if 'status' in items_df.columns else ["All"]
                    status_filter = st.selectbox("📋 Status", status_options, key="mp_status_filter", label_visibility="collapsed")
                with col3:
                    sort_by = st.selectbox("Sort by", ["Newest", "Price (Low)", "Price (High)", "Title"], key="mp_sort")

                # Apply search filter (requires Enter - Streamlit limitation)
                if search and not items_df.empty:
                    items_df = items_df[items_df['title'].str.contains(search, case=False, na=False)]

                # Apply status filter (instant, no Enter needed)
                if status_filter and status_filter != "All" and not items_df.empty:
                    items_df = items_df[items_df['status'] == status_filter]

                # Apply sorting (RESTORED)
                if not items_df.empty and sort_by:
                    if sort_by == "Newest" and 'created_at' in items_df.columns:
                        items_df = items_df.sort_values('created_at', ascending=False)
                    elif sort_by == "Price (Low)" and 'price' in items_df.columns:
                        # Extract numeric price for sorting
                        items_df['_price_num'] = items_df['price'].str.extract(r'(\d+\.?\d*)').astype(float)
                        items_df = items_df.sort_values('_price_num', ascending=True)
                    elif sort_by == "Price (High)" and 'price' in items_df.columns:
                        items_df['_price_num'] = items_df['price'].str.extract(r'(\d+\.?\d*)').astype(float)
                        items_df = items_df.sort_values('_price_num', ascending=False)
                    elif sort_by == "Title" and 'title' in items_df.columns:
                        items_df = items_df.sort_values('title', ascending=True)

                st.info(f"Showing {len(items_df)} of {len(items)} listings")

                if view_mode == "📋 Table":
                    # TABLE VIEW - with row selection and detailed listing panel
                    if not items_df.empty:
                        # Select columns to display
                        display_cols = ['item_id', 'title', 'price', 'status', 'bump_count', 'days_until_next_bump']
                        available_cols = [c for c in display_cols if c in items_df.columns]

                        # Enable row selection - clicking a row selects it
                        selection_event = st.dataframe(
                            items_df[available_cols],
                            width="stretch",
                            height=400,
                            hide_index=True,
                            on_select="rerun",
                            selection_mode="single-row",
                            key="mp_table_selection"
                        )

                        # Detailed view for selected item
                        st.markdown("---")
                        st.subheader("📄 Listing Details")

                        # Get selected row from dataframe click, or use selectbox as fallback
                        selected_rows = selection_event.selection.rows if selection_event.selection.rows else []

                        # Build lookup dict for format_func: item_id -> display string with title
                        id_to_title = {
                            row['item_id']: f"{format_display_title(row.get('title', ''), row['item_id'])} ({row['item_id']})"
                            for _, row in items_df.iterrows()
                        }

                        # If row clicked in table, use that; otherwise show selectbox
                        if selected_rows:
                            selected_id = items_df.iloc[selected_rows[0]]['item_id']
                            st.caption(f"📍 Selected from table: {id_to_title.get(selected_id, selected_id)}")
                        else:
                            selected_id = st.selectbox(
                                "Select Listing",
                                items_df['item_id'].tolist(),
                                format_func=lambda x: id_to_title.get(x, str(x)),
                                key="mp_selected_item"
                            )
                        if selected_id:
                            item = items_df[items_df['item_id'] == selected_id].iloc[0].to_dict()

                            col1, col2 = st.columns([1, 2])
                            with col1:
                                # Show image (RESTORED)
                                local_img = item.get('local_image_path') or item.get('local_image_paths')
                                remote_img = item.get('image_url') or item.get('image_urls')
                                # Also check marketplace_images folder
                                mp_img = Path(f"marketplace_images/{item.get('item_id', '')}.jpg")

                                if local_img and Path(str(local_img)).exists():
                                    st.image(local_img, width="stretch")
                                elif mp_img.exists():
                                    st.image(str(mp_img), width="stretch")
                                elif remote_img:
                                    try:
                                        st.image(remote_img, width="stretch")
                                    except Exception as e:
                                        logger.debug(f"Remote image load failed: {e}")
                                        st.info("📷 No image")
                                else:
                                    st.info("📷 No image available")

                            with col2:
                                # Use helper functions for consistent display
                                display_title = format_display_title(item.get('title', ''), item.get('item_id', ''))
                                display_price = format_display_price(item.get('price'))
                                st.markdown(f"**Title:** {display_title}")
                                st.markdown(f"**Price:** {display_price}")

                                # Status with badge (RESTORED)
                                status = item.get('status', 'available')
                                status_badges = {
                                    'available': '🟢 Available',
                                    'pending': '🟡 Pending',
                                    'sold': '🔴 Sold',
                                    'draft': '⚪ Draft'
                                }
                                st.markdown(f"**Status:** {status_badges.get(status, status)}")

                                # Bump info (RESTORED) - Fixed NaN handling per Rule 43
                                bump_count = item.get('bump_count', 0)
                                max_bumps = item.get('max_bump_count', 5)
                                days_next = item.get('days_until_next_bump')
                                if bump_count is not None:
                                    bump_text = f"{bump_count}/{max_bumps} bumps used"
                                    # Use pd.notna() to properly check for NaN values
                                    if pd.notna(days_next):
                                        if days_next <= 0:
                                            bump_text += " (**Ready to bump!**)"
                                        else:
                                            bump_text += f" (next in {int(days_next)} days)"
                                    st.markdown(f"**Bumps:** {bump_text}")

                                st.markdown(f"**Item ID:** {item.get('item_id', 'N/A')}")
                                if item.get('item_url'):
                                    st.link_button("🔗 View on Facebook", item['item_url'])
                    else:
                        st.info("No listings match your search/filter")
                else:
                    # CARDS VIEW - Visual grid with thumbnails using render_listing_card
                    if items_df.empty:
                        st.info("No listings match your search/filter")
                    else:
                        # Display as 3-column grid using render_listing_card
                        cols_per_row = 3
                        for i in range(0, len(items_df), cols_per_row):
                            cols = st.columns(cols_per_row)
                            for j, col in enumerate(cols):
                                if i + j < len(items_df):
                                    row = items_df.iloc[i + j]
                                    with col:
                                        render_listing_card(row)

                # Export option
                st.markdown("---")
                if st.button("📥 Export Listings to CSV", help="Download all listings as CSV"):
                    csv = items_df.to_csv(index=False)
                    st.download_button(
                        "⬇️ Download CSV",
                        csv,
                        "my_marketplace_listings.csv",
                        "text/csv"
                    )

    # ========== TAB 8: API Config ==========
    if current_tab_index == 7:
        logger.debug("Rendering TAB 8: API Config")
        st.header("🔧 Facebook Commerce API")

        # Run live diagnostics
        commerce_api = None
        if COMMERCE_API_AVAILABLE:
            try:
                commerce_api = get_commerce_api()
            except Exception:
                pass

        diagnostics = run_live_diagnostics(commerce_api)

        # SINGLE STATUS DISPLAY (no duplicates, no instructions)
        if diagnostics["can_proceed"]:
            st.success(f"🟢 **Ready** — {diagnostics['passed']}/{diagnostics['total']} checks passed")
        else:
            st.error(f"🔴 **Blocked** — {diagnostics['failed']} required")

            # Show each failure ONCE with selectable link text
            for check in diagnostics["checks"]:
                if check["status"] == "fail":
                    # Markdown link = selectable text + accessible
                    st.markdown(
                        f'❌ **{check["label"]}** — '
                        f'<a href="{check["fix_url"]}" target="_blank" '
                        f'aria-label="Fix {check["label"]}: {check["reason"]}">'
                        f'Fix →</a>',
                        unsafe_allow_html=True
                    )

        # Only show advanced options if basic requirements met
        if commerce_api and commerce_api.is_valid:
            st.markdown("---")
            comp_status = commerce_api.get_status()

            # Compact status line
            api_version_status = get_api_version_status()
            mode = "🔒 Production" if comp_status.get("mode") == "background" else "🧪 Setup"
            st.caption(f"Mode: {mode} | API: v{comp_status.get('api_version', '?')}")

            # Pre-flight (only action needed)
            if st.button("🛫 Verify Configuration", type="primary", key="btn_preflight"):
                gate = commerce_api.run_preflight_check()
                can_proceed, message = gate.can_proceed("API operation")
                if can_proceed:
                    st.success(f"✅ {message}")
                else:
                    st.error(message)


if __name__ == '__main__':
    main()


