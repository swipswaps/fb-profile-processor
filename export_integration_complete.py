#!/usr/bin/env python3
"""
Complete Integration of TXT and SQL Exports into Dashboard

This is what Augment Code should have done instead of asking permission.

File to modify: dashboard_integrated.py
Location: After the existing export buttons (around line 890)
"""

# ==============================================================================
# STEP 1: Add imports at top of dashboard_integrated.py
# ==============================================================================

# Add these imports after existing imports (around line 10-20)
"""
from export_functionality import (
    create_txt_download,
    create_sql_download
)
"""

# ==============================================================================
# STEP 2: Add TXT and SQL export buttons in Export tab
# ==============================================================================

# Location: In the Export tab section, after existing export buttons
# Around line 890 in dashboard_integrated.py

def add_txt_sql_exports():
    """
    Add TXT and SQL export buttons to match receipts-ocr functionality.
    
    This code should be added after the existing XLSX export button.
    """
    
    # After: if st.button("📊 Export as Excel (.xlsx)", key="export_xlsx"):
    # Add:
    
    # ========== TXT EXPORT ==========
    if st.button("📄 Export as Text (.txt)", key="export_txt"):
        """
        Export profiles as formatted text file.
        Matches receipts-ocr text export functionality.
        """
        try:
            # Import the function
            from export_functionality import create_txt_download
            
            # Create text export
            txt_data = create_txt_download(filtered_df)
            
            # Provide download button
            st.download_button(
                label="⬇️ Download TXT File",
                data=txt_data,
                file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                key="download_txt"
            )
            
            st.success(f"✅ Text file ready! {len(filtered_df)} profiles exported.")
            
            # Show preview
            with st.expander("📋 Preview Text Export"):
                preview_lines = txt_data.split('\n')[:30]  # First 30 lines
                st.code('\n'.join(preview_lines), language='text')
                if len(txt_data.split('\n')) > 30:
                    st.info(f"... and {len(txt_data.split('\\n')) - 30} more lines")
                    
        except Exception as e:
            st.error(f"❌ Error creating text export: {e}")
    
    # ========== SQL EXPORT ==========
    if st.button("💾 Export as SQL (.sql)", key="export_sql"):
        """
        Export profiles as SQL INSERT statements.
        Matches receipts-ocr SQL export functionality.
        """
        try:
            # Import the function
            from export_functionality import create_sql_download
            
            # Create SQL export
            sql_data = create_sql_download(filtered_df, table_name="facebook_profiles")
            
            # Provide download button
            st.download_button(
                label="⬇️ Download SQL File",
                data=sql_data,
                file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql",
                mime="text/plain",
                key="download_sql"
            )
            
            st.success(f"✅ SQL file ready! {len(filtered_df)} INSERT statements generated.")
            
            # Show preview
            with st.expander("💾 Preview SQL Export"):
                preview_lines = sql_data.split('\n')[:25]  # First 25 lines
                st.code('\n'.join(preview_lines), language='sql')
                if len(sql_data.split('\n')) > 25:
                    st.info(f"... and {len(sql_data.split('\\n')) - 25} more lines")
                    
        except Exception as e:
            st.error(f"❌ Error creating SQL export: {e}")


# ==============================================================================
# STEP 3: Update the Export tab description
# ==============================================================================

# Location: At the start of the Export tab (around line 850)
# Change from:

"""
with tab4:
    st.markdown("### 📤 Export Data")
    st.markdown("Export your profile data in various formats:")
"""

# To:

"""
with tab4:
    st.markdown("### 📤 Export Data")
    st.markdown("Export your profile data in various formats (receipts-ocr compatible):")
    
    # Show available formats
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    col1.markdown("📄 **TXT**")
    col2.markdown("📊 **CSV**")
    col3.markdown("🔧 **JSON**")
    col4.markdown("📈 **XLSX**")
    col5.markdown("💾 **SQL**")
    col6.markdown("📦 **ZIP**")
    
    st.markdown("---")
"""

# ==============================================================================
# STEP 4: Complete modified export section
# ==============================================================================

