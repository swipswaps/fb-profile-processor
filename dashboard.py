#!/usr/bin/env python3
"""
Facebook Data Dashboard - Schema-Adaptive Multi-Database Viewer
Supports both Facebook Profile data and Marketplace Listings

USAGE:
    streamlit run dashboard.py
    streamlit run dashboard.py -- --database custom.db
"""

import streamlit as st
import pandas as pd
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

# Configure logging (Rule 25 - Comprehensive Application Logging)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('dashboard')

# Import marketplace API functions
try:
    from marketplace_scraper import (
        get_facebook_api, get_access_token, set_access_token,
        get_catalog_id, set_catalog_id, test_access_token,
        test_catalog_access, get_available_catalogs, FacebookMarketplaceAPI,
        get_commerce_api, FacebookCommerceAPI, run_preflight_compliance_check,
        ComplianceGate
    )
    MARKETPLACE_API_AVAILABLE = True
    logger.info("Marketplace API module loaded successfully")
except ImportError as e:
    MARKETPLACE_API_AVAILABLE = False
    logger.warning(f"Marketplace API not available: {e}")

# Page configuration
st.set_page_config(
    page_title="Facebook Data Dashboard",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SCHEMA DETECTION (ChatGPT-inspired, enhanced)
# =============================================================================

def detect_schema_type(db_path: str) -> tuple[str, str, list]:
    """
    Detect database schema type by inspecting tables and columns.

    Returns:
        (schema_type, table_name, column_list)
        schema_type: 'profile', 'marketplace', or 'unknown'
    """
    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        if not tables:
            conn.close()
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


@st.cache_data
def load_data(db_path: str) -> tuple[pd.DataFrame, str, list]:
    """
    Load data from SQLite database with schema detection.

    Returns:
        (dataframe, schema_type, columns)
    """
    schema_type, table_name, columns = detect_schema_type(db_path)

    if schema_type in ('empty', 'error'):
        return pd.DataFrame(), schema_type, []

    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)

        # Order by appropriate column based on schema
        order_col = 'updated_at' if 'updated_at' in columns else 'id'
        order_dir = 'DESC' if order_col in columns else ''

        query = f"SELECT * FROM {table_name}"
        if order_col in columns:
            query += f" ORDER BY {order_col} DESC"

        df = pd.read_sql_query(query, conn)
        conn.close()

        logger.info(f"Loaded {len(df)} records from {table_name}")
        return df, schema_type, columns

    except Exception as e:
        logger.error(f"Error loading database: {e}")
        st.error(f"Error loading database: {e}")
        return pd.DataFrame(), 'error', []


def safe_col(df: pd.DataFrame, col: str, default=None):
    """Safely get column from dataframe, return default if missing."""
    return df[col] if col in df.columns else default


def get_database_stats(df: pd.DataFrame, schema_type: str) -> dict:
    """Calculate database statistics based on schema type."""
    if df.empty:
        return {'total_records': 0}

    stats = {'total_records': len(df)}

    if schema_type == 'profile':
        # Profile schema stats
        if 'error' in df.columns:
            stats['successful'] = len(df[df['error'].isna()])
            stats['errors'] = len(df[df['error'].notna()])
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

    elif schema_type == 'marketplace':
        # Marketplace schema stats
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

    return stats


