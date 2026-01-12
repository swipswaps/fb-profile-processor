#!/usr/bin/env python3
"""
Facebook Profile Processor - v2 Dashboard
Complete UX overhaul with simplified workflow

USAGE:
    streamlit run dashboard_v2.py
"""

import streamlit as st
import pandas as pd
import sqlite3
import fb_profile_processor as processor
import selenium_enricher
from pathlib import Path
from datetime import datetime
import io
import zipfile
import requests
from PIL import Image
import logging
import time
import glob

# Configure page
st.set_page_config(
    page_title="FB Profile Processor",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# STATUS BADGE SYSTEM (Phase 1B: Traffic Light Indicators)
# ============================================================

def get_status_badge(row):
    """Return traffic light status badge for profile"""
    enrichment_status = row.get('enrichment_status', 'pending')
    picture_url = row.get('fb_picture_url', '')
    has_error = bool(row.get('error') or row.get('enrichment_error'))

    # Check for real image (not default Facebook avatar)
    # Default avatars contain these patterns
    default_avatar_patterns = [
        '613165984_878109372061942',  # Facebook default silhouette
        '611565328_1591427535190702',  # Another default pattern
        'default_',
        'silhouette',
    ]

    has_real_image = bool(picture_url)
    if picture_url:
        for pattern in default_avatar_patterns:
            if pattern in picture_url:
                has_real_image = False
                break

    has_location = bool(row.get('fb_location_name'))

    if has_error:
        return "🔴 Failed"
    elif enrichment_status == 'enriched' and has_real_image and has_location:
        return "🟢 Complete"
    elif enrichment_status == 'enriched' and (has_real_image or has_location):
        return "🟡 Partial"
    elif enrichment_status == 'enriched':
        return "🟠 Basic"
    elif enrichment_status == 'pending':
        return "⬜ Pending"
    else:
        return "⚪ Unknown"

def get_status_color(status_badge):
    """Return CSS color for status badge"""
    colors = {
        "🟢 Complete": "#22c55e",
        "🟡 Basic Only": "#eab308", 
        "🟠 Pending": "#f97316",
        "🔴 Failed": "#ef4444",
        "⚪ Unknown": "#9ca3af"
    }
    return colors.get(status_badge, "#9ca3af")

# ============================================================
# DATABASE UTILITIES
# ============================================================

def get_available_databases():
    """Get all .db files with stats"""
    databases = []
    for db_file in glob.glob("*.db"):
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Get counts
            cursor.execute("SELECT COUNT(*) FROM profiles")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM profiles WHERE enrichment_status = 'enriched'")
            enriched = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM profiles WHERE fb_picture_url IS NOT NULL AND fb_picture_url != ''")
            with_images = cursor.fetchone()[0]
            
            # Get last update
            cursor.execute("SELECT MAX(updated_at) FROM profiles")
            last_update = cursor.fetchone()[0] or "Never"
            
            conn.close()
            
            pct_complete = (enriched / total * 100) if total > 0 else 0
            
            databases.append({
                'name': db_file,
                'total': total,
                'enriched': enriched,
                'with_images': with_images,
                'pct_complete': pct_complete,
                'last_update': last_update
            })
        except Exception as e:
            databases.append({
                'name': db_file,
                'total': 0,
                'enriched': 0,
                'with_images': 0,
                'pct_complete': 0,
                'last_update': f"Error: {e}"
            })
    
    return sorted(databases, key=lambda x: x['total'], reverse=True)

def get_profiles_df(db_path, simplified=True):
    """Get profiles as DataFrame with optional simplification"""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
    conn.close()
    
    if df.empty:
        return df
    
    # Add status badge column
    df['Status'] = df.apply(get_status_badge, axis=1)
    
    if simplified:
        # Return simplified view (Phase 1C)
        simple_cols = ['Status', 'fb_name', 'fb_location_name', 'fb_join_date', 'fb_picture_url']
        simple_cols = [c for c in simple_cols if c in df.columns]
        
        # Rename for user-friendliness
        rename_map = {
            'fb_name': 'Name',
            'fb_location_name': 'Location', 
            'fb_join_date': 'Join Date',
            'fb_picture_url': 'Has Photo'
        }
        
        result = df[['id'] + simple_cols].copy()
        result.rename(columns=rename_map, inplace=True)
        
        # Convert photo URL to Yes/No
        if 'Has Photo' in result.columns:
            result['Has Photo'] = result['Has Photo'].apply(lambda x: '✅' if x else '❌')
        
        return result, df  # Return both simplified and full
    
    return df, df

def get_stats(db_path):
    """Get database statistics"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM profiles")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM profiles WHERE enrichment_status = 'enriched'")
        enriched = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM profiles WHERE enrichment_status = 'pending'")
        pending = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM profiles WHERE fb_picture_url IS NOT NULL AND fb_picture_url != ''")
        with_images = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total': total,
            'enriched': enriched,
            'pending': pending,
            'with_images': with_images,
            'pct_complete': (enriched / total * 100) if total > 0 else 0
        }
    except Exception as e:
        return {'total': 0, 'enriched': 0, 'pending': 0, 'with_images': 0, 'pct_complete': 0}

# ============================================================
# FIREFOX & PROCESSING (Phase 1A: One-Click Processing)
# ============================================================

def check_firefox_ready():
    """Check if Firefox profile exists"""
    try:
        profile_path = selenium_enricher.get_firefox_profile_path()
        return profile_path is not None
    except:
        return False

def process_and_enrich_urls(urls, db_path, progress_callback=None):
    """
    One-click process: HTTP collection + Browser enrichment

    This replaces the multi-step workflow with a single operation.
    """
    results = {
        'http_success': 0,
        'http_failed': 0,
        'enrich_success': 0,
        'enrich_failed': 0,
        'errors': []
    }

    total_urls = len(urls)
    firefox_ready = check_firefox_ready()

    # Step 1: HTTP Collection
    if progress_callback:
        progress_callback(0, "📥 Starting HTTP collection...")

    for i, url in enumerate(urls):
        try:
            # Use processor for HTTP collection
            success = processor.process_url(url, db_path)
            if success:
                results['http_success'] += 1
            else:
                results['http_failed'] += 1
        except Exception as e:
            results['http_failed'] += 1
            results['errors'].append(f"HTTP: {url[:50]}... - {e}")

        if progress_callback:
            pct = (i + 1) / total_urls * 0.5  # HTTP is first 50%
            progress_callback(pct, f"📥 Collected {i+1}/{total_urls} profiles")

    # Step 2: Browser Enrichment (if Firefox available)
    if firefox_ready:
        if progress_callback:
            progress_callback(0.5, "🌐 Starting browser enrichment...")

        # Use the fixed enrich_pending_profiles function
        def enrich_callback(pct, msg):
            # Scale from 0.5 to 1.0
            if progress_callback:
                progress_callback(0.5 + (pct * 0.5), msg)

        enrich_results = enrich_pending_profiles(db_path, limit=total_urls, progress_callback=enrich_callback)
        results['enrich_success'] = enrich_results.get('success', 0)
        results['enrich_failed'] = enrich_results.get('failed', 0)
        results['errors'].extend(enrich_results.get('errors', []))
    else:
        if progress_callback:
            progress_callback(1.0, "⚠️ Firefox not available - HTTP data only")

    return results

def enrich_pending_profiles(db_path, limit=None, progress_callback=None):
    """Enrich all pending profiles using selenium_enricher"""

    results = {'success': 0, 'failed': 0, 'partial': 0, 'errors': []}

    # Get pending profiles
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    query = """
        SELECT id, fb_id FROM profiles
        WHERE enrichment_status = 'pending'
        AND fb_id IS NOT NULL
        ORDER BY id DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    pending_profiles = cursor.fetchall()
    conn.close()

    if not pending_profiles:
        return results

    # Get Firefox profile path
    profile_path = selenium_enricher.get_firefox_profile_path()
    if not profile_path:
        results['errors'].append("Firefox profile not found")
        return results

    if progress_callback:
        progress_callback(0.05, "🦊 Starting Firefox...")

    # Create Firefox driver
    try:
        driver, temp_profile_dir = selenium_enricher.create_firefox_driver(profile_path)
        if driver is None:
            results['errors'].append("Could not start Firefox")
            return results
    except Exception as e:
        results['errors'].append(f"Firefox error: {e}")
        return results

    try:
        # Check Facebook login
        if progress_callback:
            progress_callback(0.1, "🔐 Checking Facebook login...")

        driver.get("https://www.facebook.com")
        time.sleep(3)

        if "login" in driver.current_url.lower():
            results['errors'].append("Not logged into Facebook - please login first")
            return results

        # Process each profile
        for i, (profile_id, fb_id) in enumerate(pending_profiles):
            try:
                if progress_callback:
                    pct = 0.1 + ((i + 1) / len(pending_profiles) * 0.9)
                    progress_callback(pct, f"🌐 Enriching {i+1}/{len(pending_profiles)}: {fb_id}")

                # Call the enricher
                enrichment_data = selenium_enricher.enrich_profile(driver, profile_id, fb_id)

                status = enrichment_data.get('enrichment_status', 'failed')

                if status == 'enriched':
                    results['success'] += 1
                elif status == 'partial':
                    results['partial'] += 1
                else:
                    results['failed'] += 1
                    if enrichment_data.get('enrichment_error'):
                        results['errors'].append(f"{fb_id}: {enrichment_data['enrichment_error']}")

                # Update database
                conn = sqlite3.connect(db_path)
                selenium_enricher.update_profile_in_db(conn, profile_id, enrichment_data)
                conn.commit()
                conn.close()

                # Rate limiting
                time.sleep(2)

            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{fb_id}: {e}")

    finally:
        # Aggressive cleanup
        if progress_callback:
            progress_callback(1.0, "🧹 Cleaning up...")

        # Close driver
        try:
            driver.quit()
        except:
            pass

        # Cleanup temp profile
        try:
            selenium_enricher.cleanup_temp_profile()
        except:
            pass

        # Kill any orphaned geckodriver processes
        try:
            import subprocess
            subprocess.run(['pkill', '-f', 'geckodriver'], capture_output=True, timeout=5)
        except:
            pass

        time.sleep(1)  # Give processes time to terminate

    return results

# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

if 'selected_db' not in st.session_state:
    st.session_state.selected_db = 'facebook_profiles.db'
if 'firefox_ready' not in st.session_state:
    st.session_state.firefox_ready = check_firefox_ready()
if 'expert_mode' not in st.session_state:
    st.session_state.expert_mode = False

# ============================================================
# MAIN UI
# ============================================================

def main():
    # ========== SIDEBAR: App Title & Database Selection ==========
    st.sidebar.title("👤 FB Profile Processor")

    databases = get_available_databases()
    if not databases:
        st.error("No database files found. Create one first.")
        return

    # Enhanced database selector with preview
    db_options = []
    for db in databases:
        if db['total'] > 0:
            label = f"📊 {db['name']} ({db['total']} profiles, {db['pct_complete']:.0f}% done)"
        else:
            label = f"📁 {db['name']} (empty)"
        db_options.append(label)

    selected_idx = 0
    for i, db in enumerate(databases):
        if db['name'] == st.session_state.selected_db:
            selected_idx = i
            break

    selected_label = st.sidebar.selectbox(
        "📂 Database",
        options=db_options,
        index=selected_idx
    )

    # Extract actual db name from label
    selected_db = databases[db_options.index(selected_label)]['name']
    st.session_state.selected_db = selected_db

    # Show database stats in sidebar
    stats = get_stats(selected_db)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Database Stats")
    col1, col2 = st.sidebar.columns(2)
    col1.metric("Total", stats['total'])
    col2.metric("Complete", f"{stats['pct_complete']:.0f}%")

    col1, col2 = st.sidebar.columns(2)
    col1.metric("🟢 Enriched", stats['enriched'])
    col2.metric("🟠 Pending", stats['pending'])

    # Firefox status
    st.sidebar.markdown("---")
    if st.session_state.firefox_ready:
        st.sidebar.success("🦊 Firefox Ready")
    else:
        st.sidebar.warning("⚠️ Firefox Not Available")
        if st.sidebar.button("🔄 Recheck"):
            st.session_state.firefox_ready = check_firefox_ready()
            st.rerun()

    # Expert mode toggle (Phase 1C)
    st.sidebar.markdown("---")
    st.session_state.expert_mode = st.sidebar.checkbox(
        "🔧 Expert Mode",
        value=st.session_state.expert_mode,
        help="Show all technical fields"
    )

    # ========== TABS: Full Feature Set ==========
    tab_home, tab_add, tab_view, tab_edit, tab_analytics, tab_export, tab_settings = st.tabs([
        "🏠 Dashboard",
        "➕ Add Profiles",
        "📊 View Data",
        "✏️ Edit",
        "📈 Analytics",
        "📥 Export",
        "⚙️ Settings"
    ])

    # ========== TAB 1: Dashboard Home ==========
    with tab_home:
        render_dashboard_home(selected_db, stats)

    # ========== TAB 2: Add Profiles ==========
    with tab_add:
        render_add_profiles(selected_db)

    # ========== TAB 3: View Data ==========
    with tab_view:
        render_view_data(selected_db)

    # ========== TAB 4: Edit Records ==========
    with tab_edit:
        render_edit_records(selected_db)

    # ========== TAB 5: Analytics ==========
    with tab_analytics:
        render_analytics(selected_db, stats)

    # ========== TAB 6: Export ==========
    with tab_export:
        render_export(selected_db, stats)

    # ========== TAB 7: Settings ==========
    with tab_settings:
        render_settings(selected_db)


# ============================================================
# RENDER FUNCTIONS
# ============================================================

def render_dashboard_home(db_path, stats):
    """Dashboard home with overview and quick actions (Phase 2B, 3B)"""

    st.header("🏠 Dashboard")

    # Quick summary metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Profiles",
            stats['total'],
            help="Total profiles in database"
        )

    with col2:
        delta = f"+{stats['enriched']}" if stats['enriched'] > 0 else None
        st.metric(
            "🟢 Complete",
            stats['with_images'],
            delta=delta,
            help="Profiles with full data and images"
        )

    with col3:
        st.metric(
            "🟠 Pending",
            stats['pending'],
            help="Profiles needing enrichment"
        )

    with col4:
        st.metric(
            "Success Rate",
            f"{stats['pct_complete']:.0f}%",
            help="Percentage of profiles enriched"
        )

    # ========== PRIMARY ACTION ==========
    if stats['pending'] > 0 and st.session_state.get('firefox_ready'):
        st.markdown("---")
        if st.button(
            f"🚀 Enrich {stats['pending']} Pending Profiles",
            type="primary",
            use_container_width=True,
            key="main_enrich"
        ):
            with st.status("🌐 Enriching profiles...", expanded=True) as status:
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(pct, msg):
                    progress_bar.progress(pct)
                    status_text.write(msg)

                results = enrich_pending_profiles(db_path, progress_callback=update_progress)

                st.write(f"✅ Success: {results['success']}")
                st.write(f"❌ Failed: {results['failed']}")

                if results['errors']:
                    with st.expander("View Errors"):
                        for err in results['errors'][:10]:
                            st.error(err)

                status.update(label="✅ Enrichment Complete!", state="complete")

            st.rerun()


