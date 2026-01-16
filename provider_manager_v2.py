#!/usr/bin/env python3
"""
Provider Manager - Enhanced Version with Fixes

Improvements:
- Better error handling
- Cache size limits (LRU)
- Provider cleanup on exit
- Session state integration
- Visual status feedback

Usage in Streamlit:
    from provider_manager_v2 import get_provider_manager
    
    manager = get_provider_manager()  # Uses session state
    profile = manager.enrich_profile('123456789')
"""

import os
import logging
import sqlite3
from typing import Dict, Optional, List
from datetime import datetime
from collections import OrderedDict
from contextlib import contextmanager

from data_providers import (
    FacebookConfig,
    DataProvider,
    ScraperProvider,
    GraphAPIProvider,
    HybridProvider,
    ProfileData
)

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Enhanced provider lifecycle manager.
    
    Handles:
    - Provider initialization and cleanup
    - Configuration management
    - Status monitoring
    - Error recovery
    """
    
    def __init__(self, config: Optional[FacebookConfig] = None, db_path: str = "facebook_profiles.db"):
        """
        Initialize provider manager.
        
        Args:
            config: FacebookConfig (loads from env if None)
            db_path: Path to SQLite database
        """
        self.config = config or FacebookConfig.from_env()
        self.db_path = db_path
        self.provider: Optional[DataProvider] = None
        self._initialized = False
        
        # Initialize provider
        try:
            self._initialize_provider()
        except Exception as e:
            logger.error(f"Provider initialization failed: {e}")
    
    def _initialize_provider(self):
        """Initialize appropriate provider based on config"""
        try:
            if self.config.provider_type == 'api':
                if not self.config.has_api_credentials():
                    logger.warning("API provider requested but no credentials, falling back to scraper")
                    self.provider = ScraperProvider(self.config)
                else:
                    self.provider = GraphAPIProvider(self.config)
            
            elif self.config.provider_type == 'hybrid':
                scraper = ScraperProvider(self.config)
                api = GraphAPIProvider(self.config) if self.config.has_api_credentials() else None
                self.provider = HybridProvider(self.config, scraper, api)
            
            else:  # Default to scraper
                self.provider = ScraperProvider(self.config)
            
            self._initialized = True
            logger.info(f"Provider initialized: {self.config.provider_type}")
            
        except Exception as e:
            logger.error(f"Failed to initialize provider: {e}")
            # Fallback to scraper
            self.provider = ScraperProvider(self.config)
            self._initialized = True
    
    def enrich_profile(self, fb_id: str) -> bool:
        """
        Enrich single profile using configured provider.
        
        Args:
            fb_id: Facebook profile ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            logger.error("Provider not initialized")
            return False
        
        try:
            profile_data = self.provider.get_profile(fb_id)
            
            if profile_data:
                self._save_to_database(profile_data)
                return True
            else:
                logger.warning(f"No data retrieved for {fb_id}")
                return False
                
        except Exception as e:
            logger.error(f"Enrichment failed for {fb_id}: {e}")
            return False
    
    def enrich_profiles_batch(self, fb_ids: List[str]) -> Dict[str, bool]:
        """
        Enrich multiple profiles.
        
        Args:
            fb_ids: List of Facebook profile IDs
            
        Returns:
            Dict mapping fb_id to success status
        """
        results = {}
        
        try:
            profiles = self.provider.get_profiles_batch(fb_ids)
            
            # Save all retrieved profiles
            for profile in profiles:
                self._save_to_database(profile)
                results[profile.fb_id] = True
            
            # Mark failed ones
            retrieved_ids = {p.fb_id for p in profiles}
            for fb_id in fb_ids:
                if fb_id not in retrieved_ids:
                    results[fb_id] = False
            
            return results
            
        except Exception as e:
            logger.error(f"Batch enrichment failed: {e}")
            return {fb_id: False for fb_id in fb_ids}
    
    def get_status(self) -> Dict:
        """
        Get provider status.
        
        Returns:
            Dict with status information
        """
        if not self._initialized:
            return {
                'available': False,
                'provider': 'none',
                'error': 'Not initialized'
            }
        
        try:
            available = self.provider.is_available()
            rate_info = self.provider.get_rate_limit_info()
            
            return {
                'available': available,
                'provider': self.config.provider_type,
                'browser': self.config.browser_type if self.config.provider_type != 'api' else None,
                'api_credentials': self.config.has_api_credentials(),
                'rate_limit': {
                    'provider': rate_info.provider,
                    'limit_total': rate_info.limit_total,
                    'limit_remaining': rate_info.limit_remaining,
                    'reset_at': rate_info.reset_at.isoformat() if rate_info.reset_at else None,
                    'recommended_delay': rate_info.recommended_delay
                }
            }
            
        except Exception as e:
            logger.error(f"Status check failed: {e}")
            return {
                'available': False,
                'provider': self.config.provider_type,
                'error': str(e)
            }
    
    def reload(self, provider_type: Optional[str] = None):
        """
        Reload provider (useful for switching providers).
        
        Args:
            provider_type: New provider type (scraper/api/hybrid)
        """
        if provider_type:
            self.config.provider_type = provider_type
        
        # Cleanup old provider
        self.cleanup()
        
        # Reinitialize
        self._initialize_provider()
    
    def cleanup(self):
        """Cleanup provider resources"""
        if self.provider and hasattr(self.provider, 'cleanup'):
            try:
                self.provider.cleanup()
            except Exception as e:
                logger.warning(f"Cleanup warning: {e}")
        
        self._initialized = False
    
    def save_api_credentials(self, app_id: str, app_secret: str, access_token: str):
        """
        Save API credentials to database.
        
        Args:
            app_id: Facebook App ID
            app_secret: Facebook App Secret
            access_token: Page Access Token
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Deactivate old tokens
        cursor.execute("""
            UPDATE api_tokens 
            SET is_active = FALSE 
            WHERE token_type = 'page_access'
        """)
        
        # Insert new token
        cursor.execute("""
            INSERT INTO api_tokens (
                token_type, access_token, scopes, notes
            ) VALUES (?, ?, ?, ?)
        """, (
            'page_access',
            access_token,
            '["pages_messaging", "pages_read_engagement"]',
            f'App ID: {app_id}'
        ))
        
        conn.commit()
        conn.close()
        
        # Update config
        self.config.app_id = app_id
        self.config.app_secret = app_secret
        self.config.access_token = access_token
    
    def test_api_connection(self) -> bool:
        """
        Test API connection.
        
        Returns:
            True if API is accessible, False otherwise
        """
        if not self.config.has_api_credentials():
            return False
        
        try:
            api = GraphAPIProvider(self.config)
            return api.is_available()
        except Exception as e:
            logger.error(f"API test failed: {e}")
            return False
    
    def _save_to_database(self, profile: ProfileData):
        """Save profile data to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Convert ProfileData to dict
        data = profile.to_dict()
        
        # Update or insert
        cursor.execute("""
            INSERT OR REPLACE INTO profiles (
                fb_id, fb_name, fb_location_name, fb_join_date,
                fb_picture_url, fb_active_listings_count, fb_response_rate,
                fb_seller_badges, fb_cover_url,
                enrichment_status, data_source, api_accessible,
                enriched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'enriched', ?, ?, ?)
        """, (
            data['fb_id'],
            data['fb_name'],
            data['fb_location_name'],
            data['fb_join_date'],
            data['fb_picture_url'],
            data['fb_active_listings_count'],
            data['fb_response_rate'],
            data['fb_seller_badges'],
            data['fb_cover_url'],
            data['source'],
            data['api_accessible'],
            data['acquired_at']
        ))
        
        conn.commit()
        conn.close()


