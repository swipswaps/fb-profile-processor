#!/usr/bin/env python3
"""
Fix Export Issues - Add Images and Unify Databases

Issues identified:
1. ZIP exports have no images (fb_picture_url exists but not downloaded)
2. Two databases causing confusion (test_profiles.db vs facebook_profiles.db)
3. Explanation without action pattern still present

This code FIXES these issues instead of just explaining them.
"""

import sqlite3
import requests
from pathlib import Path
from zipfile import ZipFile
import json
import csv
from datetime import datetime
from typing import List, Dict
import shutil


class ImageDownloader:
    """Download profile images from URLs"""

    def __init__(self, output_dir: str = "profile_images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def download_image(self, url: str, fb_id: str) -> str:
        """
        Download image from URL.
        
        Args:
            url: Image URL (fb_picture_url)
            fb_id: Facebook profile ID
            
        Returns:
            Local path to downloaded image
        """
        if not url:
            return None

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # Save image
            image_path = self.output_dir / f"{fb_id}.jpg"
            with open(image_path, 'wb') as f:
                f.write(response.content)

            print(f"✅ Downloaded: {fb_id}.jpg ({len(response.content)} bytes)")
            return str(image_path)

        except Exception as e:
            print(f"❌ Failed to download {fb_id}: {e}")
            return None

    def download_all_images(self, db_path: str) -> Dict[str, str]:
        """
        Download all images from database.
        
        Args:
            db_path: Path to SQLite database
            
        Returns:
            Dict mapping fb_id to local image path
        """
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT fb_id, fb_picture_url 
            FROM profiles 
            WHERE fb_picture_url IS NOT NULL
        """)

        image_map = {}
        total = 0
        downloaded = 0

        for fb_id, url in cursor.fetchall():
            total += 1
            local_path = self.download_image(url, fb_id)
            if local_path:
                image_map[fb_id] = local_path
                downloaded += 1

                # Update database with local path
                cursor.execute("""
                    UPDATE profiles 
                    SET local_picture_path = ? 
                    WHERE fb_id = ?
                """, (local_path, fb_id))

        conn.commit()
        conn.close()

        print(f"\n✅ Downloaded {downloaded}/{total} images")
        return image_map


class EnhancedExporter:
    """Export profiles with images included"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.downloader = ImageDownloader()

    def export_with_images(self, output_filename: str = None) -> str:
        """
        Export profiles to ZIP with images.
        
        Args:
            output_filename: Output ZIP filename
            
        Returns:
            Path to created ZIP file
        """
        if not output_filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"fb_profiles_with_images_{timestamp}.zip"

        # Download all images first
        print("Downloading profile images...")
        image_map = self.downloader.download_all_images(self.db_path)

        # Get profile data
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM profiles")
        profiles = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Create ZIP
        print(f"\nCreating ZIP: {output_filename}")
        with ZipFile(output_filename, 'w') as zipf:
            # Add CSV
            csv_data = self._create_csv(profiles)
            zipf.writestr('profiles.csv', csv_data)
            print(f"  ✅ Added profiles.csv")

            # Add JSON
            json_data = self._create_json(profiles)
            zipf.writestr('profiles.json', json_data)
            print(f"  ✅ Added profiles.json")

            # Add images
            images_added = 0
            for fb_id, image_path in image_map.items():
                if Path(image_path).exists():
                    zipf.write(image_path, f"images/{fb_id}.jpg")
                    images_added += 1

            print(f"  ✅ Added {images_added} images")

            # Add README
            readme = self._create_readme(len(profiles), images_added)
            zipf.writestr('README.txt', readme)
            print(f"  ✅ Added README.txt")

        print(f"\n✅ Export complete: {output_filename}")
        print(f"   Profiles: {len(profiles)}")
        print(f"   Images: {images_added}")

        return output_filename

    def _create_csv(self, profiles: List[Dict]) -> str:
        """Create CSV data"""
        if not profiles:
            return ""

        import io
        output = io.StringIO()

        # Get all fields
        fields = list(profiles[0].keys())
        writer = csv.DictWriter(output, fieldnames=fields)

        writer.writeheader()
        writer.writerows(profiles)

        return output.getvalue()

    def _create_json(self, profiles: List[Dict]) -> str:
        """Create JSON data"""
        return json.dumps(profiles, indent=2, default=str)

    def _create_readme(self, profile_count: int, image_count: int) -> str:
        """Create README"""
        return f"""Facebook Profiles Export
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Contents:
- profiles.csv: {profile_count} profiles in CSV format
- profiles.json: {profile_count} profiles in JSON format
- images/: {image_count} profile pictures

Image Format:
- Filename: {{fb_id}}.jpg
- Source: Downloaded from fb_picture_url

Fields Included:
- fb_id: Facebook profile ID
- fb_name: Seller name
- fb_location_name: Location
- fb_join_date: Join date
- fb_active_listings_count: Active listings
- fb_picture_url: Original image URL
- local_picture_path: Local image path
- And more...

Note: Some fields may be NULL if not available for that seller.
"""


class DatabaseUnifier:
    """Unify test_profiles.db enriched data into facebook_profiles.db"""

    def __init__(self, source_db: str = "test_profiles.db", target_db: str = "facebook_profiles.db"):
        self.source_db = source_db
        self.target_db = target_db

    def unify(self, backup: bool = True) -> Dict:
        """
        Merge enriched profiles from source to target.
        
        Args:
            backup: Create backup of target before merging
            
        Returns:
            Stats dict
        """
        if backup:
            backup_path = f"{self.target_db}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(self.target_db, backup_path)
            print(f"✅ Backup created: {backup_path}")

        # Get enriched profiles from source
        source_conn = sqlite3.connect(self.source_db)
        source_conn.row_factory = sqlite3.Row
        source_cursor = source_conn.cursor()

        source_cursor.execute("""
            SELECT * FROM profiles 
            WHERE enrichment_status = 'enriched'
        """)

        enriched = [dict(row) for row in source_cursor.fetchall()]
        source_conn.close()

        print(f"\n📊 Found {len(enriched)} enriched profiles in {self.source_db}")

        # Update target database
        target_conn = sqlite3.connect(self.target_db)
        target_cursor = target_conn.cursor()

        updated = 0
        inserted = 0

        for profile in enriched:
            fb_id = profile['fb_id']

            # Check if exists
            target_cursor.execute("SELECT id FROM profiles WHERE fb_id = ?", (fb_id,))
            exists = target_cursor.fetchone()

            if exists:
                # Update existing
                fields = ', '.join([f"{k} = ?" for k in profile.keys() if k != 'id'])
                values = [v for k, v in profile.items() if k != 'id']
                values.append(fb_id)

                target_cursor.execute(f"""
                    UPDATE profiles 
                    SET {fields}
                    WHERE fb_id = ?
                """, values)
                updated += 1
            else:
                # Insert new
                fields = ', '.join(profile.keys())
                placeholders = ', '.join(['?' for _ in profile])

                target_cursor.execute(f"""
                    INSERT INTO profiles ({fields})
                    VALUES ({placeholders})
                """, list(profile.values()))
                inserted += 1

        target_conn.commit()
        target_conn.close()

        stats = {
            'source_db': self.source_db,
            'target_db': self.target_db,
            'enriched_found': len(enriched),
            'updated': updated,
            'inserted': inserted,
            'total_affected': updated + inserted,
        }

        print(f"\n✅ Unification complete:")
        print(f"   Updated: {updated} profiles")
        print(f"   Inserted: {inserted} profiles")
        print(f"   Total: {updated + inserted} enriched profiles now in {self.target_db}")

        return stats


def main():
    """Main execution - FIX the issues"""

    print("=" * 80)
    print("FIXING EXPORT ISSUES")
    print("=" * 80)

    # Issue 1: Unify databases
    print("\n1. Unifying databases...")
    unifier = DatabaseUnifier()
    stats = unifier.unify()

    # Issue 2: Export with images
    print("\n2. Creating export with images...")
    exporter = EnhancedExporter("facebook_profiles.db")
    zip_file = exporter.export_with_images()

    # Verify the new export
    print("\n3. Verifying export...")
    with ZipFile(zip_file, 'r') as zipf:
        file_list = zipf.namelist()
        images = [f for f in file_list if f.startswith('images/')]

        print(f"\n✅ Verification:")
        print(f"   Files in ZIP: {len(file_list)}")
        print(f"   Images: {len(images)}")
        print(f"   Has CSV: {'profiles.csv' in file_list}")
        print(f"   Has JSON: {'profiles.json' in file_list}")
        print(f"   Has README: {'README.txt' in file_list}")

    print("\n" + "=" * 80)
    print("✅ ALL ISSUES FIXED")
    print("=" * 80)
    print(f"\nNew export: {zip_file}")
    print(f"This export includes {len(images)} profile images")
    print(f"Enriched data from test_profiles.db is now in facebook_profiles.db")


if __name__ == "__main__":
    main()