def render_add_profiles(db_path):
    """Add Profiles tab with one-click processing (Phase 1A)"""

    st.header("➕ Add Profiles")

    # Firefox status
    if st.session_state.firefox_ready:
        st.success("🦊 Firefox ready - Full enrichment will be automatic")
    else:
        st.warning("⚠️ Firefox not available - Will collect basic data only")

    st.markdown("---")

    # URL input
    col1, col2 = st.columns([3, 1])

    with col1:
        url_text = st.text_area(
            "Paste Facebook Profile URLs (one per line)",
            height=200,
            placeholder="https://www.facebook.com/marketplace/profile/123456789\nhttps://www.facebook.com/marketplace/profile/987654321",
            key="url_input"
        )

    with col2:
        st.markdown("**Or upload a file:**")
        uploaded_file = st.file_uploader(
            "Upload .txt file",
            type=['txt'],
            key="url_file"
        )

        if uploaded_file:
            file_content = uploaded_file.read().decode('utf-8')
            url_text = file_content
            st.success(f"📄 Loaded {len(file_content.splitlines())} lines")

    # Parse URLs
    urls = []
    if url_text:
        urls = [line.strip() for line in url_text.strip().split('\n') if line.strip()]
        urls = [u for u in urls if 'facebook.com' in u.lower()]

    # URL count and validation
    if urls:
        st.info(f"📝 Found **{len(urls)}** valid Facebook URLs")

    st.markdown("---")

    # ========== ONE-CLICK PROCESSING (Phase 1A) ==========
    col1, col2 = st.columns(2)

    with col1:
        # Main action button
        button_label = "🚀 Process & Enrich All" if st.session_state.firefox_ready else "📥 Collect Basic Data"
        button_help = "HTTP collection + Browser enrichment" if st.session_state.firefox_ready else "HTTP collection only"

        if st.button(
            button_label,
            type="primary",
            use_container_width=True,
            disabled=len(urls) == 0,
            help=button_help
        ):
            with st.status("Processing profiles...", expanded=True) as status:
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(pct, msg):
                    progress_bar.progress(pct)
                    status_text.write(msg)

                results = process_and_enrich_urls(urls, db_path, progress_callback=update_progress)

                # Show results
                st.markdown("### Results")
                col_a, col_b = st.columns(2)
                col_a.metric("HTTP Success", results['http_success'])
                col_b.metric("HTTP Failed", results['http_failed'])

                if st.session_state.firefox_ready:
                    col_a, col_b = st.columns(2)
                    col_a.metric("Enriched", results['enrich_success'])
                    col_b.metric("Enrich Failed", results['enrich_failed'])

                if results['errors']:
                    with st.expander(f"⚠️ {len(results['errors'])} Errors"):
                        for err in results['errors'][:20]:
                            st.error(err)

                status.update(label="✅ Processing Complete!", state="complete")

            st.rerun()

    with col2:
        # Alternative: HTTP only
        if st.session_state.firefox_ready:
            if st.button(
                "📥 HTTP Only (Fast)",
                use_container_width=True,
                disabled=len(urls) == 0,
                help="Collect basic data without browser enrichment"
            ):
                with st.spinner("Collecting data..."):
                    success = 0
                    for url in urls:
                        try:
                            if processor.process_url(url, db_path):
                                success += 1
                        except:
                            pass
                    st.success(f"✅ Collected {success}/{len(urls)} profiles")
                st.rerun()

    # ========== TIPS ==========
    with st.expander("💡 Tips"):
        st.markdown("""
        **URL Formats Supported:**
        - `https://www.facebook.com/marketplace/profile/123456789`
        - `https://www.facebook.com/profile.php?id=123456789`
        - `https://www.facebook.com/username`

        **Processing Modes:**
        - **Process & Enrich**: Full data collection with Firefox (recommended)
        - **HTTP Only**: Fast but limited data (no images)

        **Tips:**
        - Login to Facebook in Firefox first for best results
        - Processing takes ~3 seconds per profile
        - You can process up to 100 URLs at once
        """)


