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
import browser_enricher
from pathlib import Path
from datetime import datetime
import io
import zipfile
import requests
from PIL import Image
import logging


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

# Initialize session state
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'last_processed' not in st.session_state:
    st.session_state.last_processed = None
if 'selected_db' not in st.session_state:
    st.session_state.selected_db = 'facebook_profiles.db'
if 'chrome_connected' not in st.session_state:
    st.session_state.chrome_connected = None


def check_chrome_connection():
    """Check if Chrome is running with remote debugging"""
    try:
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        browser = p.chromium.connect_over_cdp('http://localhost:9222')
        browser.close()
        p.stop()
        return True
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
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()


def get_database_stats(df):
    """Calculate database statistics (Graph API compatible)"""
    if df.empty:
        return {}

    # Handle both old and new schema
    error_col = 'http_error' if 'http_error' in df.columns else 'error'
    pic_col = 'fb_picture_url' if 'fb_picture_url' in df.columns else 'browser_profile_pic_url'

    stats = {
        'total_records': len(df),
        'successful': len(df[df[error_col].isna()]),
        'errors': len(df[df[error_col].notna()]),
        'pending_enrichment': len(df[df['enrichment_status'] == 'pending']),
        'enriched': len(df[df['enrichment_status'] == 'enriched']),
        'failed_enrichment': len(df[df['enrichment_status'] == 'failed']),
        'with_images': len(df[df[pic_col].notna()]),
    }

    return stats


def process_urls_ui(urls, db_file, rate_limit=1.0, timeout=15):
    """Process URLs with HTTP only (Stage 1)"""
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
    """Enrich pending profiles with browser (Stage 2)"""
    st.session_state.processing = True

    progress_bar = st.progress(0)
    status_text = st.empty()
    results_container = st.container()

    try:
        # Connect to Chrome
        status_text.text("Connecting to Chrome...")
        playwright, browser, page = browser_enricher.connect_to_chrome()

        # Get pending profiles
        conn = sqlite3.connect(db_file)
        cur = conn.cursor()
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
        for i, (db_id, profile_id, clean_url) in enumerate(pending, 1):
            progress_bar.progress(i / total)
            status_text.text(f"Enriching {i}/{total}: {profile_id}...")

            try:
                # Enrich profile
                enrichment_data = browser_enricher.enrich_profile(page, profile_id)

                # Download profile image if available
                local_image_path = None
                if enrichment_data.get('browser_profile_pic_url'):
                    local_image_path = download_profile_image(
                        profile_id,
                        enrichment_data['browser_profile_pic_url']
                    )
                    if local_image_path:
                        enrichment_data['local_image_path'] = local_image_path

                # Update database
                conn = sqlite3.connect(db_file)
                browser_enricher.update_profile(conn, db_id, enrichment_data)
                conn.close()

                with results_container:
                    st.success(f"✓ {profile_id} - {enrichment_data.get('browser_resolved_username', 'N/A')}")

                success_count += 1

            except Exception as e:
                with results_container:
                    st.error(f"✗ {profile_id} - Error: {str(e)}")
                error_count += 1

            # Rate limiting
            if i < total:
                import time
                time.sleep(rate_limit)

        # Cleanup
        page.close()
        browser.close()
        playwright.stop()

        # Summary
        st.success(f"""
        **Browser Enrichment Complete!**
        - Total: {total}
        - Success: {success_count}
        - Errors: {error_count}
        """)

    except Exception as e:
        st.error(f"Browser enrichment failed: {e}")
        st.info("""
        **To enable browser enrichment:**
        1. Close all Chrome windows
        2. Run: `google-chrome --remote-debugging-port=9222`
        3. Log into Facebook in that Chrome window
        4. Refresh this dashboard
        """)

    finally:
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
    except:
        pass
    return None