def main():
    # Sidebar - Database selection (do this first to detect schema)
    st.sidebar.header("⚙️ Settings")

    # Find available databases
    db_files = list(Path('.').glob('*.db'))
    db_options = [str(f) for f in db_files]

    if not db_options:
        st.error("No database files found in current directory")
        st.info("Run `python3 fb_profile_processor.py` or `python3 marketplace_scraper.py` first")
        return

    # Smart default: prefer marketplace.db, then test_profiles.db
    if 'marketplace.db' in db_options:
        default_db = 'marketplace.db'
    elif 'test_profiles.db' in db_options:
        default_db = 'test_profiles.db'
    else:
        default_db = db_options[0]

    selected_db = st.sidebar.selectbox(
        "Select Database",
        db_options,
        index=db_options.index(default_db) if default_db in db_options else 0
    )

    # Load data with schema detection
    df, schema_type, columns = load_data(selected_db)

    # Dynamic title based on schema
    if schema_type == 'marketplace':
        st.title("🛒 Facebook Marketplace Dashboard")
        st.markdown("Interactive viewer for your Marketplace listings")
    elif schema_type == 'profile':
        st.title("🔗 Facebook Profile Processor Dashboard")
        st.markdown("Interactive database viewer for processed Facebook profiles")
    else:
        st.title("📊 Database Viewer")
        st.markdown(f"Viewing: {selected_db}")

    # Schema indicator
    schema_badges = {
        'marketplace': ('🛒 Marketplace', 'success'),
        'profile': ('👤 Profiles', 'info'),
        'unknown': ('❓ Unknown', 'warning'),
        'empty': ('📭 Empty', 'error'),
        'error': ('❌ Error', 'error'),
    }
    badge_text, badge_type = schema_badges.get(schema_type, ('❓', 'warning'))

    if badge_type == 'success':
        st.sidebar.success(f"Schema: {badge_text}")
    elif badge_type == 'info':
        st.sidebar.info(f"Schema: {badge_text}")
    elif badge_type == 'warning':
        st.sidebar.warning(f"Schema: {badge_text}")
    else:
        st.sidebar.error(f"Schema: {badge_text}")

    if df.empty:
        st.warning(f"Database '{selected_db}' is empty or could not be loaded")
        if schema_type == 'error':
            st.info("Check that the file exists and is a valid SQLite database")
        return

    # Database statistics (schema-aware)
    stats = get_database_stats(df, schema_type)

    # Sidebar metrics (schema-aware)
    st.sidebar.markdown("---")
    st.sidebar.metric("Total Records", stats['total_records'])

    if schema_type == 'marketplace':
        st.sidebar.metric("Available", stats.get('available', 0))
        st.sidebar.metric("Sold", stats.get('sold', 0))
        if stats.get('ready_to_bump', 0) > 0:
            st.sidebar.metric("Ready to Bump", stats.get('ready_to_bump', 0))
    elif schema_type == 'profile':
        st.sidebar.metric("Successful", stats.get('successful', 0))
        st.sidebar.metric("Errors", stats.get('errors', 0))
        if 'enrichment_status' in df.columns:
            st.sidebar.markdown("### Enrichment Status")
            st.sidebar.metric("Pending", stats.get('pending_enrichment', 0))
            st.sidebar.metric("Enriched", stats.get('enriched', 0))

    # Route to schema-specific view
    if schema_type == 'marketplace':
        render_marketplace_dashboard(df, stats)
    elif schema_type == 'profile':
        render_profile_dashboard(df, stats)
    else:
        render_generic_dashboard(df, stats)