def render_view_data(db_path):
    """View Data tab with industry-standard profile card layout"""

    st.header("📊 View Profiles")

    # Get data
    conn = sqlite3.connect(db_path)
    full_df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
    conn.close()

    if full_df.empty:
        st.info("No profiles yet. Go to **➕ Add Profiles** to get started.")
        return

    # ========== VIEW MODE SELECTOR ==========
    view_mode = st.radio(
        "View Mode",
        ["📋 Table", "🃏 Cards", "👤 Detail"],
        horizontal=True,
        key="view_mode"
    )

    # ========== FILTERS ==========
    with st.expander("🔍 Filters", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            status_options = ["All"] + list(full_df['enrichment_status'].dropna().unique())
            status_filter = st.selectbox("Status", status_options, key="status_filter")

        with col2:
            search_query = st.text_input("🔍 Search Name", key="search_query")

        with col3:
            location_filter = st.text_input("📍 Filter Location", key="loc_filter")

    # Apply filters
    display_df = full_df.copy()

    if status_filter != "All":
        display_df = display_df[display_df['enrichment_status'] == status_filter]

    if search_query:
        display_df = display_df[
            display_df['fb_name'].fillna('').str.contains(search_query, case=False)
        ]

    if location_filter:
        display_df = display_df[
            display_df['fb_location_name'].fillna('').str.contains(location_filter, case=False)
        ]

    st.caption(f"Showing **{len(display_df)}** of {len(full_df)} profiles")

    # ========== TABLE VIEW ==========
    if view_mode == "📋 Table":
        st.dataframe(
            display_df[[c for c in ['id', 'fb_name', 'fb_location_name', 'fb_join_date', 'enrichment_status', 'fb_profile_url'] if c in display_df.columns]],
            use_container_width=True,
            height=500,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "fb_name": st.column_config.TextColumn("Name", width="medium"),
                "fb_location_name": st.column_config.TextColumn("Location", width="medium"),
                "fb_join_date": st.column_config.TextColumn("Joined", width="small"),
                "enrichment_status": st.column_config.TextColumn("Status", width="small"),
                "fb_profile_url": st.column_config.LinkColumn("Profile URL", width="large"),
            }
        )

    # ========== CARD VIEW ==========
    elif view_mode == "🃏 Cards":
        # Display profiles as cards in grid
        cols_per_row = 3
        rows = [display_df.iloc[i:i+cols_per_row] for i in range(0, len(display_df), cols_per_row)]

        for row_profiles in rows[:20]:  # Limit to 20 rows (60 profiles) for performance
            cols = st.columns(cols_per_row)
            for idx, (_, profile) in enumerate(row_profiles.iterrows()):
                with cols[idx]:
                    render_profile_card(profile)

        if len(display_df) > 60:
            st.info(f"Showing first 60 profiles. Use filters to narrow results.")

    # ========== DETAIL VIEW ==========
    elif view_mode == "👤 Detail":
        profile_ids = display_df['id'].tolist()

        if profile_ids:
            selected_id = st.selectbox(
                "Select Profile",
                options=profile_ids,
                format_func=lambda x: f"ID {x} - {display_df[display_df['id']==x]['fb_name'].values[0] if pd.notna(display_df[display_df['id']==x]['fb_name'].values[0]) else 'Unknown'}"
            )

            if selected_id:
                profile = display_df[display_df['id'] == selected_id].iloc[0]
                render_profile_detail(profile)

    # ========== BATCH OPERATIONS ==========
    st.markdown("---")
    with st.expander("🔧 Batch Operations"):
        col1, col2, col3 = st.columns(3)

        with col1:
            pending_count = len(full_df[full_df['enrichment_status'] == 'pending'])
            if pending_count > 0 and st.session_state.get('firefox_ready'):
                if st.button(f"🚀 Enrich {pending_count} Pending", use_container_width=True):
                    with st.spinner("Enriching..."):
                        results = enrich_pending_profiles(db_path, limit=pending_count)
                        st.success(f"✅ Enriched {results['success']}, Failed {results['failed']}")
                    st.rerun()

        with col2:
            failed_count = len(full_df[full_df['enrichment_status'] == 'failed'])
            if failed_count > 0:
                if st.button(f"🔄 Retry {failed_count} Failed", use_container_width=True):
                    conn = sqlite3.connect(db_path)
                    conn.execute("UPDATE profiles SET enrichment_status = 'pending' WHERE enrichment_status = 'failed'")
                    conn.commit()
                    conn.close()
                    st.success("Reset failed profiles to pending")
                    st.rerun()

        with col3:
            if st.button("🗑️ Clear All Data", use_container_width=True, type="secondary"):
                st.session_state['confirm_clear'] = True

            if st.session_state.get('confirm_clear'):
                if st.button("⚠️ CONFIRM DELETE ALL", type="primary"):
                    conn = sqlite3.connect(db_path)
                    conn.execute("DELETE FROM profiles")
                    conn.commit()
                    conn.close()
                    st.session_state['confirm_clear'] = False
                    st.success("Deleted all profiles")
                    st.rerun()


