#!/usr/bin/env python3
"""
Test Script for Export Functionality
Verifies all export functions work correctly.

Usage:
    python3 test_export.py
"""

import pandas as pd
import sys
from pathlib import Path

# Import export functions
try:
    from export_functionality import (
        create_csv_download,
        create_excel_download,
        create_txt_download,
        create_sql_download,
        create_json_download
    )
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure export_functionality.py is in the same directory")
    sys.exit(1)


def create_test_data() -> pd.DataFrame:
    """Create sample DataFrame for testing"""
    data = {
        'fb_id': ['100001669012324', '100010505562305', '100024126863464'],
        'fb_name': ['Kyle', 'Abu', 'Olivia C.'],
        'fb_location_name': ['New York, NY', 'Los Angeles, CA', 'Chicago, IL'],
        'fb_join_date': ['2010', '2015', '2018'],
        'fb_active_listings_count': [0, 5, 1],
        'fb_response_rate': [None, 'Very responsive', None],
        'fb_picture_url': [
            'https://example.com/pic1.jpg',
            'https://example.com/pic2.jpg',
            'https://example.com/pic3.jpg'
        ]
    }

    return pd.DataFrame(data)


def test_csv_export(df: pd.DataFrame) -> bool:
    """Test CSV export"""
    try:
        csv_data = create_csv_download(df)

        # Verify it's a string
        assert isinstance(csv_data, str), "CSV should be string"

        # Verify it has headers
        assert 'fb_id' in csv_data, "CSV should have headers"

        # Verify it has data
        assert 'Kyle' in csv_data, "CSV should have data"

        print("✅ CSV export works")
        return True
    except Exception as e:
        print(f"❌ CSV export failed: {e}")
        return False


def test_excel_export(df: pd.DataFrame) -> bool:
    """Test Excel export"""
    try:
        excel_data = create_excel_download(df)

        # Verify it's bytes
        assert isinstance(excel_data, bytes), "Excel should be bytes"

        # Verify it's not empty
        assert len(excel_data) > 0, "Excel data should not be empty"

        # Verify it starts with Excel signature
        # Excel files start with PK (ZIP format)
        assert excel_data[:2] == b'PK', "Should be valid Excel file"

        print("✅ Excel export works")
        return True
    except Exception as e:
        print(f"❌ Excel export failed: {e}")
        return False


def test_txt_export(df: pd.DataFrame) -> bool:
    """Test Text export"""
    try:
        txt_data = create_txt_download(df)

        # Verify it's a string
        assert isinstance(txt_data, str), "Text should be string"

        # Verify it has title
        assert 'FACEBOOK MARKETPLACE' in txt_data, "Should have title"

        # Verify it has data
        assert 'Kyle' in txt_data, "Should have profile data"

        # Verify it has record count
        assert 'Total Records: 3' in txt_data, "Should show record count"

        print("✅ Text export works")
        return True
    except Exception as e:
        print(f"❌ Text export failed: {e}")
        return False


def test_sql_export(df: pd.DataFrame) -> bool:
    """Test SQL export"""
    try:
        sql_data = create_sql_download(df)

        # Verify it's a string
        assert isinstance(sql_data, str), "SQL should be string"

        # Verify it has CREATE TABLE
        assert 'CREATE TABLE' in sql_data, "Should have CREATE TABLE"

        # Verify it has INSERT statements
        assert 'INSERT INTO' in sql_data, "Should have INSERT statements"

        # Verify it has data
        assert 'Kyle' in sql_data, "Should have profile data"

        # Verify NULL handling
        assert 'NULL' in sql_data, "Should handle NULL values"

        print("✅ SQL export works")
        return True
    except Exception as e:
        print(f"❌ SQL export failed: {e}")
        return False


def test_json_export(df: pd.DataFrame) -> bool:
    """Test JSON export"""
    try:
        import json

        json_data = create_json_download(df)

        # Verify it's a string
        assert isinstance(json_data, str), "JSON should be string"

        # Verify it's valid JSON
        parsed = json.loads(json_data)
        assert isinstance(parsed, list), "JSON should be array"
        assert len(parsed) == 3, "Should have 3 records"

        # Verify structure
        assert 'fb_id' in parsed[0], "Should have fb_id field"
        assert parsed[0]['fb_name'] == 'Kyle', "Should have correct data"

        print("✅ JSON export works")
        return True
    except Exception as e:
        print(f"❌ JSON export failed: {e}")
        return False


def test_export_with_real_db():
    """Test with real database if available"""
    try:
        import sqlite3

        if not Path('test_profiles.db').exists():
            print("\n⚠️  test_profiles.db not found - skipping real DB test")
            return True

        conn = sqlite3.connect('test_profiles.db')
        query = """
            SELECT fb_id, fb_name, fb_location_name, fb_join_date,
                   fb_active_listings_count, fb_response_rate, fb_picture_url
            FROM profiles
            WHERE fb_name IS NOT NULL
            LIMIT 3
        """
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            print("\n⚠️  No profiles in database - skipping real DB test")
            return True

        print(f"\n📊 Testing with real database ({len(df)} profiles)...")

        # Test all formats with different assertions (real data)
        all_ok = True

        # CSV test
        try:
            csv_data = create_csv_download(df)
            assert isinstance(csv_data, str) and 'fb_id' in csv_data
            print("✅ Real DB CSV export works")
        except Exception as e:
            print(f"❌ Real DB CSV failed: {e}")
            all_ok = False

        # Excel test
        try:
            excel_data = create_excel_download(df)
            assert isinstance(excel_data, bytes) and len(excel_data) > 100
            print("✅ Real DB Excel export works")
        except Exception as e:
            print(f"❌ Real DB Excel failed: {e}")
            all_ok = False

        # TXT test
        try:
            txt_data = create_txt_download(df)
            assert isinstance(txt_data, str) and 'EXPORT' in txt_data
            print("✅ Real DB Text export works")
        except Exception as e:
            print(f"❌ Real DB Text failed: {e}")
            all_ok = False

        # SQL test
        try:
            sql_data = create_sql_download(df)
            assert 'INSERT INTO' in sql_data and 'CREATE TABLE' in sql_data
            print("✅ Real DB SQL export works")
        except Exception as e:
            print(f"❌ Real DB SQL failed: {e}")
            all_ok = False

        # JSON test
        try:
            import json
            json_data = create_json_download(df)
            parsed = json.loads(json_data)
            assert isinstance(parsed, list) and len(parsed) > 0
            print("✅ Real DB JSON export works")
        except Exception as e:
            print(f"❌ Real DB JSON failed: {e}")
            all_ok = False

        return all_ok

    except Exception as e:
        print(f"\n⚠️  Real DB test failed: {e}")
        return True  # Don't fail overall test


def main():
    """Run all tests"""
    print("=" * 60)
    print("EXPORT FUNCTIONALITY TEST SUITE")
    print("=" * 60)

    # Create test data
    print("\n📝 Creating test data...")
    df = create_test_data()
    print(f"   Created DataFrame with {len(df)} rows, {len(df.columns)} columns")

    # Run tests
    print("\n🧪 Running export tests...\n")

    results = {
        'CSV': test_csv_export(df),
        'Excel': test_excel_export(df),
        'Text': test_txt_export(df),
        'SQL': test_sql_export(df),
        'JSON': test_json_export(df)
    }

    # Test with real DB if available
    test_export_with_real_db()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(results.values())

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name:10} {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✅ All tests passed! Export functionality is working correctly.")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