def main():
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
    
    selected_db = st.sidebar.selectbox(
        "Select Database",
        db_options,
        index=0
    )

    # Detect and display schema version
    if Path(selected_db).exists():
        schema_version = detect_schema_version(selected_db)
        if schema_version == 'new':
            st.sidebar.success("✅ Facebook API Schema (v24.0)")
        elif schema_version == 'old':
            st.sidebar.warning("⚠️ Legacy Schema Detected")
            with st.sidebar.expander("ℹ️ About Schema Versions"):
                st.write("""
                **Legacy Schema**: Original column names (profile_id, page_title, etc.)

                **Facebook API Schema**: Graph API v24.0 compatible (fb_id, fb_name, etc.)

                Both schemas are fully supported. You can migrate to the new schema using:
                ```bash
                python3 schema_upgrade_v2.py --database {selected_db}
                ```
                """)
        else:
            st.sidebar.error("❌ Unknown schema")

    st.session_state.selected_db = selected_db
    
    # Initialize database if it doesn't exist
    if not Path(selected_db).exists():
        processor.init_db(selected_db)
        st.sidebar.success(f"Created new database: {selected_db}")

    # Load data
    df = load_data(selected_db)
    stats = get_database_stats(df)

    # Sidebar stats
    st.sidebar.markdown("---")
    st.sidebar.metric("Total Records", stats.get('total_records', 0))
    st.sidebar.metric("Successful", stats.get('successful', 0))
    st.sidebar.metric("With Images", stats.get('with_images', 0))

    # ========== QUICK ACTIONS (UX Improvement) ==========
    pending_count = stats.get('pending_enrichment', 0)
    if pending_count > 0:
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚡ Quick Actions")
        st.sidebar.warning(f"**{pending_count} profiles** need browser enrichment to get images & full data")

        # Check Chrome status for quick action button
        if st.session_state.chrome_connected:
            if st.sidebar.button(
                f"🚀 Enrich All {pending_count} Pending",
                use_container_width=True,
                type="primary"
            ):
                enrich_with_browser_ui(selected_db, rate_limit=3.0)
                st.rerun()
        else:
            st.sidebar.button(
                f"🚀 Enrich All {pending_count} Pending",
                use_container_width=True,
                disabled=True,
                help="Start Chrome with: google-chrome --remote-debugging-port=9222"
            )
            with st.sidebar.expander("🔧 How to Enable"):
                st.markdown("""
                1. **Close all Chrome windows**
                2. **Run in terminal:**
                   ```bash
                   google-chrome --remote-debugging-port=9222
                   ```
                3. **Log into Facebook** in that Chrome
                4. **Refresh this page**
                """)

    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📤 Upload & Process",
        "📊 View Data",
        "✏️ Edit Records",
        "📈 Analytics",
        "💾 Export"
    ])

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
    with tab1:
        st.header("Upload & Process Facebook Profile URLs")

        # Check Chrome connection
        if st.session_state.chrome_connected is None:
            st.session_state.chrome_connected = check_chrome_connection()

        # Chrome status indicator
        col_status1, col_status2 = st.columns([3, 1])
        with col_status1:
            if st.session_state.chrome_connected:
                st.success("✅ Chrome Connected - Full enrichment available")
            else:
                st.warning("⚠️ Chrome Not Connected - HTTP processing only")
        with col_status2:
            if st.button("🔄 Recheck"):
                st.session_state.chrome_connected = check_chrome_connection()
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
                use_container_width=True,
                type="primary",
                help="Process URLs with HTTP requests (no browser needed)",
                key="http_process_button"
            ):
                # DEBUG: Show what we're processing
                st.info(f"🔍 DEBUG: Button clicked! Processing {len(urls)} URLs")
                st.write(f"Database: {selected_db}")
                st.write(f"Rate limit: {rate_limit}s")
                st.write(f"Timeout: {timeout}s")

                try:
                    # Process URLs
                    result = process_urls_ui(urls, selected_db, rate_limit, timeout)

                    # Show result
                    st.success(f"✅ Processing complete! Result: {result}")

                    # Force refresh
                    st.rerun()

                except Exception as e:
                    st.error(f"❌ Processing failed: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        with col_browser:
            st.markdown("**Stage 2: Browser Enrichment**")
            st.caption("Slow • Full data • Requires Chrome + Facebook login")

            if not st.session_state.chrome_connected:
                st.button(
                    "⚡ Enrich with Browser",
                    disabled=True,
                    use_container_width=True,
                    help="Chrome not connected. See setup instructions below."
                )

                with st.expander("🔧 Chrome Setup Instructions"):
                    st.markdown("""
                    **To enable browser enrichment:**

                    1. Close all Chrome windows
                    2. Open terminal and run:
                    ```bash
                    google-chrome --remote-debugging-port=9222
                    ```
                    3. Log into Facebook in that Chrome window
                    4. Click "🔄 Recheck" button above
                    5. Return here and click "Enrich with Browser"

                    **What browser enrichment provides:**
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
                    use_container_width=True,
                    type="secondary"
                ):
                    enrich_with_browser_ui(selected_db, rate_limit=3.0)
                    st.rerun()

        if st.session_state.processing:
            st.warning("⏳ Processing in progress...")

    # ========== TAB 2: View Data ==========
    with tab2:
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
                    show_pending = st.button(f"⏳ Show {pending_count} Pending", use_container_width=True)
                with qf_col2:
                    show_enriched = st.button(f"✅ Show Enriched ({stats.get('enriched', 0)})", use_container_width=True)
                with qf_col3:
                    show_no_images = st.button(f"📷 Without Images", use_container_width=True)
                with qf_col4:
                    show_all = st.button("📋 Show All", use_container_width=True)

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
                st.dataframe(filtered_df[selected_columns], use_container_width=True, height=500)

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
                        except:
                            st.text("Image unavailable")

                with col2:
                    st.markdown("**Profile Details:**")
                    for col in record.index:
                        if pd.notna(record[col]) and record[col] != '':
                            st.text(f"{col}: {record[col]}")

    # ========== TAB 3: Edit Records ==========
    with tab3:
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
                    except:
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

            if st.button("🗑️ Delete This Record", type="secondary"):
                if processor.delete_profile(selected_db, record_id):
                    st.success("✅ Record deleted successfully!")
                    load_data.clear()
                    st.rerun()
                else:
                    st.error("❌ Failed to delete record")

    # ========== TAB 4: Analytics ==========
    with tab4:
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
    with tab5:
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
            st.dataframe(export_df.head(3), use_container_width=True)

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


if __name__ == '__main__':
    main()