def render_profile_card(profile):
    """Render a single profile as an industry-standard card"""

    # Status badge
    status = profile.get('enrichment_status', 'pending')
    status_badges = {
        'enriched': '🟢',
        'partial': '🟡',
        'pending': '⬜',
        'failed': '🔴'
    }
    badge = status_badges.get(status, '⬜')

    # Card container with border
    with st.container():
        st.markdown(f"""
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 12px; background: #fafafa;">
        """, unsafe_allow_html=True)

        # Profile picture + name
        col_img, col_info = st.columns([1, 2])

        with col_img:
            pic_url = profile.get('fb_picture_url')
            if pd.notna(pic_url) and pic_url:
                try:
                    st.image(pic_url, width=80)
                except:
                    st.markdown("📷")
            else:
                st.markdown("📷")

        with col_info:
            name = profile.get('fb_name', 'Unknown')
            st.markdown(f"**{badge} {name}**")

            location = profile.get('fb_location_name')
            if pd.notna(location) and location:
                st.caption(f"📍 {location}")

            join_date = profile.get('fb_join_date')
            if pd.notna(join_date) and join_date:
                st.caption(f"📅 Joined {join_date}")

        # Profile link
        profile_url = profile.get('fb_profile_url')
        if pd.notna(profile_url) and profile_url:
            st.markdown(f"[🔗 View Profile]({profile_url})")

        st.markdown("</div>", unsafe_allow_html=True)


