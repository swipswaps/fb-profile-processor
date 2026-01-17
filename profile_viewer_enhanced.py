#!/usr/bin/env python3
"""
Enhanced Profile Viewer with Export Functionality
Based on receipts-ocr UX pattern: https://swipswaps.github.io/receipts-ocr/

Features:
- Modern card-based layout
- Multi-select with visual feedback
- Export to TXT, CSV, XLSX, SQL, JSON
- Search and filter
- Responsive design
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from export_functionality import (
    create_csv_download,
    create_excel_download,
    create_txt_download,
    create_sql_download,
    create_json_download
)


def init_session_state():
    """Initialize session state variables"""
    if 'selected_profiles' not in st.session_state:
        st.session_state.selected_profiles = set()
    if 'search_query' not in st.session_state:
        st.session_state.search_query = ""


def load_profiles(db_path: str = "test_profiles.db") -> pd.DataFrame:
    """Load profiles from database"""
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            id,
            fb_id,
            fb_name,
            fb_location_name,
            fb_join_date,
            fb_active_listings_count,
            fb_response_rate,
            fb_response_time,
            fb_seller_badges,
            fb_picture_url,
            fb_cover_url,
            enriched_at,
            input_url
        FROM profiles
        WHERE enrichment_status IN ('enriched', 'partial')
          AND fb_name IS NOT NULL
        ORDER BY enriched_at DESC
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


def render_profile_card(profile: pd.Series, index: int, is_selected: bool):
    """
    Render a single profile card with selection checkbox.
    
    Args:
        profile: Profile data series
        index: Profile index
        is_selected: Whether profile is currently selected
    """
    # Create card container with selection highlighting
    card_style = """
        background-color: #f0f8ff;
        border: 2px solid #4a90e2;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    """ if is_selected else """
        background-color: #ffffff;
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    """

    with st.container():
        st.markdown(f'<div style="{card_style}">', unsafe_allow_html=True)

        # Header row: checkbox, name, and actions
        col1, col2, col3 = st.columns([0.5, 3, 1])

        with col1:
            # Selection checkbox
            checked = st.checkbox(
                "",
                value=is_selected,
                key=f"select_{profile['id']}",
                label_visibility="collapsed"
            )

            if checked and profile['id'] not in st.session_state.selected_profiles:
                st.session_state.selected_profiles.add(profile['id'])
            elif not checked and profile['id'] in st.session_state.selected_profiles:
                st.session_state.selected_profiles.remove(profile['id'])

        with col2:
            # Profile name and basic info
            st.markdown(f"### {profile['fb_name']}")

            # Location and join date
            info_parts = []
            if pd.notna(profile['fb_location_name']):
                info_parts.append(f"📍 {profile['fb_location_name']}")
            if pd.notna(profile['fb_join_date']):
                info_parts.append(f"📅 {profile['fb_join_date']}")

            if info_parts:
                st.markdown(" | ".join(info_parts))

        with col3:
            # View profile link
            if pd.notna(profile['input_url']):
                st.markdown(f"[View Profile →]({profile['input_url']})")

        # Details section
        col1, col2, col3 = st.columns(3)

        with col1:
            if pd.notna(profile['fb_active_listings_count']):
                st.metric("Active Listings", int(profile['fb_active_listings_count']))
            else:
                st.metric("Active Listings", "—")

        with col2:
            if pd.notna(profile['fb_response_rate']):
                st.metric("Response Rate", profile['fb_response_rate'])
            else:
                st.metric("Response Rate", "N/A")

        with col3:
            if pd.notna(profile['fb_response_time']):
                st.metric("Response Time", profile['fb_response_time'])
            else:
                st.metric("Response Time", "N/A")

        # Additional info in expander
        with st.expander("More Details"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Facebook ID:**")
                st.code(profile['fb_id'])

                if pd.notna(profile['fb_seller_badges']):
                    st.markdown("**Badges:**")
                    st.info(profile['fb_seller_badges'])

            with col2:
                if pd.notna(profile['fb_picture_url']):
                    st.markdown("**Profile Picture:**")
                    st.image(profile['fb_picture_url'], width=100)

                if pd.notna(profile['enriched_at']):
                    st.markdown("**Last Updated:**")
                    st.text(profile['enriched_at'][:19])

        st.markdown('</div>', unsafe_allow_html=True)


def render_export_panel(df: pd.DataFrame, selected_ids: set):
    """
    Render floating export panel.
    
    Args:
        df: Full DataFrame
        selected_ids: Set of selected profile IDs
    """
    if not selected_ids:
        return

    # Filter to selected profiles
    export_df = df[df['id'].isin(selected_ids)].copy()

    # Remove internal columns
    export_df = export_df.drop(columns=['id'], errors='ignore')

    # Create floating panel
    st.markdown("""
        <style>
        .export-panel {
            position: sticky;
            top: 10px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin: 20px 0;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="export-panel">', unsafe_allow_html=True)

        st.markdown(f"### 📦 Export {len(selected_ids)} Selected Profile(s)")

        # Export format selector
        export_format = st.selectbox(
            "Choose format:",
            ["CSV", "Excel (XLSX)", "Text", "SQL", "JSON"],
            key="export_format"
        )

        # Generate appropriate data
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if export_format == "CSV":
            data = create_csv_download(export_df)
            filename = f"profiles_{timestamp}.csv"
            mime = "text/csv"
        elif export_format == "Excel (XLSX)":
            data = create_excel_download(export_df)
            filename = f"profiles_{timestamp}.xlsx"
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif export_format == "Text":
            data = create_txt_download(export_df)
            filename = f"profiles_{timestamp}.txt"
            mime = "text/plain"
        elif export_format == "SQL":
            data = create_sql_download(export_df)
            filename = f"profiles_{timestamp}.sql"
            mime = "text/plain"
        else:  # JSON
            data = create_json_download(export_df)
            filename = f"profiles_{timestamp}.json"
            mime = "application/json"

        # Download button
        st.download_button(
            label=f"⬇️ Download {export_format}",
            data=data,
            file_name=filename,
            mime=mime,
            key="download_btn",
            use_container_width=True
        )

        # Quick actions
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✓ Select All", use_container_width=True):
                st.session_state.selected_profiles = set(df['id'].tolist())
                st.rerun()
        with col2:
            if st.button("✗ Clear All", use_container_width=True):
                st.session_state.selected_profiles = set()
                st.rerun()

        st.markdown('</div>', unsafe_allow_html=True)


def render_search_filter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Render search and filter controls.
    
    Args:
        df: DataFrame to filter
        
    Returns:
        Filtered DataFrame
    """
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search_query = st.text_input(
            "🔍 Search profiles",
            value=st.session_state.search_query,
            placeholder="Search by name, location, or Facebook ID...",
            key="search_input"
        )
        st.session_state.search_query = search_query

    with col2:
        has_listings = st.checkbox("Has Active Listings", value=False)

    with col3:
        has_response_rate = st.checkbox("Has Response Rate", value=False)

    # Apply filters
    filtered_df = df.copy()

    if search_query:
        mask = (
            df['fb_name'].str.contains(search_query, case=False, na=False) |
            df['fb_location_name'].str.contains(search_query, case=False, na=False) |
            df['fb_id'].astype(str).str.contains(search_query, case=False)
        )
        filtered_df = filtered_df[mask]

    if has_listings:
        filtered_df = filtered_df[filtered_df['fb_active_listings_count'].notna()]

    if has_response_rate:
        filtered_df = filtered_df[filtered_df['fb_response_rate'].notna()]

    return filtered_df


def main():
    """Main application"""
    st.set_page_config(
        page_title="Profile Viewer & Exporter",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    # Custom CSS
    st.markdown("""
        <style>
        .main {
            padding: 20px;
        }
        h1 {
            color: #667eea;
            text-align: center;
        }
        .stMetric {
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
        }
        </style>
    """, unsafe_allow_html=True)

    # Initialize
    init_session_state()

    # Header
    st.markdown("# 📊 Facebook Marketplace Profile Viewer")
    st.markdown("*Select profiles to export in various formats (CSV, Excel, SQL, JSON, Text)*")

    # Load data
    try:
        df = load_profiles()
    except Exception as e:
        st.error(f"❌ Error loading data: {e}")
        st.info("💡 Make sure the database exists and contains enriched profiles")
        return

    if df.empty:
        st.warning("⚠️ No enriched profiles found in database")
        st.info("Run the enricher first: `python3 selenium_enricher.py --force`")
        return

    # Statistics bar
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)

    col1.metric("📋 Total Profiles", len(df))
    col2.metric("✅ Selected", len(st.session_state.selected_profiles))
    col3.metric("📦 Active Listings", df['fb_active_listings_count'].notna().sum())
    col4.metric("💬 Response Rate Data", df['fb_response_rate'].notna().sum())

    st.markdown("---")

    # Search and filter
    filtered_df = render_search_filter(df)

    if len(filtered_df) < len(df):
        st.info(f"🔍 Showing {len(filtered_df)} of {len(df)} profiles")

    # Main layout
    col1, col2 = st.columns([2, 1])

    with col1:
        # Profile cards
        st.markdown("### Profiles")

        if filtered_df.empty:
            st.warning("No profiles match your search criteria")
        else:
            for idx, profile in filtered_df.iterrows():
                is_selected = profile['id'] in st.session_state.selected_profiles
                render_profile_card(profile, idx, is_selected)

    with col2:
        # Export panel
        render_export_panel(df, st.session_state.selected_profiles)

        # Help section
        with st.expander("ℹ️ How to Use"):
            st.markdown("""
            **Selection:**
            - Click checkboxes to select individual profiles
            - Use "Select All" to select all profiles
            - Use "Clear All" to deselect all
            
            **Export Formats:**
            - **CSV**: Comma-separated values for Excel/Google Sheets
            - **Excel**: Native .xlsx format with formatting
            - **Text**: Human-readable formatted text
            - **SQL**: INSERT statements for database import
            - **JSON**: Structured data for APIs/programming
            
            **Search:**
            - Search by name, location, or Facebook ID
            - Filter by active listings or response rate
            """)


if __name__ == "__main__":
    main()
