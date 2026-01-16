# Export Functionality Integration Guide

## Overview

This package provides modern export functionality for the Facebook Marketplace profile viewer, based on the receipts-ocr pattern (https://swipswaps.github.io/receipts-ocr/).

---

## Files Provided

1. **export_functionality.py** - Core export functions (CSV, Excel, SQL, JSON, Text)
2. **profile_viewer_enhanced.py** - Complete Streamlit app with card-based UX
3. **test_export.py** - Test script to verify export functions work

---

## Features

### Multi-Row Selection
- ✅ Checkbox selection for individual profiles
- ✅ Select All / Clear All buttons
- ✅ Visual feedback for selected items (highlighted cards)
- ✅ Selection persists across page interactions

### Export Formats
- **CSV** - Comma-separated values for Excel/Google Sheets
- **Excel (XLSX)** - Native Excel format with auto-sized columns
- **Text** - Human-readable formatted output
- **SQL** - INSERT statements for database import
- **JSON** - Structured data for APIs/programming

### Search & Filter
- 🔍 Search by name, location, or Facebook ID
- 📦 Filter by profiles with active listings
- 💬 Filter by profiles with response rate data

### Modern UX
- 📱 Card-based layout (mobile-friendly)
- 🎨 Color-coded selection (blue highlight for selected)
- 📊 Statistics dashboard (total, selected, active listings, etc.)
- 🔄 Sticky export panel (always visible)
- 💡 Help section with usage instructions

---

## Installation

### 1. Install Dependencies

```bash
pip install streamlit pandas openpyxl --break-system-packages
```

### 2. Copy Files

```bash
# Copy to your project directory
cp export_functionality.py /path/to/your/project/
cp profile_viewer_enhanced.py /path/to/your/project/
```

### 3. Test Export Functions

```bash
python3 test_export.py
```

---

## Usage

### Running the Enhanced Viewer

```bash
streamlit run profile_viewer_enhanced.py
```

The app will:
1. Load profiles from `test_profiles.db`
2. Display them in card format
3. Allow multi-select with checkboxes
4. Provide export buttons in sidebar

### Integrating Into Existing App

If you already have a Streamlit app, you can integrate the export functionality:

```python
from export_functionality import render_export_section, render_selectable_table

# In your existing Streamlit app
df = load_your_data()  # Your existing data loading

# Option 1: Use the selectable table component
selected_rows = render_selectable_table(df, key_prefix="main")
render_export_section(df, selected_rows, key_prefix="main")

# Option 2: Use your own selection mechanism
selected_rows = your_selection_logic()
render_export_section(df, selected_rows, key_prefix="main")
```

---

## API Reference

### Export Functions

#### `create_csv_download(df: pd.DataFrame) -> str`
Creates CSV string from DataFrame.

```python
csv_data = create_csv_download(df)
# Use with st.download_button()
```

#### `create_excel_download(df: pd.DataFrame) -> bytes`
Creates Excel file with auto-sized columns.

```python
excel_bytes = create_excel_download(df)
# Returns bytes ready for download
```

#### `create_txt_download(df: pd.DataFrame) -> str`
Creates formatted text with headers and record separators.

```python
txt_data = create_txt_download(df)
# Human-readable format
```

#### `create_sql_download(df: pd.DataFrame, table_name: str = "profiles") -> str`
Creates SQL INSERT statements with CREATE TABLE.

```python
sql_data = create_sql_download(df, table_name="my_profiles")
# Ready to execute in SQLite/PostgreSQL/MySQL
```

#### `create_json_download(df: pd.DataFrame) -> str`
Creates JSON array of records.

```python
json_data = create_json_download(df)
# Standard JSON format
```

### UI Components

#### `render_export_section(df, selected_rows, key_prefix)`
Renders export buttons for selected rows.

**Parameters:**
- `df`: Full DataFrame
- `selected_rows`: List of selected row indices
- `key_prefix`: Unique prefix for Streamlit widget keys

#### `render_selectable_table(df, key_prefix)`
Renders table with selection checkboxes.

**Returns:** List of selected row indices

---

## Examples

### Example 1: Basic Integration

```python
import streamlit as st
import pandas as pd
from export_functionality import render_export_section, render_selectable_table

st.title("My Data Viewer")

# Load your data
df = pd.read_csv("data.csv")

# Render selectable table
selected_rows = render_selectable_table(df, key_prefix="data")

# Render export section
render_export_section(df, selected_rows, key_prefix="data")
```

### Example 2: Custom Selection

```python
import streamlit as st
from export_functionality import render_export_section

# Your custom selection UI
selected_indices = []
for idx, row in df.iterrows():
    if st.checkbox(f"Select {row['name']}", key=f"sel_{idx}"):
        selected_indices.append(idx)

# Use export functionality with your selections
render_export_section(df, selected_indices, key_prefix="custom")
```

### Example 3: Export Only Specific Columns

```python
from export_functionality import create_csv_download

# Select only specific columns for export
export_df = df[['fb_id', 'fb_name', 'fb_location_name']].copy()

# Create download
csv_data = create_csv_download(export_df)

st.download_button(
    label="Download Selected Columns",
    data=csv_data,
    file_name="export.csv",
    mime="text/csv"
)
```

---

## Customization

### Changing Export Formats

To add a new export format:

1. Create export function in `export_functionality.py`:
```python
def create_xml_download(df: pd.DataFrame) -> str:
    """Create XML from DataFrame"""
    # Your XML generation logic
    return xml_string
```

2. Add button in `render_export_section()`:
```python
with col6:
    xml_data = create_xml_download(export_df)
    st.download_button(
        label="📋 XML",
        data=xml_data,
        file_name=f"profiles_{timestamp}.xml",
        mime="application/xml",
        key=f"{key_prefix}_xml"
    )
```

### Styling the Cards

Modify the `render_profile_card()` function in `profile_viewer_enhanced.py`:

```python
# Change selected card color
card_style = """
    background-color: #your_color;  # Change this
    border: 2px solid #your_border;  # And this
    ...
"""
```

### Adding More Statistics

In the statistics bar:

```python
col5.metric("Your Metric", calculate_your_metric(df))
```

---

## Testing

### Manual Testing Checklist

- [ ] Select individual profiles (checkboxes work)
- [ ] Select All button selects all profiles
- [ ] Clear All button deselects all profiles
- [ ] Selected profiles show blue highlight
- [ ] Export panel only shows when profiles selected
- [ ] CSV export downloads and opens in Excel
- [ ] Excel export downloads and opens in Excel
- [ ] Text export is readable
- [ ] SQL export has valid SQL syntax
- [ ] JSON export is valid JSON
- [ ] Search filters profiles correctly
- [ ] "Has Active Listings" filter works
- [ ] "Has Response Rate" filter works
- [ ] Statistics update correctly

### Automated Testing

```bash
# Run test script
python3 test_export.py

# Should output:
# ✅ CSV export works
# ✅ Excel export works
# ✅ Text export works
# ✅ SQL export works
# ✅ JSON export works
```

---

## Troubleshooting

### Issue: No profiles shown
**Solution:** Check that database has enriched profiles:
```bash
sqlite3 test_profiles.db "SELECT COUNT(*) FROM profiles WHERE enrichment_status='enriched';"
```

### Issue: Export button disabled
**Solution:** Make sure at least one profile is selected

### Issue: Excel export fails
**Solution:** Install openpyxl:
```bash
pip install openpyxl --break-system-packages
```

### Issue: Selections don't persist
**Solution:** Make sure each widget has a unique `key` parameter

---

## Performance Notes

- The app loads all profiles into memory
- For databases with 1000+ profiles, consider:
  - Pagination (load 50 profiles at a time)
  - Server-side search (query database instead of filtering DataFrame)
  - Lazy loading (load details only when card expanded)

Example pagination:

```python
page = st.number_input("Page", min_value=1, max_value=total_pages)
start_idx = (page - 1) * page_size
end_idx = start_idx + page_size
page_df = df.iloc[start_idx:end_idx]
```

---

## Comparison to receipts-ocr

This implementation follows the same UX patterns as receipts-ocr:

| Feature | receipts-ocr | This Implementation |
|---------|--------------|---------------------|
| Card-based layout | ✅ | ✅ |
| Multi-select | ✅ | ✅ |
| Export formats | ✅ (TXT, CSV) | ✅ (TXT, CSV, XLSX, SQL, JSON) |
| Search/filter | ✅ | ✅ |
| Modern styling | ✅ | ✅ |
| Mobile responsive | ✅ | ✅ (via Streamlit) |

**Improvements over receipts-ocr:**
- More export formats (added Excel, SQL, JSON)
- Persistent selection with session state
- Statistics dashboard
- Help section with instructions
- Expandable detail sections
- Filter by data availability

---

## Next Steps

1. ✅ Install dependencies
2. ✅ Copy files to your project
3. ✅ Run test script
4. ✅ Start Streamlit app
5. ✅ Select profiles and test exports
6. 📝 Customize styling/features as needed
7. 🚀 Deploy to production

---

## Support

For issues or questions:
1. Check this guide's troubleshooting section
2. Review the example code
3. Test with the provided test script
4. Check Streamlit logs for errors

---

## License

Based on the receipts-ocr project pattern. Adapt freely for your use case.
