#!/usr/bin/env python3
"""
Provider Manager - Bridges data_providers.py with existing dashboard/enricher

This module:
1. Provides simplified interface for dashboard
2. Handles provider lifecycle (init, cleanup)
3. Manages config from environment and database
4. Supports hot-switching between providers
"""

import os
import sqlite3
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager

from data_providers import (
    DataProvider,
    FacebookConfig,
    ScraperProvider,
    GraphAPIProvider,
    HybridProvider,
    ProfileData,
    DataSource,
    get_provider
)

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Singleton-like manager for data providers.
    
    Usage:
        manager = ProviderManager(db_path='facebook_profiles.db')
        profile = manager.enrich_profile('61550649184857')
        manager.cleanup()
    """

    def __init__(self, db_path: str = 'facebook_profiles.db'):
        self.db_path = db_path
        self._provider: Optional[DataProvider] = None
        self._config: Optional[FacebookConfig] = None

    @property
    def config(self) -> FacebookConfig:
        """Get or create config from environment + database"""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    @property
    def provider(self) -> DataProvider:
        """Get or create the active provider"""
        if self._provider is None:
            self._provider = get_provider(self.config)
        return self._provider

    def _load_config(self) -> FacebookConfig:
        """Load config from environment, fallback to database"""
        # Start with env-based config
        config = FacebookConfig.from_env()

        # Override with database config if available
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='provider_config'")
            if cur.fetchone():
                cur.execute("SELECT config_key, config_value FROM provider_config")
                db_config = dict(cur.fetchall())

                # Apply database overrides
                if 'provider_type' in db_config:
                    config.provider_type = db_config['provider_type']
                if 'scraper_enabled' in db_config:
                    config.scraper_enabled = db_config['scraper_enabled'].lower() == 'true'
                if 'cache_enabled' in db_config:
                    config.cache_enabled = db_config['cache_enabled'].lower() == 'true'
                if 'cache_ttl_seconds' in db_config:
                    config.cache_ttl = int(db_config['cache_ttl_seconds'])
                if 'max_requests_per_minute' in db_config:
                    config.max_requests_per_minute = int(db_config['max_requests_per_minute'])

            conn.close()
        except Exception as e:
            logger.warning(f"Could not load database config: {e}")

        return config

    def enrich_profile(self, fb_id: str) -> Optional[Dict[str, Any]]:
        """
        Enrich a single profile using the configured provider.
        Returns dict compatible with update_profile_in_db().
        """
        profile = self.provider.get_profile(fb_id)

        if profile:
            # Convert ProfileData to dict for database update
            return {
                'fb_name': profile.fb_name,
                'fb_location_name': profile.fb_location_name,
                'fb_join_date': profile.fb_join_date,
                'fb_picture_url': profile.fb_picture_url,
                'fb_active_listings_count': profile.fb_active_listings_count,
                'fb_response_rate': profile.fb_response_rate,
                'data_source': profile.source,
                'api_accessible': profile.api_accessible,
                'enrichment_status': 'complete',
            }
        return None

    def is_available(self) -> bool:
        """Check if provider is ready"""
        return self.provider.is_available()

    def get_status(self) -> Dict[str, Any]:
        """Get provider status for display"""
        rate_info = self.provider.get_rate_limit_info()
        return {
            'provider_type': self.config.provider_type,
            'available': self.is_available(),
            'rate_limit_provider': rate_info.provider,
            'rate_limit_remaining': rate_info.limit_remaining,
            'recommended_delay': rate_info.recommended_delay,
            'api_credentials_configured': self.config.has_api_credentials(),
        }

    def cleanup(self):
        """Clean up provider resources"""
        if self._provider:
            if hasattr(self._provider, 'cleanup'):
                self._provider.cleanup()
            self._provider = None

    def reset(self):
        """Reset provider and config (forces reload)"""
        self.cleanup()
        self._config = None


@contextmanager
def provider_session(db_path: str = 'facebook_profiles.db'):
    """Context manager for provider usage with automatic cleanup"""
    manager = ProviderManager(db_path)
    try:
        yield manager
    finally:
        manager.cleanup()

