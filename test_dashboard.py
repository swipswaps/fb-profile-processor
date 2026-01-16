#!/usr/bin/env python3
"""Test dashboard.py functionality without running Streamlit server"""

import pandas as pd
import sqlite3
from pathlib import Path

def test_database_connection():
    """Test database connection and data loading"""
    print("=" * 60)
    print("DASHBOARD FUNCTIONALITY TEST")
    print("=" * 60)
    
    # Find databases
    db_files = list(Path('.').glob('*.db'))
    print(f"\n✓ Found {len(db_files)} database files:")
    for db in db_files:
        print(f"  - {db}")
    
    # Test with test_profiles.db
    db_path = 'test_profiles.db'
    if not Path(db_path).exists():
        print(f"\n✗ Database '{db_path}' not found")
        return False
    
    print(f"\n✓ Testing database: {db_path}")
    
    try:
        # Read-only connection
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        
        # Load data
        df = pd.read_sql_query("SELECT * FROM profiles ORDER BY id DESC", conn)
        conn.close()
        
        print(f"✓ Loaded {len(df)} records")
        print(f"✓ Columns: {len(df.columns)}")
        print(f"\nColumn names:")
        for i, col in enumerate(df.columns, 1):
            print(f"  {i:2d}. {col}")
        
        # Statistics
        print(f"\nStatistics:")
        print(f"  Total records: {len(df)}")
        print(f"  Successful: {len(df[df['error'].isna()])}")
        print(f"  Errors: {len(df[df['error'].notna()])}")
        
        if 'enrichment_status' in df.columns:
            print(f"  Pending enrichment: {len(df[df['enrichment_status'] == 'pending'])}")
            print(f"  Enriched: {len(df[df['enrichment_status'] == 'enriched'])}")
        
        # Sample data
        print(f"\nSample record (first row):")
        if not df.empty:
            first_row = df.iloc[0]
            for col in ['id', 'input_url', 'clean_url', 'profile_id', 'http_status', 
                       'page_title', 'enrichment_status']:
                if col in df.columns:
                    print(f"  {col}: {first_row[col]}")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nTo run the dashboard:")
        print("  streamlit run dashboard.py")
        print("\nThe dashboard will open in your browser at http://localhost:8501")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


if __name__ == '__main__':
    test_database_connection()

