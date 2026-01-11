#!/usr/bin/env python3
"""
Facebook Profile Processor - Database Dashboard
Interactive Streamlit dashboard to view and analyze processed profiles

USAGE:
    streamlit run dashboard.py
    streamlit run dashboard.py -- --database custom.db
"""

import streamlit as st
import pandas as pd
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="FB Profile Processor Dashboard",
    page_icon="🔗",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_data
def load_data(db_path):
    """Load data from SQLite database with caching"""
    try:
        # Read-only connection (Rule 11 - SQLite Safety)
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        
        # Load all data
        df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
        conn.close()
        
        return df
    except Exception as e:
        st.error(f"Error loading database: {e}")
        return pd.DataFrame()


def get_database_stats(df):
    """Calculate database statistics"""
    if df.empty:
        return {}
    
    stats = {
        'total_records': len(df),
        'successful': len(df[df['error'].isna()]),
        'errors': len(df[df['error'].notna()]),
        'pending_enrichment': len(df[df['enrichment_status'] == 'pending']),
        'enriched': len(df[df['enrichment_status'] == 'enriched']),
        'failed_enrichment': len(df[df['enrichment_status'] == 'failed']),
    }
    
    return stats


def main():
    # Title and description
    st.title("🔗 Facebook Profile Processor Dashboard")
    st.markdown("Interactive database viewer for processed Facebook profiles")
    
    # Sidebar - Database selection
    st.sidebar.header("⚙️ Settings")
    
    # Find available databases
    db_files = list(Path('.').glob('*.db'))
    db_options = [str(f) for f in db_files]
    
    if not db_options:
        st.error("No database files found in current directory")
        st.info("Run `python3 fb_profile_processor.py` first to create a database")
        return
    
    # Default to test_profiles.db if it exists
    default_db = 'test_profiles.db' if 'test_profiles.db' in db_options else db_options[0]
    
    selected_db = st.sidebar.selectbox(
        "Select Database",
        db_options,
        index=db_options.index(default_db) if default_db in db_options else 0
    )
    
    # Load data
    df = load_data(selected_db)
    
    if df.empty:
        st.warning(f"Database '{selected_db}' is empty or could not be loaded")
        return
    
    # Database statistics
    stats = get_database_stats(df)
    
    st.sidebar.markdown("---")
    st.sidebar.metric("Total Records", stats['total_records'])
    st.sidebar.metric("Successful", stats['successful'])
    st.sidebar.metric("Errors", stats['errors'])
    
    if 'enrichment_status' in df.columns:
        st.sidebar.markdown("### Enrichment Status")
        st.sidebar.metric("Pending", stats['pending_enrichment'])
        st.sidebar.metric("Enriched", stats['enriched'])
        st.sidebar.metric("Failed", stats['failed_enrichment'])
    
    # Main content - Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "🔍 Data Explorer", "📈 Analytics", "💾 Export"])
    
    # Tab 1: Overview
    with tab1:
        st.header("Database Overview")
        
        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Records", stats['total_records'])
        col2.metric("Successful", stats['successful'], 
                   delta=f"{stats['successful']/stats['total_records']*100:.1f}%")
        col3.metric("Errors", stats['errors'],
                   delta=f"{stats['errors']/stats['total_records']*100:.1f}%",
                   delta_color="inverse")
        col4.metric("Pending Enrichment", stats['pending_enrichment'])
        
        st.markdown("---")
        
        # Recent records
        st.subheader("Recent Records")
        display_cols = ['id', 'input_url', 'clean_url', 'profile_id', 'http_status', 
                       'page_title', 'enrichment_status', 'fetched_at']
        available_cols = [col for col in display_cols if col in df.columns]
        st.dataframe(df[available_cols].head(10), use_container_width=True)
    
    # Tab 2: Data Explorer
    with tab2:
        st.header("Data Explorer")
        
        # Filters
        col1, col2 = st.columns(2)
        
        with col1:
            # Status filter
            if 'enrichment_status' in df.columns:
                status_options = ['All'] + list(df['enrichment_status'].dropna().unique())
                status_filter = st.selectbox("Enrichment Status", status_options)
            else:
                status_filter = 'All'
        
        with col2:
            # Error filter
            error_filter = st.selectbox("Error Status", ['All', 'Success Only', 'Errors Only'])
        
        # Apply filters
        filtered_df = df.copy()
        
        if status_filter != 'All':
            filtered_df = filtered_df[filtered_df['enrichment_status'] == status_filter]
        
        if error_filter == 'Success Only':
            filtered_df = filtered_df[filtered_df['error'].isna()]
        elif error_filter == 'Errors Only':
            filtered_df = filtered_df[filtered_df['error'].notna()]

        # Column selection
        all_columns = list(df.columns)
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

    # Tab 3: Analytics
    with tab3:
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

    # Tab 4: Export
    with tab4:
        st.header("Export Data")

        st.markdown("Export filtered data to various formats")

        # Use filtered data from tab2 if available, otherwise use full dataset
        export_df = filtered_df if 'filtered_df' in locals() else df

        col1, col2, col3 = st.columns(3)

        with col1:
            # CSV Export
            csv = export_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"fb_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

        with col2:
            # JSON Export
            json_str = export_df.to_json(orient='records', indent=2)
            st.download_button(
                label="📥 Download JSON",
                data=json_str,
                file_name=f"fb_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )

        with col3:
            # Excel Export (if openpyxl is available)
            try:
                from io import BytesIO
                buffer = BytesIO()
                export_df.to_excel(buffer, index=False, engine='openpyxl')
                st.download_button(
                    label="📥 Download Excel",
                    data=buffer.getvalue(),
                    file_name=f"fb_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except ImportError:
                st.info("Install openpyxl for Excel export: pip install openpyxl")

        st.markdown("---")

        # Export statistics
        st.subheader("Export Preview")
        st.write(f"**Records to export:** {len(export_df)}")
        st.write(f"**Columns:** {len(export_df.columns)}")
        st.dataframe(export_df.head(5), use_container_width=True)


if __name__ == '__main__':
    main()