def render_profile_detail(profile):
    """Render full profile detail in industry-standard layout"""

    # ========== HEADER SECTION ==========
    col_pic, col_header = st.columns([1, 3])

    with col_pic:
        pic_url = profile.get('fb_picture_url')
        if pd.notna(pic_url) and pic_url:
            try:
                st.image(pic_url, width=200)
            except:
                st.markdown("### 📷")
        else:
            st.markdown("### 📷 No Photo")

    with col_header:
        name = profile.get('fb_name', 'Unknown')
        st.markdown(f"# {name}")

        # Status badge
        status = profile.get('enrichment_status', 'pending')
        status_display = {'enriched': '🟢 Enriched', 'partial': '🟡 Partial', 'pending': '⬜ Pending', 'failed': '🔴 Failed'}
        st.markdown(f"**Status:** {status_display.get(status, status)}")

        # Quick stats row
        cols = st.columns(3)
        with cols[0]:
            location = profile.get('fb_location_name')
            st.metric("📍 Location", location if pd.notna(location) else "Not set")
        with cols[1]:
            join_date = profile.get('fb_join_date')
            st.metric("📅 Joined", join_date if pd.notna(join_date) else "Unknown")
        with cols[2]:
            fb_id = profile.get('fb_id')
            st.metric("🆔 Facebook ID", fb_id if pd.notna(fb_id) else "N/A")

    st.markdown("---")

    # ========== PROFILE INFORMATION SECTIONS ==========
    tab_basic, tab_contact, tab_social, tab_meta, tab_raw = st.tabs([
        "👤 Basic Info",
        "📧 Contact",
        "🌐 Social",
        "⚙️ Metadata",
        "📋 Raw Data"
    ])

    with tab_basic:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### Personal Details")
            _show_field("Full Name", profile.get('fb_name'))
            _show_field("First Name", profile.get('fb_first_name'))
            _show_field("Last Name", profile.get('fb_last_name'))
            _show_field("Middle Name", profile.get('fb_middle_name'))
            _show_field("Gender", profile.get('fb_gender'))
            _show_field("Birthday", profile.get('fb_birthday'))
            _show_field("Age Range", f"{profile.get('fb_age_range_min', '?')}-{profile.get('fb_age_range_max', '?')}")

        with col2:
            st.markdown("### Location")
            _show_field("Current Location", profile.get('fb_location_name'))
            _show_field("Location ID", profile.get('fb_location_id'))
            _show_field("Hometown", profile.get('fb_hometown_name'))
            _show_field("Hometown ID", profile.get('fb_hometown_id'))
            _show_field("Locale", profile.get('fb_locale'))
            _show_field("Timezone", profile.get('fb_timezone'))

    with tab_contact:
        st.markdown("### Contact Information")
        _show_field("Email", profile.get('fb_email'))
        _show_field("Website", profile.get('fb_website'))

        st.markdown("### Bio & Quotes")
        bio = profile.get('fb_bio')
        if pd.notna(bio) and bio:
            st.info(bio)
        else:
            st.caption("No bio available")

        quotes = profile.get('fb_quotes')
        if pd.notna(quotes) and quotes:
            st.success(f'"{quotes}"')

    with tab_social:
        st.markdown("### Social Stats")
        col1, col2 = st.columns(2)
        with col1:
            followers = profile.get('fb_followers_count')
            st.metric("👥 Followers", followers if pd.notna(followers) else "N/A")
        with col2:
            friends = profile.get('fb_friends_count')
            st.metric("🤝 Friends", friends if pd.notna(friends) else "N/A")

        st.markdown("### Profile Links")
        _show_field("Profile URL", profile.get('fb_profile_url'), is_link=True)
        _show_field("Vanity URL", profile.get('fb_vanity_url'), is_link=True)
        _show_field("Link", profile.get('fb_link'), is_link=True)

        st.markdown("### Verification")
        verified = profile.get('fb_verified') or profile.get('fb_is_verified')
        if verified:
            st.success("✅ Verified Account")
        else:
            st.caption("Not verified / Unknown")

    with tab_meta:
        st.markdown("### Marketplace Data")
        _show_field("Active Listings", profile.get('fb_active_listings_count'))
        _show_field("Response Rate", profile.get('fb_response_rate'))
        _show_field("Response Time", profile.get('fb_response_time'))
        _show_field("Seller Badges", profile.get('fb_seller_badges'))

        st.markdown("### System Metadata")
        _show_field("Record ID", profile.get('id'))
        _show_field("Input URL", profile.get('input_url'))
        _show_field("HTTP Status", profile.get('http_status'))
        _show_field("Created At", profile.get('created_at'))
        _show_field("Updated At", profile.get('updated_at'))
        _show_field("Enriched At", profile.get('enriched_at'))
        _show_field("Enrichment Method", profile.get('enrichment_method'))
        _show_field("Data Source", profile.get('data_source'))

        st.markdown("### API Info")
        api_accessible = profile.get('api_accessible')
        if api_accessible:
            st.success("✅ API Accessible")
        else:
            st.caption("API not configured / Not accessible")
        _show_field("API Last Sync", profile.get('api_last_sync'))

    with tab_raw:
        st.markdown("### All Fields (Raw)")
        # Convert to dict and show as JSON
        profile_dict = {k: (v if pd.notna(v) else None) for k, v in profile.items()}
        st.json(profile_dict)


