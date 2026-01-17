#!/usr/bin/env python3
"""
Facebook Profile Processor - Simplified Dashboard
Simple, working UI: URLs → Data → Export

USAGE:
    streamlit run dashboard_simple.py
"""

import streamlit as st
import pandas as pd
import sqlite3
import fb_profile_processor as processor
import time
import os
from datetime import datetime

st.set_page_config(
    page_title="Facebook Profile Processor",
    page_icon="🔗",
    layout="wide"
)

# Enable text selection everywhere with visible highlight
st.markdown("""
<style>
    /* Enable text selection globally */
    * {
        user-select: text !important;
        -webkit-user-select: text !important;
        -moz-user-select: text !important;
        -ms-user-select: text !important;
    }

    /* Enable selection in dataframes */
    .stDataFrame, .stDataFrame * {
        user-select: text !important;
        -webkit-user-select: text !important;
    }

    /* Enable selection in tables */
    table, table * {
        user-select: text !important;
        -webkit-user-select: text !important;
    }

    /* Show selection highlight */
    ::selection {
        background-color: #4A90E2 !important;
        color: white !important;
    }

    ::-moz-selection {
        background-color: #4A90E2 !important;
        color: white !important;
    }

    /* Force selection highlight in dataframe cells */
    .stDataFrame *::selection,
    table td::selection,
    table th::selection {
        background-color: #4A90E2 !important;
        color: white !important;
    }

    .stDataFrame *::-moz-selection,
    table td::-moz-selection,
    table th::-moz-selection {
        background-color: #4A90E2 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ======================
# SESSION STATE INIT
# ======================

if 'processing_complete' not in st.session_state:
    st.session_state.processing_complete = False
if 'last_results' not in st.session_state:
    st.session_state.last_results = None

# ======================
# SIDEBAR: DATABASE
# ======================

st.sidebar.title("⚙️ Database")

# Find all .db files
db_files = [f for f in os.listdir('.') if f.endswith('.db')]
if not db_files:
    st.sidebar.error("No .db files found!")
    st.stop()

selected_db = st.sidebar.selectbox("Select Database", db_files, key="db_select")

# Show database info
try:
    conn = sqlite3.connect(selected_db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM profiles")
    total_count = cur.fetchone()[0]
    conn.close()
    st.sidebar.metric("Total Records", total_count)
except Exception as e:
    st.sidebar.warning(f"Database error: {e}")

# ======================
# MAIN TITLE
# ======================

st.title("🔗 Facebook Profile Processor")
st.caption("Simple workflow: Paste URLs → Process → View Data → Export")

# ======================
# TABS
# ======================

tab1, tab2, tab3, tab4 = st.tabs(["📥 Process URLs", "📊 View Data", "✏️ Edit Data", "💾 Export"])

# ======================
# TAB 1: PROCESS URLs
# ======================

with tab1:
    st.subheader("📥 Process Facebook Profile URLs")

    # URL input
    url_text = st.text_area(
        "Paste Facebook Marketplace URLs (one per line):",
        height=200,
        placeholder="https://www.facebook.com/marketplace/profile/100010505562305/?referralSurface=messenger_banner&referralCode=4\nhttps://www.facebook.com/marketplace/profile/100001669012324/?referralSurface=messenger_banner&referralCode=4",
        key="url_input"
    )

    # Parse URLs
    urls = []
    if url_text:
        urls = [u.strip() for u in url_text.split('\n') 
                if u.strip() and u.strip().lower().startswith('http')]

    # Show URL count
    if urls:
        st.success(f"✅ Found {len(urls)} valid URL(s)")
    else:
        st.info("ℹ️ Paste URLs above to get started")

    # Settings (collapsed)
    with st.expander("⚙️ Advanced Settings"):
        col1, col2 = st.columns(2)
        with col1:
            rate_limit = st.slider(
                "Delay between requests (seconds)", 
                0.5, 5.0, 1.0,
                help="Higher = slower but safer"
            )
        with col2:
            timeout = st.slider(
                "Request timeout (seconds)", 
                5, 60, 15,
                help="How long to wait for each request"
            )

    # THE BUTTON
    button_clicked = st.button(
        "🚀 Process URLs", 
        disabled=(len(urls) == 0),
        use_container_width=True,
        type="primary",
        key="process_button"
    )

    # PROCESS URLS (with session state management)
    if button_clicked:
        st.session_state.processing_complete = False
        st.session_state.last_results = None

        st.info(f"🔄 Processing {len(urls)} URLs...")

        # Progress indicators
        progress_bar = st.progress(0)
        status_text = st.empty()
        results_container = st.container()

        success_count = 0
        error_count = 0
        skipped_count = 0

        # Process each URL
        for i, url in enumerate(urls):
            # Update progress
            progress_bar.progress((i + 1) / len(urls))
            status_text.text(f"Processing {i+1}/{len(urls)}: {url[:60]}...")

            try:
                # Process single URL
                result = processor.process_single_url(url, selected_db, timeout)

                # Show immediate feedback
                with results_container:
                    if result.get('success'):
                        st.success(f"✅ {i+1}/{len(urls)}: Profile ID {result.get('profile_id', 'N/A')}")
                        success_count += 1
                    elif result.get('error') == 'URL already processed':
                        st.info(f"⊘ {i+1}/{len(urls)}: Already in database")
                        skipped_count += 1
                    else:
                        st.error(f"❌ {i+1}/{len(urls)}: {result.get('error', 'Unknown error')}")
                        error_count += 1

            except Exception as e:
                with results_container:
                    st.error(f"❌ {i+1}/{len(urls)}: Exception: {str(e)}")
                error_count += 1

            # Rate limiting
            if i < len(urls) - 1:
                time.sleep(rate_limit)

        # Final summary
        progress_bar.progress(1.0)
        status_text.text("✅ Processing complete!")

        st.success(f"""
        ✅ **Processing Complete!**

        - Total URLs: {len(urls)}
        - Successful: {success_count}
        - Skipped (duplicates): {skipped_count}
        - Failed: {error_count}

        👉 Switch to **View Data** tab to see profiles
        """)

        # Save results to session state
        st.session_state.processing_complete = True
        st.session_state.last_results = {
            'total': len(urls),
            'success': success_count,
            'skipped': skipped_count,
            'errors': error_count
        }

        # Wait a moment then rerun to refresh data
        time.sleep(2)
        st.rerun()

# ======================
# TAB 2: VIEW DATA
# ======================

with tab2:
    st.subheader("📊 Profile Data")

    # Show last processing results if available
    if st.session_state.processing_complete and st.session_state.last_results:
        result = st.session_state.last_results
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Processed", result['total'])
        col2.metric("Successful", result['success'])
        col3.metric("Skipped", result['skipped'])
        col4.metric("Errors", result['errors'])
        st.divider()

    # Load data from database
    try:
        conn = sqlite3.connect(selected_db)

        # Detect schema
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(profiles)")
        columns = {row[1] for row in cur.fetchall()}

        # Query based on schema
        if 'fb_id' in columns:
            # New schema
            df = pd.read_sql_query(
                "SELECT id, fb_id, fb_name, fb_username, input_url, created_at FROM profiles ORDER BY id DESC LIMIT 100",
                conn
            )
        else:
            # Old schema
            df = pd.read_sql_query(
                "SELECT id, profile_id, page_title, clean_url, created_at FROM profiles ORDER BY id DESC LIMIT 100",
                conn
            )

        conn.close()

        if len(df) > 0:
            # Display data
            st.dataframe(df, use_container_width=True, height=400)
            st.caption(f"Showing {len(df)} most recent records")

            # Bulk operations
            st.divider()
            st.subheader("🗑️ Bulk Operations")

            col1, col2 = st.columns([3, 1])

            with col1:
                delete_ids = st.text_input(
                    "Enter profile IDs to delete (comma-separated):",
                    placeholder="e.g., 1,2,3",
                    help="Enter the ID numbers from the table above"
                )

            with col2:
                st.write("")  # Spacing
                st.write("")  # Spacing
                if st.button("🗑️ Delete Selected", type="secondary", use_container_width=True):
                    if delete_ids:
                        try:
                            # Parse IDs
                            ids_to_delete = [int(x.strip()) for x in delete_ids.split(',') if x.strip()]

                            if ids_to_delete:
                                # Delete from database
                                conn_delete = sqlite3.connect(selected_db)
                                cur_delete = conn_delete.cursor()

                                placeholders = ','.join('?' * len(ids_to_delete))
                                cur_delete.execute(f"DELETE FROM profiles WHERE id IN ({placeholders})", ids_to_delete)

                                deleted_count = cur_delete.rowcount
                                conn_delete.commit()
                                conn_delete.close()

                                st.success(f"✅ Deleted {deleted_count} profile(s)")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.warning("⚠️ No valid IDs provided")
                        except ValueError:
                            st.error("❌ Invalid ID format. Use comma-separated numbers.")
                        except Exception as e:
                            st.error(f"❌ Delete failed: {e}")
                    else:
                        st.warning("⚠️ Enter IDs to delete")
        else:
            st.info("📭 No data yet. Process some URLs first!")

    except Exception as e:
        st.error(f"Error loading data: {e}")

# ======================
# TAB 3: EDIT DATA (CRUD)
# ======================

with tab3:
    st.subheader("✏️ Edit Profile Data")

    try:
        conn = sqlite3.connect(selected_db)

        # Get all profiles
        df = pd.read_sql_query(
            "SELECT id, fb_id, fb_name, fb_username, input_url, created_at FROM profiles ORDER BY id DESC",
            conn
        )

        if len(df) > 0:
            # Select profile to edit
            profile_options = [f"ID {row['id']}: {row['fb_name'] or row['fb_id'] or 'Unknown'}"
                             for _, row in df.iterrows()]

            selected_profile = st.selectbox(
                "Select profile to edit:",
                options=range(len(df)),
                format_func=lambda i: profile_options[i]
            )

            profile_id = df.iloc[selected_profile]['id']

            st.divider()

            # Load full profile data
            cur = conn.cursor()
            cur.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
            columns = [desc[0] for desc in cur.description]
            row = cur.fetchone()
            profile_data = dict(zip(columns, row))

            # Create edit form
            st.subheader(f"Editing Profile ID: {profile_id}")

            with st.form(key=f"edit_form_{profile_id}"):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Core Identity**")
                    fb_id = st.text_input("Facebook ID", value=profile_data.get('fb_id') or '')
                    fb_username = st.text_input("Username", value=profile_data.get('fb_username') or '')
                    fb_name = st.text_input("Name", value=profile_data.get('fb_name') or '')
                    fb_first_name = st.text_input("First Name", value=profile_data.get('fb_first_name') or '')
                    fb_last_name = st.text_input("Last Name", value=profile_data.get('fb_last_name') or '')

                with col2:
                    st.markdown("**Contact & Profile**")
                    fb_email = st.text_input("Email", value=profile_data.get('fb_email') or '')
                    fb_bio = st.text_area("Bio", value=profile_data.get('fb_bio') or '', height=100)
                    fb_location_name = st.text_input("Location", value=profile_data.get('fb_location_name') or '')
                    fb_website = st.text_input("Website", value=profile_data.get('fb_website') or '')

                st.markdown("**URLs**")
                col3, col4 = st.columns(2)
                with col3:
                    input_url = st.text_input("Input URL", value=profile_data.get('input_url') or '')
                with col4:
                    fb_link = st.text_input("Facebook Link", value=profile_data.get('fb_link') or '')

                # Submit buttons
                col_save, col_delete = st.columns([3, 1])

                with col_save:
                    submit_update = st.form_submit_button("💾 Save Changes", use_container_width=True, type="primary")

                with col_delete:
                    submit_delete = st.form_submit_button("🗑️ Delete", use_container_width=True)

                if submit_update:
                    # Update database
                    try:
                        cur.execute("""
                            UPDATE profiles SET
                                fb_id = ?,
                                fb_username = ?,
                                fb_name = ?,
                                fb_first_name = ?,
                                fb_last_name = ?,
                                fb_email = ?,
                                fb_bio = ?,
                                fb_location_name = ?,
                                fb_website = ?,
                                input_url = ?,
                                fb_link = ?,
                                updated_at = datetime('now')
                            WHERE id = ?
                        """, (
                            fb_id or None,
                            fb_username or None,
                            fb_name or None,
                            fb_first_name or None,
                            fb_last_name or None,
                            fb_email or None,
                            fb_bio or None,
                            fb_location_name or None,
                            fb_website or None,
                            input_url or None,
                            fb_link or None,
                            profile_id
                        ))
                        conn.commit()
                        st.success(f"✅ Profile ID {profile_id} updated successfully!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Update failed: {e}")

                if submit_delete:
                    # Delete profile
                    try:
                        cur.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
                        conn.commit()
                        st.success(f"✅ Profile ID {profile_id} deleted!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Delete failed: {e}")

            conn.close()

        else:
            st.info("📭 No profiles to edit. Process some URLs first!")
            conn.close()

    except Exception as e:
        st.error(f"Error loading profiles: {e}")

# ======================
# TAB 4: EXPORT
# ======================

with tab4:
    st.subheader("💾 Export Data")

    try:
        conn = sqlite3.connect(selected_db)
        df = pd.read_sql_query("SELECT * FROM profiles", conn)
        conn.close()

        if len(df) > 0:
            st.info(f"📊 Ready to export {len(df)} records")

            col1, col2 = st.columns(2)

            with col1:
                # CSV download
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Download CSV",
                    csv,
                    f"profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    "text/csv",
                    use_container_width=True
                )

            with col2:
                # JSON download
                json_str = df.to_json(orient='records', indent=2)
                st.download_button(
                    "📥 Download JSON",
                    json_str,
                    f"profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    "application/json",
                    use_container_width=True
                )

            # Preview
            with st.expander("👁️ Preview Data"):
                st.dataframe(df.head(10), use_container_width=True)

        else:
            st.info("📭 No data to export yet. Process some URLs first!")

    except Exception as e:
        st.error(f"Error preparing export: {e}")

# ======================
# FOOTER
# ======================

st.divider()
st.caption("Facebook Profile Processor - Simplified Dashboard")