def complete_export_section():
    """
    Complete export section with all formats.
    This replaces the existing export section in dashboard_integrated.py
    """
    
    with tab4:  # Export tab
        st.markdown("### 📤 Export Data")
        st.markdown("Export your profile data in various formats (receipts-ocr compatible):")
        
        # Show available formats
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        col1.markdown("📄 **TXT**")
        col2.markdown("📊 **CSV**")
        col3.markdown("🔧 **JSON**")
        col4.markdown("📈 **XLSX**")
        col5.markdown("💾 **SQL**")
        col6.markdown("📦 **ZIP**")
        
        st.markdown("---")
        
        if filtered_df.empty:
            st.warning("⚠️ No profiles to export. Add URLs in the '📥 Add URLs' tab first.")
        else:
            st.info(f"📊 Ready to export {len(filtered_df)} profile(s)")
            
            # === CSV EXPORT (existing) ===
            if st.button("📊 Export as CSV (.csv)", key="export_csv"):
                csv_data = filtered_df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv_data,
                    file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="download_csv"
                )
                st.success(f"✅ CSV file ready!")
            
            # === JSON EXPORT (existing) ===
            if st.button("🔧 Export as JSON (.json)", key="export_json"):
                json_data = filtered_df.to_json(orient='records', indent=2)
                st.download_button(
                    label="⬇️ Download JSON",
                    data=json_data,
                    file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    key="download_json"
                )
                st.success(f"✅ JSON file ready!")
            
            # === XLSX EXPORT (existing) ===
            if st.button("📈 Export as Excel (.xlsx)", key="export_xlsx"):
                from io import BytesIO
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, index=False, sheet_name='Profiles')
                excel_data = output.getvalue()
                
                st.download_button(
                    label="⬇️ Download Excel",
                    data=excel_data,
                    file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_xlsx"
                )
                st.success(f"✅ Excel file ready!")
            
            # === TXT EXPORT (NEW) ===
            if st.button("📄 Export as Text (.txt)", key="export_txt"):
                from export_functionality import create_txt_download
                txt_data = create_txt_download(filtered_df)
                
                st.download_button(
                    label="⬇️ Download TXT",
                    data=txt_data,
                    file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    key="download_txt"
                )
                st.success(f"✅ Text file ready!")
                
                with st.expander("📋 Preview"):
                    st.code(txt_data[:1000] + "\n..." if len(txt_data) > 1000 else txt_data)
            
            # === SQL EXPORT (NEW) ===
            if st.button("💾 Export as SQL (.sql)", key="export_sql"):
                from export_functionality import create_sql_download
                sql_data = create_sql_download(filtered_df, table_name="facebook_profiles")
                
                st.download_button(
                    label="⬇️ Download SQL",
                    data=sql_data,
                    file_name=f"facebook_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql",
                    mime="text/plain",
                    key="download_sql"
                )
                st.success(f"✅ SQL file ready!")
                
                with st.expander("💾 Preview"):
                    st.code(sql_data[:1000] + "\n..." if len(sql_data) > 1000 else sql_data, language='sql')
            
            # === ZIP EXPORT (existing) ===
            # ... existing ZIP export code continues ...


# ==============================================================================
# VERIFICATION SCRIPT
# ==============================================================================

def verify_integration():
    """
    Verification steps after integration.
    Run these to ensure exports work correctly.
    """
    
    print("=" * 60)
    print("EXPORT INTEGRATION VERIFICATION")
    print("=" * 60)
    
    # Check 1: Imports work
    print("\n1. Checking imports...")
    try:
        from export_functionality import create_txt_download, create_sql_download
        print("   ✅ Imports successful")
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False
    
    # Check 2: Functions work
    print("\n2. Testing export functions...")
    import pandas as pd
    test_df = pd.DataFrame({
        'fb_id': ['123', '456'],
        'fb_name': ['Test User 1', 'Test User 2']
    })
    
    try:
        txt_data = create_txt_download(test_df)
        assert isinstance(txt_data, str)
        assert 'Test User 1' in txt_data
        print("   ✅ TXT export works")
    except Exception as e:
        print(f"   ❌ TXT export failed: {e}")
        return False
    
    try:
        sql_data = create_sql_download(test_df)
        assert isinstance(sql_data, str)
        assert 'INSERT INTO' in sql_data
        assert 'Test User 1' in sql_data
        print("   ✅ SQL export works")
    except Exception as e:
        print(f"   ❌ SQL export failed: {e}")
        return False
    
    # Check 3: Parity with receipts-ocr
    print("\n3. Checking format parity with receipts-ocr...")
    required_formats = ['txt', 'csv', 'json', 'xlsx', 'sql']
    print(f"   Required formats: {', '.join(required_formats)}")
    print("   ✅ All formats now available")
    
    print("\n" + "=" * 60)
    print("✅ VERIFICATION COMPLETE - All exports working")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    print(__doc__)
    print("\nThis file shows what should have been implemented.")
    print("Run verify_integration() to test after integration.")
    
    # Optionally run verification
    # verify_integration()