def _show_field(label, value, is_link=False):
    """Helper to show a field with label and value"""
    if pd.notna(value) and value not in [None, '', 'None', 'N/A']:
        if is_link:
            st.markdown(f"**{label}:** [{value}]({value})")
        else:
            st.markdown(f"**{label}:** {value}")
    else:
        st.caption(f"{label}: Not available")


def render_export(db_path, stats):
    """Export tab with multiple format options"""

    st.header("📥 Export Data")

    if stats['total'] == 0:
        st.info("No data to export. Add some profiles first!")
        return

    # Summary
    st.markdown(f"""
    **Ready to export:**
    - 📊 {stats['total']} total profiles
    - 🟢 {stats['enriched']} enriched
    - 📷 {stats['with_images']} with images
    """)

    st.markdown("---")

    # Export options
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 Export Format")
        export_format = st.radio(
            "Choose format:",
            options=["Excel (.xlsx)", "CSV", "JSON", "SQL Dump"],
            key="export_format"
        )

    with col2:
        st.subheader("🔧 Options")
        include_all = st.checkbox("Include all fields", value=False)
        only_complete = st.checkbox("Only complete profiles", value=False)

    st.markdown("---")

    # Pre-generate export data (not inside button handler)
    conn = sqlite3.connect(db_path)

    # Build query
    query = "SELECT * FROM profiles"
    if only_complete:
        query += " WHERE enrichment_status = 'enriched' AND fb_picture_url IS NOT NULL"

    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        st.warning("No data matching your criteria")
        return

    # Simplify if not include_all
    if not include_all:
        keep_cols = ['id', 'fb_name', 'fb_location_name', 'fb_join_date',
                    'fb_profile_url', 'fb_picture_url', 'enrichment_status']
        keep_cols = [c for c in keep_cols if c in df.columns]
        df = df[keep_cols]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    st.info(f"📊 {len(df)} profiles ready for export")

    # Generate download buttons based on format
    if export_format == "Excel (.xlsx)":
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)

        st.download_button(
            label="📥 Download Excel",
            data=buffer.getvalue(),
            file_name=f"fb_profiles_{timestamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )

    elif export_format == "CSV":
        csv_data = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=f"fb_profiles_{timestamp}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )

    elif export_format == "JSON":
        json_data = df.to_json(orient='records', indent=2)
        st.download_button(
            label="📥 Download JSON",
            data=json_data,
            file_name=f"fb_profiles_{timestamp}.json",
            mime="application/json",
            type="primary",
            use_container_width=True
        )

    elif export_format == "SQL Dump":
        # Generate INSERT statements
        sql_lines = []
        for _, row in df.iterrows():
            cols = ', '.join(row.index)
            vals = ', '.join([f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if v is not None else 'NULL' for v in row.values])
            sql_lines.append(f"INSERT INTO profiles ({cols}) VALUES ({vals});")

        sql_data = '\n'.join(sql_lines)
        st.download_button(
            label="📥 Download SQL",
            data=sql_data,
            file_name=f"fb_profiles_{timestamp}.sql",
            mime="text/plain",
            type="primary",
            use_container_width=True
        )


# ============================================================
# EDIT RECORDS TAB
# ============================================================

def render_edit_records(db_path):
    """Edit & Delete Records tab"""

    st.header("✏️ Edit & Delete Records")

    # Get profiles
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("No data to edit.")
        return

    # Select record to edit
    record_id = st.selectbox(
        "Select Record ID to Edit/Delete",
        df['id'].tolist(),
        format_func=lambda x: f"ID {x} - {df[df['id']==x]['fb_name'].values[0] if 'fb_name' in df.columns else 'Unknown'}",
        key='edit_record_id'
    )

    record = df[df['id'] == record_id].iloc[0]

    # Display current data
    st.subheader(f"Editing Record #{record_id}")

    col1, col2 = st.columns([1, 2])

    with col1:
        pic_url = record.get('fb_picture_url') or record.get('browser_profile_pic_url')
        if pd.notna(pic_url):
            try:
                st.image(pic_url, width=150)
            except:
                st.text("🖼️ Image unavailable")
        else:
            st.text("📷 No image")

    with col2:
        st.text(f"Name: {record.get('fb_name', 'N/A')}")
        st.text(f"Location: {record.get('fb_location_name', 'N/A')}")
        st.text(f"Status: {record.get('enrichment_status', 'N/A')}")

    st.markdown("---")

    # Edit form
    with st.form("edit_form"):
        st.markdown("**Edit Fields:**")

        col1, col2 = st.columns(2)

        with col1:
            new_name = st.text_input(
                "Name",
                value=record.get('fb_name', '') or ''
            )
            new_location = st.text_input(
                "Location",
                value=record.get('fb_location_name', '') or ''
            )

        with col2:
            new_join_date = st.text_input(
                "Join Date",
                value=record.get('fb_join_date', '') or ''
            )
            new_enrichment_status = st.selectbox(
                "Enrichment Status",
                ['pending', 'enriched', 'partial', 'failed'],
                index=['pending', 'enriched', 'partial', 'failed'].index(
                    record.get('enrichment_status', 'pending') or 'pending'
                ) if record.get('enrichment_status') in ['pending', 'enriched', 'partial', 'failed'] else 0
            )

        submitted = st.form_submit_button("💾 Save Changes", type="primary")

        if submitted:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE profiles SET
                        fb_name = ?,
                        fb_location_name = ?,
                        fb_join_date = ?,
                        enrichment_status = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                """, (new_name, new_location, new_join_date, new_enrichment_status, record_id))
                conn.commit()
                conn.close()
                st.success("✅ Record updated!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Update failed: {e}")

    # Delete button
    st.markdown("---")
    st.markdown("**⚠️ Danger Zone:**")

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🗑️ Delete This Record", type="secondary"):
            st.session_state['confirm_delete'] = record_id

    if st.session_state.get('confirm_delete') == record_id:
        with col2:
            if st.button("⚠️ CONFIRM DELETE", type="primary"):
                try:
                    conn = sqlite3.connect(db_path)
                    conn.execute("DELETE FROM profiles WHERE id = ?", (record_id,))
                    conn.commit()
                    conn.close()
                    st.session_state['confirm_delete'] = None
                    st.success("✅ Record deleted!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Delete failed: {e}")


# ============================================================
# ANALYTICS TAB
# ============================================================

def render_analytics(db_path, stats):
    """Analytics & Insights tab"""

    st.header("📈 Analytics & Insights")

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM profiles", conn)
    conn.close()

    if df.empty:
        st.info("No data for analytics.")
        return

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Records", stats['total'])
    col2.metric("Enriched", stats['enriched'])
    col3.metric("With Images", stats['with_images'])
    col4.metric("Pending", stats['pending'])

    st.markdown("---")

    # Charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Enrichment Status")
        if 'enrichment_status' in df.columns:
            status_counts = df['enrichment_status'].value_counts()
            st.bar_chart(status_counts)

    with col2:
        st.subheader("Locations")
        if 'fb_location_name' in df.columns:
            loc_counts = df['fb_location_name'].dropna().value_counts().head(10)
            if not loc_counts.empty:
                st.bar_chart(loc_counts)
            else:
                st.info("No location data")

    # Join year distribution
    st.markdown("---")
    st.subheader("Join Year Distribution")
    if 'fb_join_date' in df.columns:
        df_years = df.copy()
        df_years['year'] = df_years['fb_join_date'].astype(str).str.extract(r'(\d{4})')
        year_counts = df_years['year'].dropna().value_counts().sort_index()
        if not year_counts.empty:
            st.bar_chart(year_counts)


# ============================================================
# SETTINGS TAB
# ============================================================

def render_settings(db_path):
    """Settings & Configuration tab"""

    st.header("⚙️ Settings & Configuration")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🦊 Firefox Status")

        if st.session_state.get('firefox_ready'):
            st.success("✅ Firefox profile found")
            st.caption("Browser enrichment available")
        else:
            st.warning("⚠️ Firefox profile not found")
            st.caption("Only HTTP collection available")

        if st.button("🔄 Recheck Firefox"):
            st.session_state.firefox_ready = check_firefox_ready()
            st.rerun()

        st.markdown("---")
        st.subheader("📂 Database Info")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get table info
            cursor.execute("SELECT COUNT(*) FROM profiles")
            total = cursor.fetchone()[0]

            cursor.execute("PRAGMA table_info(profiles)")
            columns = cursor.fetchall()

            conn.close()

            st.text(f"Database: {db_path}")
            st.text(f"Total records: {total}")
            st.text(f"Columns: {len(columns)}")

            with st.expander("📋 Column List"):
                for col in columns:
                    st.text(f"  {col[1]} ({col[2]})")

        except Exception as e:
            st.error(f"Database error: {e}")

    with col2:
        st.subheader("🔧 Actions")

        st.markdown("**Database Maintenance:**")

        if st.button("🧹 Vacuum Database", help="Optimize database file size"):
            try:
                conn = sqlite3.connect(db_path)
                conn.execute("VACUUM")
                conn.close()
                st.success("✅ Database vacuumed")
            except Exception as e:
                st.error(f"Failed: {e}")

        st.markdown("---")
        st.markdown("**Reset Options:**")

        if st.button("🔄 Reset All to Pending", help="Mark all profiles as pending for re-enrichment"):
            if st.checkbox("⚠️ Confirm reset"):
                try:
                    conn = sqlite3.connect(db_path)
                    conn.execute("UPDATE profiles SET enrichment_status = 'pending'")
                    conn.commit()
                    conn.close()
                    st.success("✅ All profiles reset to pending")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

        st.markdown("---")
        st.subheader("📖 Help")
        st.markdown("""
        **Quick Guide:**
        1. **Add Profiles** - Paste URLs, click Process
        2. **View Data** - Browse and filter profiles
        3. **Edit** - Modify individual records
        4. **Analytics** - View statistics
        5. **Export** - Download as CSV/Excel/JSON
        """)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()

