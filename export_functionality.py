"""
Export Functionality for Profile Viewer

Features:
- Multi-row selection with checkboxes
- Export selected rows to: TXT, CSV, XLS, SQL
- Based on receipts-ocr pattern: https://swipswaps.github.io/receipts-ocr/

Usage:
    Add this to your Streamlit profile viewer app
"""

import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO, StringIO
from typing import List, Dict
import json


def create_excel_download(df: pd.DataFrame, filename: str = "export.xlsx") -> bytes:
    """
    Create downloadable Excel file from DataFrame.
    
    Args:
        df: DataFrame to export
        filename: Output filename
        
    Returns:
        Bytes of Excel file
    """
    output = BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Profiles')

        # Auto-adjust column widths
        worksheet = writer.sheets['Profiles']
        for idx, col in enumerate(df.columns):
            max_length = max(
                df[col].astype(str).apply(len).max(),
                len(col)
            )
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

    return output.getvalue()


def create_csv_download(df: pd.DataFrame) -> str:
    """
    Create CSV string from DataFrame.
    
    Args:
        df: DataFrame to export
        
    Returns:
        CSV string
    """
    return df.to_csv(index=False)


def create_txt_download(df: pd.DataFrame) -> str:
    """
    Create formatted text from DataFrame.
    
    Args:
        df: DataFrame to export
        
    Returns:
        Formatted text string
    """
    output = StringIO()

    # Header
    output.write("=" * 80 + "\n")
    output.write("FACEBOOK MARKETPLACE PROFILES EXPORT\n")
    output.write("=" * 80 + "\n\n")

    # Records
    for idx, row in df.iterrows():
        output.write(f"--- Profile {idx + 1} ---\n")
        for col in df.columns:
            value = row[col]
            if pd.notna(value):
                output.write(f"{col:30} : {value}\n")
        output.write("\n")

    output.write("=" * 80 + "\n")
    output.write(f"Total Records: {len(df)}\n")
    output.write("=" * 80 + "\n")

    return output.getvalue()


def create_sql_download(df: pd.DataFrame, table_name: str = "profiles") -> str:
    """
    Create SQL INSERT statements from DataFrame.
    
    Args:
        df: DataFrame to export
        table_name: Table name for SQL statements
        
    Returns:
        SQL string
    """
    output = StringIO()

    # Header comment
    output.write(f"-- Facebook Marketplace Profiles Export\n")
    output.write(f"-- Generated: {pd.Timestamp.now()}\n")
    output.write(f"-- Records: {len(df)}\n\n")

    # Create table statement
    output.write(f"CREATE TABLE IF NOT EXISTS {table_name} (\n")

    column_defs = []
    for col, dtype in df.dtypes.items():
        if dtype == 'int64':
            sql_type = "INTEGER"
        elif dtype == 'float64':
            sql_type = "REAL"
        else:
            sql_type = "TEXT"
        column_defs.append(f"    {col} {sql_type}")

    output.write(",\n".join(column_defs))
    output.write("\n);\n\n")

    # Insert statements
    for idx, row in df.iterrows():
        columns = ", ".join(df.columns)
        values = []

        for val in row:
            if pd.isna(val):
                values.append("NULL")
            elif isinstance(val, (int, float)):
                values.append(str(val))
            else:
                # Escape single quotes
                escaped = str(val).replace("'", "''")
                values.append(f"'{escaped}'")

        values_str = ", ".join(values)
        output.write(f"INSERT INTO {table_name} ({columns}) VALUES ({values_str});\n")

    return output.getvalue()


def create_json_download(df: pd.DataFrame) -> str:
    """
    Create JSON from DataFrame.
    
    Args:
        df: DataFrame to export
        
    Returns:
        JSON string
    """
    return df.to_json(orient='records', indent=2)


