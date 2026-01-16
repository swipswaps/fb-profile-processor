"""
Enrichment Coordinator
======================

Routes enrichment requests to the appropriate provider (Firefox or API)
WITHOUT modifying the existing selenium_enricher.py.

IMPORTANT: This is an ADDITIVE module. The existing Firefox enrichment
continues to work exactly as before. API is optional and only used
when explicitly enabled.

Default behavior: Uses Firefox (existing selenium_enricher)
Optional: Uses API if configured and enabled via feature flags
"""

import os
from typing import Dict, Optional, Any
from dataclasses import dataclass, field

from feature_flags import FeatureFlags


@dataclass
class EnrichmentResult:
    """Result of an enrichment attempt"""
    success: bool
    method: str  # 'firefox', 'api', 'hybrid'
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    fallback_used: bool = False


class EnrichmentCoordinator:
    """
    Coordinates between Firefox and API enrichment.
    
    DEFAULT: Uses Firefox (existing behavior, unchanged)
    OPTIONAL: Uses API if configured and enabled
    
    This class wraps existing functionality - it does NOT modify
    selenium_enricher.py or any existing code.
    """
    
    def __init__(self, use_api: bool = None, use_hybrid: bool = None):
        """
        Initialize the coordinator.
        
        Args:
            use_api: Force API mode (None = check feature flags)
            use_hybrid: Force hybrid mode (None = check feature flags)
        """
        # Check feature flags if not explicitly set
        if use_api is None:
            use_api = FeatureFlags.is_enabled('api_integration')
        if use_hybrid is None:
            use_hybrid = FeatureFlags.is_enabled('hybrid_provider')
        
        self.use_api = use_api
        self.use_hybrid = use_hybrid
        self.provider = None
        
        # Only initialize API provider if enabled and credentials exist
        if (use_api or use_hybrid) and FeatureFlags.require_for_api():
            self._init_api_provider()
    
    def _init_api_provider(self):
        """Initialize API provider if available"""
        try:
            from data_providers import get_provider, FacebookConfig
            config = FacebookConfig.from_env()
            if config.has_api_credentials():
                self.provider = get_provider(config)
        except ImportError:
            # data_providers not available - that's fine
            pass
        except Exception as e:
            print(f"[EnrichmentCoordinator] API provider init failed: {e}")
    
    def enrich(self, driver, profile_id: str, fb_id: str) -> EnrichmentResult:
        """
        Enrich a profile using the appropriate method.
        
        DEFAULT: Firefox enrichment (existing selenium_enricher)
        FALLBACK: API (if configured and enabled)
        
        Args:
            driver: Selenium WebDriver (for Firefox enrichment)
            profile_id: Database profile ID
            fb_id: Facebook profile/user ID
            
        Returns:
            EnrichmentResult with enriched data
        """
        # Hybrid mode: Try API first, fallback to Firefox
        if self.use_hybrid and self.provider:
            api_result = self._try_api_enrichment(fb_id)
            if api_result.success:
                return api_result
            # API failed, fall back to Firefox
            firefox_result = self._firefox_enrichment(driver, profile_id, fb_id)
            firefox_result.fallback_used = True
            return firefox_result
        
        # API-only mode (rare - most users won't have API access)
        if self.use_api and self.provider:
            return self._try_api_enrichment(fb_id)
        
        # DEFAULT: Firefox enrichment (existing behavior)
        return self._firefox_enrichment(driver, profile_id, fb_id)
    
    def _firefox_enrichment(self, driver, profile_id: str, fb_id: str) -> EnrichmentResult:
        """
        Use existing Firefox enrichment (unchanged).
        
        This is the DEFAULT and most reliable method.
        """
        try:
            from selenium_enricher import enrich_profile
            data = enrich_profile(driver, profile_id, fb_id)
            return EnrichmentResult(
                success=bool(data),
                method='firefox',
                data=data if data else {}
            )
        except Exception as e:
            return EnrichmentResult(
                success=False,
                method='firefox',
                error=str(e)
            )
    
    def _try_api_enrichment(self, fb_id: str) -> EnrichmentResult:
        """
        Try API enrichment (optional, requires credentials).
        """
        if not self.provider:
            return EnrichmentResult(
                success=False,
                method='api',
                error='API provider not configured'
            )
        
        try:
            profile_data = self.provider.get_profile(fb_id)
            if profile_data:
                return EnrichmentResult(
                    success=True,
                    method='api',
                    data=profile_data.to_dict() if hasattr(profile_data, 'to_dict') else profile_data
                )
            return EnrichmentResult(
                success=False,
                method='api',
                error='No data returned from API'
            )
        except Exception as e:
            return EnrichmentResult(
                success=False,
                method='api',
                error=str(e)
            )
    
    @property
    def current_method(self) -> str:
        """Get the current enrichment method being used"""
        if self.use_hybrid:
            return 'hybrid'
        elif self.use_api and self.provider:
            return 'api'
        return 'firefox'  # Default