def render_marketplace_dashboard(df: pd.DataFrame, stats: dict):
    """Render dashboard for Marketplace listings schema."""

    # Tabs for marketplace
    if MARKETPLACE_API_AVAILABLE:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🏠 Listings", "🔍 Data Explorer", "📈 Analytics", "💾 Export", "🔑 API Config"
        ])
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "🏠 Listings", "🔍 Data Explorer", "📈 Analytics", "💾 Export"
        ])

    # Tab 1: Listings Grid
    with tab1:
        st.header("Your Marketplace Listings")

        # Metrics row
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total", stats['total_records'])
        col2.metric("Available", stats.get('available', 0))
        col3.metric("Sold", stats.get('sold', 0))
        col4.metric("Drafts", stats.get('draft', 0))
        col5.metric("With Prices", stats.get('with_price', 0))

        st.markdown("---")

        # Status filter
        status_options = ['All'] + list(df['status'].dropna().unique()) if 'status' in df.columns else ['All']
        status_filter = st.selectbox("Filter by Status", status_options)

        filtered_df = df.copy()
        if status_filter != 'All' and 'status' in df.columns:
            filtered_df = filtered_df[filtered_df['status'] == status_filter]

        st.info(f"Showing {len(filtered_df)} of {len(df)} listings")

        # Display listings as cards (3 columns)
        cols_per_row = 3
        for i in range(0, len(filtered_df), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                if i + j < len(filtered_df):
                    row = filtered_df.iloc[i + j]
                    with col:
                        render_listing_card(row)

    # Tab 2: Data Explorer (reuse existing logic)
    with tab2:
        render_data_explorer(df)

    # Tab 3: Analytics
    with tab3:
        render_marketplace_analytics(df, stats)

    # Tab 4: Export
    with tab4:
        render_export_tab(df, 'marketplace')

    # Tab 5: API Config (if available)
    if MARKETPLACE_API_AVAILABLE:
        with tab5:
            render_api_config_tab()


def render_listing_card(row: pd.Series):
    """Render a single marketplace listing as a card."""
    item_id = row.get('item_id', row.get('id', 'N/A'))
    title = row.get('title', 'Untitled')[:60]
    price = row.get('price', 'N/A')
    status = row.get('status', 'unknown')

    # Status badge
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
        image_path = Path(f"marketplace_images/{item_id}.jpg")
        if image_path.exists():
            st.image(str(image_path), use_container_width=True)
        else:
            st.markdown("📷 *No image*")

        st.markdown(f"**{title}**")
        st.markdown(f"{status_icon} {status.title()} | **{price}**")

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

        # Link
        st.markdown(f"[View on Facebook](https://facebook.com/marketplace/item/{item_id})")
        st.markdown("---")


def render_marketplace_analytics(df: pd.DataFrame, stats: dict):
    """Render analytics for marketplace data."""
    st.header("Marketplace Analytics")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Status Distribution")
        if 'status' in df.columns:
            status_counts = df['status'].value_counts()
            st.bar_chart(status_counts)
        else:
            st.info("No status data available")

    with col2:
        st.subheader("Price Distribution")
        if 'price_numeric' in df.columns and df['price_numeric'].notna().any():
            # Filter out extreme outliers for visualization
            prices = df['price_numeric'].dropna()
            prices = prices[prices < prices.quantile(0.95)]  # Remove top 5%
            st.bar_chart(prices)
        elif 'price' in df.columns:
            st.info("Numeric price data not available")

    st.markdown("---")

    # Bump statistics
    if 'bump_count' in df.columns:
        st.subheader("Bump Statistics")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Bumps Used", stats.get('total_bumps', 0))
        col2.metric("Ready to Bump", stats.get('ready_to_bump', 0))

        # Average bumps per listing
        avg_bumps = df['bump_count'].mean() if df['bump_count'].notna().any() else 0
        col3.metric("Avg Bumps/Listing", f"{avg_bumps:.1f}")


def render_profile_dashboard(df: pd.DataFrame, stats: dict):
    """Render dashboard for Profile processing schema."""

    # Main content - Tabs
    if MARKETPLACE_API_AVAILABLE:
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Overview", "🔍 Data Explorer", "📈 Analytics", "💾 Export", "🔑 API Config"
        ])
    else:
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Overview", "🔍 Data Explorer", "📈 Analytics", "💾 Export"
        ])

    # Tab 1: Overview
    with tab1:
        st.header("Database Overview")

        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Records", stats['total_records'])

        if stats.get('successful', 0) > 0:
            col2.metric("Successful", stats['successful'],
                       delta=f"{stats['successful']/stats['total_records']*100:.1f}%")
        else:
            col2.metric("Successful", 0)

        if stats.get('errors', 0) > 0:
            col3.metric("Errors", stats['errors'],
                       delta=f"{stats['errors']/stats['total_records']*100:.1f}%",
                       delta_color="inverse")
        else:
            col3.metric("Errors", 0)
        col4.metric("Pending Enrichment", stats.get('pending_enrichment', 0))

        st.markdown("---")

        # Recent records
        st.subheader("Recent Records")
        display_cols = ['id', 'input_url', 'clean_url', 'profile_id', 'http_status',
                       'page_title', 'enrichment_status', 'fetched_at']
        available_cols = [col for col in display_cols if col in df.columns]
        st.dataframe(df[available_cols].head(10), use_container_width=True)

    # Tab 2: Data Explorer
    with tab2:
        render_data_explorer(df)

    # Tab 3: Analytics
    with tab3:
        render_profile_analytics(df)

    # Tab 4: Export
    with tab4:
        render_export_tab(df, 'profile')

    # Tab 5: API Configuration (only if marketplace API is available)
    if MARKETPLACE_API_AVAILABLE:
        with tab5:
            render_api_config_tab()


