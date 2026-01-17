#!/usr/bin/env python3
"""
Database Migration - Add Facebook API Support

Adds tables and columns needed for future API integration:
- API token management
- Rate limit tracking
- Data source tracking
- API accessibility flags

Run this to prepare database for API integration.
"""

import sqlite3
import sys
from datetime import datetime


def migrate_database(db_path: str = "facebook_profiles.db"):
    """
    Add API-related schema enhancements.
    
    Args:
        db_path: Path to SQLite database
    """
    print(f"Migrating database: {db_path}")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get current schema version
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
    """)

    cursor.execute("SELECT MAX(version) FROM schema_version")
    current_version = cursor.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0

    print(f"Current schema version: {current_version}")

    migrations = []

    # ========== Migration 1: Add API fields to profiles ==========
    if current_version < 1:
        print("\n[1] Adding API fields to profiles table...")

        migrations.append((
            "Add API accessibility tracking",
            """
            ALTER TABLE profiles ADD COLUMN api_accessible BOOLEAN DEFAULT FALSE;
            ALTER TABLE profiles ADD COLUMN api_last_sync TIMESTAMP;
            ALTER TABLE profiles ADD COLUMN data_source VARCHAR(20) DEFAULT 'scraper';
            """
        ))

    # ========== Migration 2: Create API tokens table ==========
    if current_version < 2:
        print("\n[2] Creating api_tokens table...")

        migrations.append((
            "Create API tokens table",
            """
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_type VARCHAR(50) NOT NULL,
                access_token TEXT NOT NULL,
                token_expires_at TIMESTAMP,
                scopes TEXT,
                page_id VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                notes TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_api_tokens_type ON api_tokens(token_type);
            CREATE INDEX IF NOT EXISTS idx_api_tokens_active ON api_tokens(is_active);
            """
        ))

    # ========== Migration 3: Create rate limits tracking ==========
    if current_version < 3:
        print("\n[3] Creating api_rate_limits table...")

        migrations.append((
            "Create rate limits tracking table",
            """
            CREATE TABLE IF NOT EXISTS api_rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider VARCHAR(50) NOT NULL,
                endpoint VARCHAR(200),
                limit_total INTEGER,
                limit_remaining INTEGER,
                reset_at TIMESTAMP,
                measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_rate_limits_provider ON api_rate_limits(provider);
            CREATE INDEX IF NOT EXISTS idx_rate_limits_measured ON api_rate_limits(measured_at);
            """
        ))

    # ========== Migration 4: Create API request log ==========
    if current_version < 4:
        print("\n[4] Creating api_request_log table...")

        migrations.append((
            "Create API request logging table",
            """
            CREATE TABLE IF NOT EXISTS api_request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider VARCHAR(50) NOT NULL,
                endpoint VARCHAR(200),
                method VARCHAR(10),
                profile_id VARCHAR(100),
                status_code INTEGER,
                error_message TEXT,
                response_time_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE INDEX IF NOT EXISTS idx_request_log_profile ON api_request_log(profile_id);
            CREATE INDEX IF NOT EXISTS idx_request_log_status ON api_request_log(status_code);
            CREATE INDEX IF NOT EXISTS idx_request_log_created ON api_request_log(created_at);
            """
        ))

    # ========== Migration 5: Create provider config table ==========
    if current_version < 5:
        print("\n[5] Creating provider_config table...")

        migrations.append((
            "Create provider configuration table",
            """
            CREATE TABLE IF NOT EXISTS provider_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_key VARCHAR(100) UNIQUE NOT NULL,
                config_value TEXT,
                config_type VARCHAR(20) DEFAULT 'string',
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Insert default config
            INSERT OR IGNORE INTO provider_config (config_key, config_value, config_type, description)
            VALUES 
                ('provider_type', 'scraper', 'string', 'Current data provider: scraper, api, or hybrid'),
                ('scraper_enabled', 'true', 'boolean', 'Enable browser scraping'),
                ('api_enabled', 'false', 'boolean', 'Enable Graph API'),
                ('cache_enabled', 'true', 'boolean', 'Enable result caching'),
                ('cache_ttl_seconds', '3600', 'integer', 'Cache time-to-live in seconds'),
                ('max_requests_per_minute', '30', 'integer', 'Rate limiting threshold');
            """
        ))

    # Execute migrations atomically
    try:
        # Begin explicit transaction for atomicity
        conn.isolation_level = None
        cursor.execute("BEGIN TRANSACTION")

        for i, (description, sql) in enumerate(migrations, start=current_version + 1):
            print(f"\nApplying migration {i}: {description}")

            # Split and execute each statement
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            for statement in statements:
                cursor.execute(statement)

            # Record migration
            cursor.execute("""
                INSERT INTO schema_version (version, description)
                VALUES (?, ?)
            """, (i, description))

            print(f"  ✅ Migration {i} complete")

        # Commit all changes atomically
        cursor.execute("COMMIT")
        print("\n✅ All migrations committed atomically")

        # Verify final schema
        cursor.execute("SELECT MAX(version) FROM schema_version")
        final_version = cursor.fetchone()[0]

        print("\n" + "=" * 60)
        print(f"✅ Migration complete!")
        print(f"Schema version: {current_version} → {final_version}")

        # Show table summary
        print("\nTables in database:")
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """)

        for (table_name,) in cursor.fetchall():
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  {table_name:30} {count:6} rows")

        return True

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        try:
            cursor.execute("ROLLBACK")
            print("  ↩️ Changes rolled back")
        except:
            pass
        return False

    finally:
        conn.close()


def verify_migration(db_path: str = "facebook_profiles.db"):
    """Verify migration was successful"""
    print("\n" + "=" * 60)
    print("VERIFICATION")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check for new columns in profiles
    cursor.execute("PRAGMA table_info(profiles)")
    columns = {row[1]: row[2] for row in cursor.fetchall()}

    print("\nProfiles table new columns:")
    for col in ['api_accessible', 'api_last_sync', 'data_source']:
        if col in columns:
            print(f"  ✅ {col} ({columns[col]})")
        else:
            print(f"  ❌ {col} MISSING")

    # Check for new tables
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name IN (
            'api_tokens', 
            'api_rate_limits', 
            'api_request_log', 
            'provider_config'
        )
    """)

    new_tables = [row[0] for row in cursor.fetchall()]

    print("\nNew tables:")
    for table in ['api_tokens', 'api_rate_limits', 'api_request_log', 'provider_config']:
        if table in new_tables:
            print(f"  ✅ {table}")
        else:
            print(f"  ❌ {table} MISSING")

    # Show provider config
    print("\nProvider configuration:")
    cursor.execute("SELECT config_key, config_value FROM provider_config ORDER BY config_key")
    for key, value in cursor.fetchall():
        print(f"  {key:30} = {value}")

    conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate database for Facebook API support")
    parser.add_argument(
        '--database',
        default='facebook_profiles.db',
        help='Path to SQLite database (default: facebook_profiles.db)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify migration, do not apply'
    )

    args = parser.parse_args()

    if args.verify_only:
        verify_migration(args.database)
    else:
        success = migrate_database(args.database)
        if success:
            verify_migration(args.database)
            sys.exit(0)
        else:
            sys.exit(1)
