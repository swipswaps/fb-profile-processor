"""
Feature Flags for Facebook Profile Processor
============================================

Allows enabling/disabling features without code changes.
Designed for safe, gradual rollout of new capabilities.

Usage:
    from feature_flags import FeatureFlags
    
    if FeatureFlags.is_enabled('api_integration'):
        show_api_features()
    else:
        show_firefox_only()  # Current default behavior
"""

import os
from typing import Dict


class FeatureFlags:
    """
    Centralized feature flag management.
    
    All API features are DISABLED by default.
    Firefox enrichment remains the default and stable method.
    """

    # Default values - API disabled, Firefox enabled
    DEFAULTS = {
        # Core features (always enabled)
        'firefox_enrichment': True,
        'http_collection': True,
        'export_functionality': True,
        'edit_records': True,
        'analytics': True,

        # API features (disabled by default)
        'api_integration': False,
        'api_credentials_ui': False,
        'hybrid_provider': False,

        # Experimental features
        'experimental_ui': False,
        'card_view': True,  # New card view - enabled
        'detail_view': True,  # New detail view - enabled
    }

    @staticmethod
    def is_enabled(feature: str) -> bool:
        """
        Check if a feature is enabled.
        
        Priority:
        1. Environment variable (ENABLE_{FEATURE}=true/false)
        2. Default value from DEFAULTS dict
        3. False if not found
        
        Args:
            feature: Feature name (e.g., 'api_integration')
            
        Returns:
            bool: True if feature is enabled
        """
        # Check environment variable first
        env_key = f"ENABLE_{feature.upper()}"
        env_value = os.getenv(env_key)

        if env_value is not None:
            return env_value.lower() in ('true', '1', 'yes', 'on')

        # Fall back to default
        return FeatureFlags.DEFAULTS.get(feature, False)

    @staticmethod
    def get_all() -> Dict[str, bool]:
        """
        Get all feature flags with current values.
        
        Returns:
            dict: Feature name -> enabled status
        """
        return {
            feature: FeatureFlags.is_enabled(feature)
            for feature in FeatureFlags.DEFAULTS.keys()
        }

    @staticmethod
    def get_api_status() -> Dict[str, any]:
        """
        Get API-specific feature status for dashboard display.
        
        Returns:
            dict: API configuration status
        """
        return {
            'api_enabled': FeatureFlags.is_enabled('api_integration'),
            'hybrid_enabled': FeatureFlags.is_enabled('hybrid_provider'),
            'credentials_ui_enabled': FeatureFlags.is_enabled('api_credentials_ui'),
            'has_api_token': bool(os.getenv('FACEBOOK_ACCESS_TOKEN')),
            'has_app_id': bool(os.getenv('FACEBOOK_APP_ID')),
        }

    @staticmethod
    def require_for_api() -> bool:
        """
        Check if all requirements for API usage are met.
        
        Returns:
            bool: True if API can be used
        """
        if not FeatureFlags.is_enabled('api_integration'):
            return False

        # Check for credentials
        token = os.getenv('FACEBOOK_ACCESS_TOKEN')
        app_id = os.getenv('FACEBOOK_APP_ID')

        return bool(token and app_id)


# Convenience function
def feature_enabled(feature: str) -> bool:
    """Shorthand for FeatureFlags.is_enabled()"""
    return FeatureFlags.is_enabled(feature)