def render_export_section(
    df: pd.DataFrame,
    selected_rows: List[int],
    key_prefix: str = "export"
):
    """
    Render export section with download buttons.
    
    Args:
        df: DataFrame with all data
        selected_rows: List of selected row indices
        key_prefix: Prefix for Streamlit widget keys
    """
    if not selected_rows:
        st.info("Select one or more rows to enable export")
        return

    # Filter to selected rows
    export_df = df.iloc[selected_rows].reset_index(drop=True)

    st.markdown(f"### Export {len(selected_rows)} Selected Profile(s)")

    # Create columns for export buttons
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        # CSV export
        csv_data = create_csv_download(export_df)
        st.download_button(
            label="📄 CSV",
            data=csv_data,
            file_name=f"profiles_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            key=f"{key_prefix}_csv",
            help="Export as Comma-Separated Values"
        )

    with col2:
        # Excel export
        excel_data = create_excel_download(export_df)
        st.download_button(
            label="📊 Excel",
            data=excel_data,
            file_name=f"profiles_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_xlsx",
            help="Export as Excel spreadsheet"
        )

    with col3:
        # Text export
        txt_data = create_txt_download(export_df)
        st.download_button(
            label="📝 Text",
            data=txt_data,
            file_name=f"profiles_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            key=f"{key_prefix}_txt",
            help="Export as formatted text"
        )

    with col4:
        # SQL export
        sql_data = create_sql_download(export_df)
        st.download_button(
            label="💾 SQL",
            data=sql_data,
            file_name=f"profiles_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.sql",
            mime="text/plain",
            key=f"{key_prefix}_sql",
            help="Export as SQL INSERT statements"
        )

    with col5:
        # JSON export
        json_data = create_json_download(export_df)
        st.download_button(
            label="🔧 JSON",
            data=json_data,
            file_name=f"profiles_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key=f"{key_prefix}_json",
            help="Export as JSON"
        )

    # Preview section
    with st.expander("📋 Preview Export Data"):
        st.dataframe(export_df, use_container_width=True)


def render_selectable_table(
    df: pd.DataFrame,
    key_prefix: str = "table"
) -> List[int]:
    """
    Render table with row selection checkboxes.
    
    Args:
        df: DataFrame to display
        key_prefix: Prefix for Streamlit widget keys
        
    Returns:
        List of selected row indices
    """
    # Add select all checkbox
    select_all = st.checkbox(
        "Select All",
        key=f"{key_prefix}_select_all",
        help="Select/deselect all rows"
    )

    # Initialize session state for selections
    if f"{key_prefix}_selections" not in st.session_state:
        st.session_state[f"{key_prefix}_selections"] = set()

    # Handle select all
    if select_all:
        st.session_state[f"{key_prefix}_selections"] = set(range(len(df)))

    # Create table with checkboxes
    selected_rows = []

    # Header row
    cols = st.columns([0.5] + [2] * len(df.columns))
    cols[0].markdown("**Select**")
    for i, col_name in enumerate(df.columns, 1):
        cols[i].markdown(f"**{col_name}**")

    # Data rows
    for idx, row in df.iterrows():
        cols = st.columns([0.5] + [2] * len(df.columns))

        # Checkbox
        is_selected = cols[0].checkbox(
            "",
            value=idx in st.session_state[f"{key_prefix}_selections"],
            key=f"{key_prefix}_row_{idx}",
            label_visibility="collapsed"
        )

        if is_selected:
            st.session_state[f"{key_prefix}_selections"].add(idx)
            selected_rows.append(idx)
        elif idx in st.session_state[f"{key_prefix}_selections"]:
            st.session_state[f"{key_prefix}_selections"].remove(idx)

        # Data columns
        for i, (col_name, value) in enumerate(row.items(), 1):
            # Truncate long values
            display_value = str(value)[:50]
            if len(str(value)) > 50:
                display_value += "..."
            cols[i].text(display_value)

    return selected_rows


def get_profiles_from_db(db_path: str = "test_profiles.db") -> pd.DataFrame:
    """
    Load profiles from database.
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        DataFrame with profile data
    """
    conn = sqlite3.connect(db_path)

    query = """
        SELECT 
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
            enriched_at
        FROM profiles
        ORDER BY enriched_at DESC
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df


# Example usage in Streamlit app
def main():
    """Example Streamlit app with export functionality"""
    st.set_page_config(
        page_title="Profile Viewer with Export",
        page_icon="📊",
        layout="wide"
    )

    st.title("📊 Facebook Marketplace Profile Viewer")
    st.markdown("Select profiles to export in various formats")

    # Load data
    try:
        df = get_profiles_from_db()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    if df.empty:
        st.warning("No profiles found in database")
        return

    # Statistics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Profiles", len(df))
    col2.metric("With Active Listings", df['fb_active_listings_count'].notna().sum())
    col3.metric("With Response Rate", df['fb_response_rate'].notna().sum())

    st.markdown("---")

    # Display table with selection
    st.markdown("### Select Profiles to Export")
    selected_rows = render_selectable_table(df)

    st.markdown("---")

    # Export section
    render_export_section(df, selected_rows)

    # Summary
    if selected_rows:
        st.success(f"✅ {len(selected_rows)} profile(s) selected for export")


if __name__ == "__main__":
    main()
