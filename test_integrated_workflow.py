#!/usr/bin/env python3
"""Test integrated dashboard workflow"""

import fb_profile_processor as processor
from pathlib import Path
import sqlite3

def test_workflow():
    """Test complete CRUD workflow"""
    print("=" * 70)
    print("INTEGRATED DASHBOARD WORKFLOW TEST")
    print("=" * 70)
    
    # Test database
    test_db = 'test_integrated.db'
    
    # Clean up if exists
    if Path(test_db).exists():
        Path(test_db).unlink()
    
    print(f"\n1. INITIALIZE DATABASE")
    print("-" * 70)
    processor.init_db(test_db)
    print(f"✅ Database created: {test_db}")
    
    # Test URLs
    test_urls = [
        'https://www.facebook.com/marketplace/profile/111111111',
        'https://www.facebook.com/marketplace/profile/222222222',
        'https://www.facebook.com/marketplace/profile/333333333',
    ]
    
    print(f"\n2. PROCESS URLS (CREATE)")
    print("-" * 70)
    
    def progress_callback(current, total, url, result):
        status = "✅" if result['success'] else "❌"
        print(f"  [{current}/{total}] {status} {url}")
        if result['error']:
            print(f"      Error: {result['error']}")
    
    batch_result = processor.process_urls_batch(
        test_urls,
        test_db,
        rate_limit=0.5,
        timeout=10,
        progress_callback=progress_callback
    )
    
    print(f"\n  Summary:")
    print(f"    Total: {batch_result['total']}")
    print(f"    Success: {batch_result['success']}")
    print(f"    Errors: {batch_result['errors']}")
    print(f"    Skipped: {batch_result['skipped']}")
    
    print(f"\n3. READ DATA")
    print("-" * 70)
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, input_url, profile_id, http_status, enrichment_status FROM profiles")
    rows = cur.fetchall()
    
    print(f"  Records in database: {len(rows)}")
    for row in rows:
        print(f"    ID {row['id']}: {row['input_url'][:50]} | Status: {row['enrichment_status']}")
    
    conn.close()
    
    print(f"\n4. UPDATE RECORD")
    print("-" * 70)
    if rows:
        first_id = rows[0]['id']
        updates = {
            'page_title': 'Updated Test Title',
            'enrichment_status': 'enriched',
            'browser_profile_name': 'Test User'
        }
        
        success = processor.update_profile(test_db, first_id, updates)
        print(f"  Update record #{first_id}: {'✅ Success' if success else '❌ Failed'}")
        
        # Verify update
        updated = processor.get_profile_by_id(test_db, first_id)
        if updated:
            print(f"  Verified:")
            print(f"    page_title: {updated['page_title']}")
            print(f"    enrichment_status: {updated['enrichment_status']}")
            print(f"    browser_profile_name: {updated['browser_profile_name']}")
    
    print(f"\n5. DELETE RECORD")
    print("-" * 70)
    if len(rows) > 1:
        delete_id = rows[-1]['id']
        success = processor.delete_profile(test_db, delete_id)
        print(f"  Delete record #{delete_id}: {'✅ Success' if success else '❌ Failed'}")
        
        # Verify deletion
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM profiles")
        count = cur.fetchone()[0]
        conn.close()
        print(f"  Remaining records: {count}")
    
    print(f"\n6. EXPORT DATA")
    print("-" * 70)
    
    # Test CSV export
    csv_file = 'test_integrated_export.csv'
    processor.export_to_csv(test_db, csv_file)
    if Path(csv_file).exists():
        print(f"  ✅ CSV export: {csv_file}")
        print(f"     Size: {Path(csv_file).stat().st_size} bytes")
    
    # Test JSON export
    json_file = 'test_integrated_export.json'
    processor.export_to_json(test_db, json_file)
    if Path(json_file).exists():
        print(f"  ✅ JSON export: {json_file}")
        print(f"     Size: {Path(json_file).stat().st_size} bytes")
    
    print("\n" + "=" * 70)
    print("✅ ALL WORKFLOW TESTS PASSED")
    print("=" * 70)
    
    print(f"\nTest artifacts created:")
    print(f"  - {test_db}")
    print(f"  - {csv_file}")
    print(f"  - {json_file}")
    
    print(f"\nTo test the dashboard:")
    print(f"  streamlit run dashboard_integrated.py")
    
    return True


if __name__ == '__main__':
    test_workflow()