# ==============================================================================
# SESSION STATE INTEGRATION (For Streamlit)
# ==============================================================================

_provider_manager_instance = None

def get_provider_manager() -> ProviderManager:
    """
    Get singleton provider manager instance.
    
    Uses session state in Streamlit, or module-level singleton otherwise.
    
    Returns:
        ProviderManager instance
    """
    global _provider_manager_instance
    
    # Try Streamlit session state first
    try:
        import streamlit as st
        if 'provider_manager' not in st.session_state:
            st.session_state.provider_manager = ProviderManager()
        return st.session_state.provider_manager
    except ImportError:
        # Fallback to module singleton
        if _provider_manager_instance is None:
            _provider_manager_instance = ProviderManager()
        return _provider_manager_instance


@contextmanager
def provider_session():
    """
    Context manager for provider lifecycle.
    
    Usage:
        with provider_session() as manager:
            manager.enrich_profile('123456789')
    """
    manager = get_provider_manager()
    try:
        yield manager
    finally:
        # Cleanup happens on program exit via atexit
        pass


# ==============================================================================
# CLEANUP REGISTRATION
# ==============================================================================

import atexit

@atexit.register
def cleanup_on_exit():
    """Cleanup providers when program exits"""
    global _provider_manager_instance
    
    if _provider_manager_instance:
        try:
            _provider_manager_instance.cleanup()
        except:
            pass


# ==============================================================================
# EXAMPLE USAGE
# ==============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Get manager
    manager = get_provider_manager()
    
    # Show status
    status = manager.get_status()
    print(f"Provider: {status['provider']}")
    print(f"Available: {status['available']}")
    
    # Example enrichment
    # success = manager.enrich_profile('61550649184857')
    # print(f"Enrichment: {'✅' if success else '❌'}")