def render_data_explorer(df: pd.DataFrame):
    """Render generic data explorer with filtering and column selection."""
    st.header("Data Explorer")

    # Filters
    col1, col2 = st.columns(2)

    with col1:
        # Status filter - schema-aware
        if 'enrichment_status' in df.columns:
            status_options = ['All'] + list(df['enrichment_status'].dropna().unique())
            status_filter = st.selectbox("Enrichment Status", status_options)
        elif 'status' in df.columns:
            status_options = ['All'] + list(df['status'].dropna().unique())
            status_filter = st.selectbox("Status", status_options)
        else:
            status_filter = 'All'

    with col2:
        # Error filter (only for profile schema)
        if 'error' in df.columns:
            error_filter = st.selectbox("Error Status", ['All', 'Success Only', 'Errors Only'])
        else:
            error_filter = 'All'

    # Apply filters
    filtered_df = df.copy()

    if status_filter != 'All':
        if 'enrichment_status' in df.columns:
            filtered_df = filtered_df[filtered_df['enrichment_status'] == status_filter]
        elif 'status' in df.columns:
            filtered_df = filtered_df[filtered_df['status'] == status_filter]

    if error_filter == 'Success Only' and 'error' in df.columns:
        filtered_df = filtered_df[filtered_df['error'].isna()]
    elif error_filter == 'Errors Only' and 'error' in df.columns:
        filtered_df = filtered_df[filtered_df['error'].notna()]

    # Column selection with smart defaults
    all_columns = list(df.columns)

    # Choose default columns based on schema
    if 'item_id' in all_columns:  # Marketplace
        default_columns = ['item_id', 'title', 'price', 'status', 'bump_count', 'updated_at']
    else:  # Profile
        default_columns = ['id', 'input_url', 'clean_url', 'profile_id', 'http_status',
                          'page_title', 'enrichment_status', 'fetched_at']

    default_columns = [col for col in default_columns if col in all_columns]

    selected_columns = st.multiselect(
        "Select Columns to Display",
        all_columns,
        default=default_columns
    )

    if not selected_columns:
        st.warning("Please select at least one column")
    else:
        st.info(f"Showing {len(filtered_df)} of {len(df)} records")
        st.dataframe(filtered_df[selected_columns], use_container_width=True, height=600)


def render_profile_analytics(df: pd.DataFrame):
    """Render analytics for profile data."""
    st.header("Analytics")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("HTTP Status Distribution")
        if 'http_status' in df.columns:
            status_counts = df['http_status'].value_counts()
            st.bar_chart(status_counts)
        else:
            st.info("No HTTP status data available")

    with col2:
        st.subheader("Enrichment Status Distribution")
        if 'enrichment_status' in df.columns:
            enrichment_counts = df['enrichment_status'].value_counts()
            st.bar_chart(enrichment_counts)
        else:
            st.info("No enrichment status data available")

    st.markdown("---")

    # Timeline
    st.subheader("Processing Timeline")
    if 'fetched_at' in df.columns:
        df_timeline = df.copy()
        df_timeline['fetched_at'] = pd.to_datetime(df_timeline['fetched_at'], errors='coerce')
        df_timeline = df_timeline.dropna(subset=['fetched_at'])

        if not df_timeline.empty:
            df_timeline['date'] = df_timeline['fetched_at'].dt.date
            timeline_counts = df_timeline.groupby('date').size()
            st.line_chart(timeline_counts)
        else:
            st.info("No timeline data available")
    else:
        st.info("No timestamp data available")


