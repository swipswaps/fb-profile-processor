#!/usr/bin/env python3
"""Test script for fb_profile_processor"""

import fb_profile_processor

# Test URL transformation
print("Testing URL transformation...")
result = fb_profile_processor.transform_url('https://www.facebook.com/marketplace/profile/123456789/?ref=test')
print(f"Result: {result}")
assert result['valid'] == True, "URL should be valid"
assert result['id'] == '123456789', "Profile ID should be extracted"
assert result['clean'] == 'https://www.facebook.com/123456789', "Clean URL should be correct"
print("✅ URL transformation test passed")

# Test invalid URL
print("\nTesting invalid URL...")
result2 = fb_profile_processor.transform_url('https://www.facebook.com/some-page')
print(f"Result: {result2}")
assert result2['valid'] == False, "Invalid URL should be marked as invalid"
print("✅ Invalid URL test passed")

# Test database initialization
print("\nTesting database initialization...")
import tempfile
import os
temp_db = tempfile.mktemp(suffix='.db')
conn = fb_profile_processor.init_db(temp_db)
cur = conn.cursor()
cur.execute("PRAGMA table_info(profiles)")
schema = cur.fetchall()
print(f"Schema columns: {len(schema)}")
assert len(schema) == 21, "Should have 21 columns (hybrid schema)"

# Verify key columns exist
column_names = [col[1] for col in schema]
required_columns = ['id', 'input_url', 'clean_url', 'profile_id', 'resolved_url',
                   'enrichment_status', 'browser_resolved_url']
for col in required_columns:
    assert col in column_names, f"Column '{col}' should exist"
    print(f"  ✓ Column '{col}' exists")

conn.close()
os.remove(temp_db)
print("✅ Database initialization test passed")

print("\n" + "="*50)
print("ALL TESTS PASSED ✅")
print("="*50)