def render_export_tab(df: pd.DataFrame, schema_type: str):
    """Render export tab with download buttons."""
    st.header("Export Data")

    st.markdown("Export data to various formats")

    prefix = 'marketplace' if schema_type == 'marketplace' else 'fb_profiles'

    col1, col2, col3 = st.columns(3)

    with col1:
        # CSV Export
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

    with col2:
        # JSON Export
        json_str = df.to_json(orient='records', indent=2)
        st.download_button(
            label="📥 Download JSON",
            data=json_str,
            file_name=f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

    with col3:
        # Excel Export (if openpyxl is available)
        try:
            from io import BytesIO
            buffer = BytesIO()
            df.to_excel(buffer, index=False, engine='openpyxl')
            st.download_button(
                label="📥 Download Excel",
                data=buffer.getvalue(),
                file_name=f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except ImportError:
            st.info("Install openpyxl for Excel export: pip install openpyxl")

    st.markdown("---")

    # Export statistics
    st.subheader("Export Preview")
    st.write(f"**Records to export:** {len(df)}")
    st.write(f"**Columns:** {len(df.columns)}")
    st.dataframe(df.head(5), use_container_width=True)


def render_generic_dashboard(df: pd.DataFrame, stats: dict):
    """Render a generic dashboard for unknown schemas."""
    st.warning("Unknown database schema - showing generic view")
    st.write(f"**Columns:** {list(df.columns)}")

    tab1, tab2 = st.tabs(["📊 Data", "💾 Export"])

    with tab1:
        st.header("Data Viewer")
        st.dataframe(df, use_container_width=True, height=600)

    with tab2:
        render_export_tab(df, 'generic')


def render_api_config_tab():
    """
    Render the API configuration tab for Facebook Commerce API.

    UX Enforcement (per ChatGPT directive):
    - Deduplicated error messages (one failure = one message)
    - Guardrails instead of instructions
    - Disabled buttons when prerequisites not met
    - Environment-only diagnostics when token missing
    """
    st.header("🔑 Facebook API Configuration")

    # Get API status ONCE to avoid duplicate checks
    api = get_facebook_api()
    status = api.get_api_status()
    current_token = get_access_token()
    current_catalog = get_catalog_id()

    # =================================================================
    # BLOCKING BANNER - Single, unified status message
    # =================================================================
    blocking_issues = []
    if not current_token:
        blocking_issues.append(("FB_ACCESS_TOKEN", "Access token not configured"))
    elif not status['api_available']:
        blocking_issues.append(("TOKEN_INVALID", "Token present but API validation failed"))

    if current_token and status['api_available'] and not current_catalog:
        blocking_issues.append(("FB_CATALOG_ID", "Catalog ID not configured"))
    elif current_token and status['api_available'] and not status['catalog_available']:
        blocking_issues.append(("CATALOG_INVALID", "Catalog ID present but access failed"))

    # Show single unified banner (NOT repeated messages)
    if blocking_issues:
        st.error("🚫 **Operations Blocked** - Complete the setup below to enable Marketplace API")

        # Create remediation table
        remediation_data = {
            "FB_ACCESS_TOKEN": {
                "what": "Set `FB_ACCESS_TOKEN` environment variable",
                "where": "[Meta Developer Portal](https://developers.facebook.com/tools/explorer/)",
                "how": "Export in terminal: `export FB_ACCESS_TOKEN='your_token'`"
            },
            "TOKEN_INVALID": {
                "what": "Token validation failed",
                "where": "[Debug Token](https://developers.facebook.com/tools/debug/accesstoken/)",
                "how": "Generate a new token with required permissions"
            },
            "FB_CATALOG_ID": {
                "what": "Set `FB_CATALOG_ID` environment variable or configure below",
                "where": "[Commerce Manager](https://business.facebook.com/commerce/)",
                "how": "Find your catalog ID in Commerce Manager → Settings"
            },
            "CATALOG_INVALID": {
                "what": "Cannot access the configured catalog",
                "where": "[Commerce Manager](https://business.facebook.com/commerce/)",
                "how": "Verify catalog ID and token permissions"
            }
        }

        for issue_key, issue_desc in blocking_issues:
            rem = remediation_data.get(issue_key, {})
            with st.expander(f"❌ {issue_desc}", expanded=True):
                st.markdown(f"**What to do:** {rem.get('what', 'Unknown')}")
                st.markdown(f"**Where:** {rem.get('where', 'Unknown')}")
                st.markdown(f"**How:** {rem.get('how', 'Unknown')}")

        st.info("💡 This app will automatically unlock when environment variables are detected.")
        st.caption("Note: Restart the app after setting environment variables")
    else:
        st.success("✅ **All Systems Operational** - Marketplace API ready")

    st.markdown("---")

    # =================================================================
    # STATUS INDICATORS (read-only, always shown)
    # =================================================================
    st.subheader("📊 API Status")

    col1, col2, col3 = st.columns(3)
    with col1:
        if status['api_available']:
            st.success("✅ API Connected")
        elif current_token:
            st.error("❌ API Error")
        else:
            st.warning("⏸️ Token Required")
    with col2:
        if status['catalog_available']:
            st.success("✅ Catalog Connected")
        elif current_catalog:
            st.error("❌ Catalog Error")
        else:
            st.warning("⏸️ Catalog Required")
    with col3:
        if status['user_info']:
            st.info(f"👤 {status['user_info'].get('name', 'Unknown')}")
        else:
            st.caption("👤 Not authenticated")

    # API Version (shown only if we have a token)
    if current_token:
        api_version_status = status.get('api_version_status', {})
        if api_version_status.get('warning'):
            st.warning(api_version_status['warning'])
        else:
            st.caption(f"API Version: {status.get('api_version', 'Unknown')} "
                      f"(~{api_version_status.get('months_until_deprecation', '?')} months until deprecation)")

        if status['permissions']:
            st.write("**Granted Permissions:**", ", ".join(status['permissions']))

    st.markdown("---")

    # =================================================================
    # COMPLIANCE STATUS (only shown when token is present)
    # =================================================================
    st.subheader("🔒 Compliance Status")

    if not current_token:
        st.caption("Compliance checks require an access token. Configure token below.")
    else:
        # Token is present - try to get Commerce API for enhanced status
        try:
            commerce_api = get_commerce_api()
            if commerce_api:
                gate = run_preflight_compliance_check(commerce_api)
                compliance_status = gate.get_status()

                # State machine display
                comp_status = commerce_api.get_status()
                state_machine = comp_status.get("state_machine", {})

                if state_machine.get("states"):
                    st.write("**Authentication Pipeline:**")
                    cols = st.columns(5)
                    for i, state in enumerate(state_machine["states"]):
                        with cols[i]:
                            st.metric(
                                label=state["name"],
                                value=state["status"],
                                help=f"Step {state['step']}"
                            )

                    if state_machine.get("all_ok"):
                        st.success(f"✅ {state_machine.get('summary', 'All systems operational')}")
                    else:
                        st.error(f"🚫 {state_machine.get('summary', 'Blocked')}")

                # Compliance gate status
                if compliance_status["blocking_count"] > 0:
                    st.error(f"**{compliance_status['blocking_count']} Blocking Issue(s)** - Cannot proceed")
                    for issue in compliance_status["blocking_issues"]:
                        with st.expander(f"❌ {issue['key']}", expanded=True):
                            st.write(f"**Why Meta requires this:** {issue['reason']}")
                            if issue.get("fix_steps"):
                                st.info(f"**How to fix:** {issue['fix_steps']}")
                            if issue.get("fix_url"):
                                st.markdown(f"[Open in Business Manager]({issue['fix_url']})")
                elif compliance_status["warning_count"] > 0:
                    st.warning(f"**{compliance_status['warning_count']} Warning(s)** - Proceed with caution")
                    for warn in compliance_status["warnings"]:
                        st.caption(f"⚠️ {warn['key']}: {warn['reason']}")
                else:
                    st.success("✅ All compliance checks passed")

                # Mode selector
                st.markdown("---")
                st.write("**Operation Mode:**")
                current_mode = comp_status.get("mode", "interactive")

                col_mode1, col_mode2 = st.columns(2)
                with col_mode1:
                    if current_mode == "interactive":
                        st.info("🧪 **Setup/Diagnostic Mode** (Human token OK)")
                    else:
                        if st.button("Switch to Setup Mode"):
                            success, msg = commerce_api.set_mode(FacebookCommerceAPI.MODE_INTERACTIVE)
                            if success:
                                st.success(msg)
                                st.rerun()
                with col_mode2:
                    if current_mode == "background":
                        st.success("🔒 **Production Mode** (System User required)")
                    else:
                        if st.button("Switch to Production Mode"):
                            success, msg = commerce_api.set_mode(FacebookCommerceAPI.MODE_BACKGROUND)
                            if success:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                # Pre-flight check button
                st.markdown("---")
                if st.button("🛫 Run Pre-flight Compliance Check"):
                    gate = commerce_api.run_preflight_check()
                    can_proceed, message = gate.can_proceed("API operation")
                    if can_proceed:
                        st.success(f"✅ {message}")
                    else:
                        st.error(message)
            else:
                st.info("Commerce API not available - check token permissions")
        except Exception as e:
            st.caption(f"Compliance check unavailable: {e}")

    st.markdown("---")

    # =================================================================
    # ACCESS TOKEN CONFIGURATION (with guardrails)
    # =================================================================
    st.subheader("🔐 Access Token")

    # Show current token status (not repeated)
    token_display = f"{current_token[:20]}..." if current_token else "Not set"
    st.write(f"**Current Token:** `{token_display}`")

    with st.form("token_form"):
        new_token = st.text_input(
            "Enter Access Token",
            type="password",
            help="Your Facebook Graph API access token from developers.facebook.com"
        )
        submit_token = st.form_submit_button("Save & Test Token")

        if submit_token and new_token:
            with st.spinner("Testing token..."):
                is_valid, result = test_access_token(new_token)
                if is_valid:
                    set_access_token(new_token)
                    st.success(f"✅ Token valid! User: {result.get('fb_name', 'Unknown')}")
                    st.rerun()
                else:
                    st.error(f"❌ Invalid token: {result}")

    st.markdown("---")

    # =================================================================
    # CATALOG CONFIGURATION (with guardrails)
    # =================================================================
    st.subheader("📦 Product Catalog")

    st.write(f"**Current Catalog ID:** `{current_catalog or 'Not set'}`")

    # Guardrail: Disable catalog fetch if no token
    if not current_token:
        st.caption("⏸️ Configure access token first to browse catalogs")
    elif status['api_available']:
        with st.expander("🔍 Find Available Catalogs"):
            if st.button("Fetch My Catalogs"):
                with st.spinner("Fetching catalogs..."):
                    catalogs = get_available_catalogs()
                    if catalogs:
                        st.write("**Available Catalogs:**")
                        for cat in catalogs:
                            st.write(f"- **{cat.get('name')}** (ID: `{cat.get('id')}`) "
                                   f"- {cat.get('product_count', 0)} products")
                    else:
                        st.warning("No catalogs found. Create one in Commerce Manager.")
    else:
        st.caption("⏸️ Fix token issues above to browse catalogs")

    with st.form("catalog_form"):
        new_catalog = st.text_input(
            "Enter Catalog ID",
            value=current_catalog or "",
            help="Your Facebook Product Catalog ID"
        )
        submit_catalog = st.form_submit_button("Save & Test Catalog")

        if submit_catalog and new_catalog:
            token = get_access_token()
            if not token:
                st.error("Please set an access token first")
            else:
                with st.spinner("Testing catalog access..."):
                    is_valid, result = test_catalog_access(token, new_catalog)
                    if is_valid:
                        set_catalog_id(new_catalog)
                        st.success(f"✅ Catalog connected! "
                                 f"Name: {result.get('name')}, "
                                 f"Products: {result.get('product_count', 0)}")
                        st.rerun()
                    else:
                        st.error(f"❌ Cannot access catalog: {result}")

    st.markdown("---")

    # =================================================================
    # LIVE API TESTING (with guardrails)
    # =================================================================
    st.subheader("🧪 Live API Testing")

    # Guardrail: Clearly indicate when live tests are not possible
    if not current_token:
        st.caption("⏸️ **Environment-Only Mode** - Live API tests disabled until token configured")
        st.button("Test Catalog Products API", disabled=True, help="Configure access token first")
    elif not status['api_available']:
        st.caption("⏸️ **Environment-Only Mode** - Token validation failed")
        st.button("Test Catalog Products API", disabled=True, help="Fix token issues first")
    elif not status['catalog_available']:
        st.caption("⏸️ **Catalog Required** - Configure catalog ID to test product API")
        st.button("Test Catalog Products API", disabled=True, help="Configure catalog first")
    else:
        st.caption("✅ **Live Mode** - API testing enabled")
        if st.button("Test Catalog Products API"):
            api = get_facebook_api(force_refresh=True)
            with st.spinner("Fetching products..."):
                products = api.get_catalog_products(limit=5)
                if products:
                    st.success(f"✅ Found {len(products)} products")
                    st.json(products)
                else:
                    st.warning("No products found in catalog")


if __name__ == '__main__':
    main()


