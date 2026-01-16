#!/usr/bin/env python3
"""
Facebook Data Providers - Future-Proof Architecture

Supports multiple data sources:
- ScraperProvider: Current browser automation (Selenium/Playwright)
- GraphAPIProvider: Official Facebook Graph API (future)
- ContentLibraryProvider: Meta Content Library API (if approved)
- HybridProvider: Intelligent routing between sources

Usage:
    from data_providers import get_provider, FacebookConfig
    
    config = FacebookConfig.from_env()
    provider = get_provider(config)
    
    profile = provider.get_profile('61550649184857')
    if profile:
        print(f"Got profile: {profile.fb_name}")
"""

import os
import json
import requests
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import OrderedDict

logger = logging.getLogger(__name__)


# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

class DataSource(Enum):
    """Available data sources"""
    SCRAPER = "scraper"
    GRAPH_API = "graph_api"
    CONTENT_LIBRARY = "content_library"
    CACHE = "cache"


@dataclass
class ProfileData:
    """
    Unified profile data structure.
    
    Compatible with both scraper output and Graph API response.
    Maps to database schema in profiles table.
    """
    fb_id: str
    fb_name: Optional[str] = None
    fb_location_name: Optional[str] = None
    fb_join_date: Optional[str] = None
    fb_picture_url: Optional[str] = None
    fb_active_listings_count: Optional[int] = None
    fb_response_rate: Optional[str] = None
    fb_seller_badges: Optional[List[str]] = None
    fb_cover_url: Optional[str] = None
    
    # Metadata
    source: str = DataSource.SCRAPER.value
    acquired_at: str = None
    api_accessible: bool = False
    
    def __post_init__(self):
        if self.acquired_at is None:
            self.acquired_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for database insertion"""
        data = asdict(self)
        # Convert list to JSON string for database
        if data['fb_seller_badges']:
            data['fb_seller_badges'] = json.dumps(data['fb_seller_badges'])
        return data


@dataclass
class RateLimitInfo:
    """Rate limit information"""
    provider: str
    limit_total: Optional[int] = None
    limit_remaining: Optional[int] = None
    reset_at: Optional[datetime] = None
    recommended_delay: float = 0.0


@dataclass
class FacebookConfig:
    """Facebook integration configuration"""
    
    # Scraper settings
    browser_type: str = 'firefox'
    scraper_enabled: bool = True
    scraper_headless: bool = False
    
    # API settings
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    access_token: Optional[str] = None
    api_version: str = 'v20.0'
    
    # Provider settings
    provider_type: str = 'scraper'  # 'scraper', 'api', 'hybrid'
    api_fallback: bool = True
    cache_enabled: bool = True
    cache_ttl: int = 3600
    
    # Rate limiting
    max_requests_per_minute: int = 30
    request_delay: float = 2.0
    
    @classmethod
    def from_env(cls):
        """Load configuration from environment variables"""
        return cls(
            # Scraper
            browser_type=os.getenv('BROWSER_TYPE', 'firefox'),
            scraper_enabled=os.getenv('SCRAPER_ENABLED', 'true').lower() == 'true',
            scraper_headless=os.getenv('SCRAPER_HEADLESS', 'false').lower() == 'true',
            
            # API
            app_id=os.getenv('FACEBOOK_APP_ID'),
            app_secret=os.getenv('FACEBOOK_APP_SECRET'),
            access_token=os.getenv('FACEBOOK_ACCESS_TOKEN'),
            api_version=os.getenv('FACEBOOK_API_VERSION', 'v20.0'),
            
            # Provider
            provider_type=os.getenv('DATA_PROVIDER', 'scraper'),
            api_fallback=os.getenv('API_FALLBACK_TO_SCRAPER', 'true').lower() == 'true',
            cache_enabled=os.getenv('CACHE_ENABLED', 'true').lower() == 'true',
            cache_ttl=int(os.getenv('CACHE_TTL_SECONDS', '3600')),
            
            # Rate limiting
            max_requests_per_minute=int(os.getenv('MAX_REQUESTS_PER_MINUTE', '30')),
            request_delay=float(os.getenv('REQUEST_DELAY_SECONDS', '2.0'))
        )
    
    def has_api_credentials(self) -> bool:
        """Check if API credentials are configured"""
        return bool(self.app_id and self.app_secret and self.access_token)
    
    def validate(self) -> List[str]:
        """Validate configuration, return list of errors"""
        errors = []
        
        if self.provider_type == 'api' and not self.has_api_credentials():
            errors.append("API provider requires app_id, app_secret, and access_token")
        
        if self.provider_type not in ['scraper', 'api', 'hybrid']:
            errors.append(f"Invalid provider_type: {self.provider_type}")
        
        if self.browser_type not in ['firefox', 'chrome', 'chromium']:
            errors.append(f"Unsupported browser_type: {self.browser_type}")
        
        return errors


# ==============================================================================
# BASE PROVIDER INTERFACE
# ==============================================================================

class DataProvider(ABC):
    """
    Abstract base class for all data providers.
    
    Ensures consistent interface regardless of data source.
    """
    
    def __init__(self, config: FacebookConfig):
        self.config = config
        self._request_count = 0
        self._last_request_time = None
    
    @abstractmethod
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """
        Fetch single profile by ID.
        
        Args:
            profile_id: Facebook profile/page ID
            
        Returns:
            ProfileData if successful, None otherwise
        """
        pass
    
    @abstractmethod
    def get_profiles_batch(self, profile_ids: List[str]) -> List[ProfileData]:
        """
        Fetch multiple profiles in batch.
        
        Args:
            profile_ids: List of Facebook profile IDs
            
        Returns:
            List of ProfileData (may be partial if some fail)
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if provider is currently available.
        
        Returns:
            True if provider can fetch data, False otherwise
        """
        pass
    
    @abstractmethod
    def get_rate_limit_info(self) -> RateLimitInfo:
        """
        Get current rate limit status.
        
        Returns:
            RateLimitInfo with current limits and usage
        """
        pass
    
    def _throttle(self):
        """Apply rate limiting delay"""
        if self._last_request_time:
            elapsed = (datetime.now() - self._last_request_time).total_seconds()
            delay = self.config.request_delay
            
            if elapsed < delay:
                import time
                time.sleep(delay - elapsed)
        
        self._last_request_time = datetime.now()
        self._request_count += 1


# ==============================================================================
# SCRAPER PROVIDER (Current Implementation)
# ==============================================================================

class ScraperProvider(DataProvider):
    """
    Browser-based scraping provider.
    
    Wraps existing Selenium/Playwright enrichment logic.
    """
    
    def __init__(self, config: FacebookConfig):
        super().__init__(config)
        self.driver = None
        self.driver_initialized = False
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Fetch profile via browser automation"""
        try:
            self._ensure_driver()
            self._throttle()
            
            # Use existing selenium_enricher logic
            profile_dict = self._scrape_profile_data(profile_id)
            
            if profile_dict:
                return ProfileData(
                    fb_id=profile_id,
                    **profile_dict,
                    source=DataSource.SCRAPER.value,
                    api_accessible=False
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Scraper failed for {profile_id}: {e}")
            return None
    
    def get_profiles_batch(self, profile_ids: List[str]) -> List[ProfileData]:
        """Fetch multiple profiles sequentially"""
        results = []
        
        for profile_id in profile_ids:
            profile = self.get_profile(profile_id)
            if profile:
                results.append(profile)
        
        return results
    
    def is_available(self) -> bool:
        """
        Check if browser scraping is available (without spawning browser).

        Only checks if Firefox profile exists - does NOT create a driver.
        Driver is lazily created on first actual scrape request.
        """
        try:
            # If driver is already initialized, it's definitely available
            if self.driver_initialized and self.driver:
                return True

            # Check if Firefox profile exists (without creating driver)
            from selenium_enricher import get_firefox_profile_path
            profile_path = get_firefox_profile_path()
            return profile_path is not None
        except Exception as e:
            logger.error(f"Scraper availability check failed: {e}")
            return False
    
    def get_rate_limit_info(self) -> RateLimitInfo:
        """Scraper has no official limits, but we self-throttle"""
        return RateLimitInfo(
            provider=DataSource.SCRAPER.value,
            limit_total=None,
            limit_remaining=None,
            recommended_delay=self.config.request_delay
        )
    
    def _ensure_driver(self):
        """Initialize browser driver if needed"""
        if not self.driver_initialized:
            # Import here to avoid dependency if not using scraper
            from selenium_enricher import create_firefox_driver, cleanup_temp_profile

            self.driver, self._temp_profile = create_firefox_driver()
            self.driver_initialized = True

            if not self.driver:
                raise RuntimeError("Failed to create Firefox driver")

    def _scrape_profile_data(self, profile_id: str) -> Dict:
        """
        Scrape profile data using existing selenium enricher.

        Args:
            profile_id: Facebook profile ID

        Returns:
            Dict with profile data, or empty dict on failure
        """
        try:
            from selenium_enricher import enrich_profile

            # enrich_profile expects: (driver, profile_id, fb_id)
            # Returns dict with: browser_profile_name, browser_profile_location, etc.
            result = enrich_profile(self.driver, profile_id, profile_id)

            if not result or not isinstance(result, dict):
                logger.warning(f"enrich_profile returned invalid data: {type(result)}")
                return {}

            # Map selenium_enricher output to ProfileData fields
            return {
                'fb_name': result.get('browser_profile_name'),
                'fb_location_name': result.get('browser_profile_location'),
                'fb_join_date': result.get('browser_marketplace_join_date'),
                'fb_picture_url': result.get('browser_profile_pic_url'),
                'fb_active_listings_count': result.get('browser_marketplace_listings_count'),
                'fb_response_rate': result.get('browser_marketplace_response_rate'),
                'fb_seller_badges': result.get('browser_marketplace_badges'),
            }

        except ImportError:
            logger.error("selenium_enricher module not found")
            return {}
        except Exception as e:
            logger.error(f"Enrichment failed for {profile_id}: {e}")
            return {}
    
    def cleanup(self):
        """Clean up browser resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
            self.driver_initialized = False

        # Cleanup temp profile if it exists
        try:
            from selenium_enricher import cleanup_temp_profile
            cleanup_temp_profile()
        except:
            pass


# ==============================================================================
# GRAPH API PROVIDER (Future)
# ==============================================================================

class GraphAPIProvider(DataProvider):
    """
    Official Facebook Graph API provider.
    
    Note: Only works for profiles/pages you have explicit access to.
    Cannot fetch arbitrary public profiles via API.
    """
    
    def __init__(self, config: FacebookConfig):
        super().__init__(config)
        self.base_url = f'https://graph.facebook.com/{config.api_version}'
        self._rate_limit = {
            'limit': 200,
            'remaining': 200,
            'reset_at': None
        }
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """
        Fetch profile via Graph API.
        
        WARNING: This only works if:
        1. Profile is a Page you manage
        2. You have appropriate permissions
        3. Profile has granted your app access
        
        For arbitrary seller profiles, this will likely fail.
        """
        try:
            self._throttle()
            
            url = f'{self.base_url}/{profile_id}'
            params = {
                'access_token': self.config.access_token,
                'fields': ','.join([
                    'id',
                    'name',
                    'location',
                    'created_time',
                    'picture',
                    'cover',
                    'about'
                ])
            }
            
            response = requests.get(url, params=params, timeout=10)
            self._update_rate_limits(response.headers)
            
            if response.status_code == 200:
                return self._map_graph_response(response.json())
            elif response.status_code == 403:
                logger.warning(f"No API access to profile {profile_id}")
            else:
                logger.error(f"API error {response.status_code}: {response.text}")
            
            return None
            
        except Exception as e:
            logger.error(f"Graph API failed for {profile_id}: {e}")
            return None
    
    def get_profiles_batch(self, profile_ids: List[str]) -> List[ProfileData]:
        """
        Fetch multiple profiles using Graph API batch request.
        
        More efficient than individual requests.
        """
        try:
            batch_requests = [
                {
                    'method': 'GET',
                    'relative_url': f'{profile_id}?fields=id,name,location,created_time,picture'
                }
                for profile_id in profile_ids
            ]
            
            url = f'{self.base_url}/'
            data = {
                'access_token': self.config.access_token,
                'batch': json.dumps(batch_requests)
            }
            
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                batch_results = response.json()
                profiles = []
                
                for result in batch_results:
                    if result.get('code') == 200:
                        body = json.loads(result['body'])
                        profile = self._map_graph_response(body)
                        if profile:
                            profiles.append(profile)
                
                return profiles
            
            return []
            
        except Exception as e:
            logger.error(f"Batch API request failed: {e}")
            return []
    
    def is_available(self) -> bool:
        """Verify API credentials are valid"""
        try:
            url = f'{self.base_url}/me'
            params = {'access_token': self.config.access_token}
            response = requests.get(url, params=params, timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def get_rate_limit_info(self) -> RateLimitInfo:
        """Return current Graph API rate limits"""
        return RateLimitInfo(
            provider=DataSource.GRAPH_API.value,
            limit_total=self._rate_limit['limit'],
            limit_remaining=self._rate_limit['remaining'],
            reset_at=self._rate_limit['reset_at']
        )
    
    def _map_graph_response(self, data: Dict) -> ProfileData:
        """Map Graph API response to ProfileData"""
        return ProfileData(
            fb_id=data.get('id'),
            fb_name=data.get('name'),
            fb_location_name=data.get('location', {}).get('name') if data.get('location') else None,
            fb_join_date=data.get('created_time'),
            fb_picture_url=data.get('picture', {}).get('data', {}).get('url'),
            fb_cover_url=data.get('cover', {}).get('source'),
            source=DataSource.GRAPH_API.value,
            api_accessible=True
        )
    
    def _update_rate_limits(self, headers: Dict):
        """Update rate limit info from response headers"""
        if 'X-App-Usage' in headers:
            usage = json.loads(headers['X-App-Usage'])
            self._rate_limit['remaining'] = 100 - usage.get('call_count', 0)
        
        if 'X-Business-Use-Case-Usage' in headers:
            usage = json.loads(headers['X-Business-Use-Case-Usage'])
            # Parse business usage limits


# ==============================================================================
# HYBRID PROVIDER (Intelligent Routing)
# ==============================================================================

class HybridProvider(DataProvider):
    """
    Intelligent provider that routes between API and scraper.

    Strategy:
    1. Try API first (if available and likely to work)
    2. Fall back to scraper if API fails
    3. Cache results to minimize requests
    4. Track which profiles are API-accessible
    """

    MAX_CACHE_SIZE = 1000  # Prevent unbounded memory growth

    def __init__(
        self,
        config: FacebookConfig,
        scraper: ScraperProvider,
        api: Optional[GraphAPIProvider] = None
    ):
        super().__init__(config)
        self.scraper = scraper
        self.api = api
        self.cache = OrderedDict()  # LRU-capable cache
        self.api_accessible_profiles = set()
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Smart profile fetching with fallback"""
        
        # Check cache first
        if self.config.cache_enabled:
            cached = self._get_from_cache(profile_id)
            if cached:
                return cached
        
        # Try API if available and profile known to be accessible
        if self.api and self.api.is_available():
            if profile_id in self.api_accessible_profiles:
                profile = self._try_api(profile_id)
                if profile:
                    return profile
        
        # Fall back to scraper
        if self.scraper.is_available():
            profile = self.scraper.get_profile(profile_id)
            if profile and self.config.cache_enabled:
                self._cache_profile(profile_id, profile)
            return profile
        
        return None
    
    def get_profiles_batch(self, profile_ids: List[str]) -> List[ProfileData]:
        """Batch fetch with intelligent routing"""
        results = []
        
        # Separate known API-accessible from unknown
        api_ids = [pid for pid in profile_ids if pid in self.api_accessible_profiles]
        scraper_ids = [pid for pid in profile_ids if pid not in self.api_accessible_profiles]
        
        # Try batch API request for known accessible profiles
        if api_ids and self.api:
            api_results = self.api.get_profiles_batch(api_ids)
            results.extend(api_results)
        
        # Use scraper for rest
        scraper_results = self.scraper.get_profiles_batch(scraper_ids)
        results.extend(scraper_results)
        
        # Cache all results
        if self.config.cache_enabled:
            for profile in results:
                self._cache_profile(profile.fb_id, profile)
        
        return results
    
    def is_available(self) -> bool:
        """Available if any provider works"""
        return self.scraper.is_available() or (self.api and self.api.is_available())
    
    def get_rate_limit_info(self) -> RateLimitInfo:
        """Combined rate limit info"""
        if self.api and self.api.is_available():
            return self.api.get_rate_limit_info()
        return self.scraper.get_rate_limit_info()
    
    def _try_api(self, profile_id: str) -> Optional[ProfileData]:
        """Try API, handle failures gracefully"""
        try:
            profile = self.api.get_profile(profile_id)
            if profile:
                self.api_accessible_profiles.add(profile_id)
                if self.config.cache_enabled:
                    self._cache_profile(profile_id, profile)
                return profile
        except Exception as e:
            logger.debug(f"API failed for {profile_id}, will use scraper: {e}")
        
        return None
    
    def _get_from_cache(self, profile_id: str) -> Optional[ProfileData]:
        """Retrieve from cache if not expired (LRU pattern)"""
        if profile_id not in self.cache:
            return None

        cached_data, cached_at = self.cache[profile_id]
        age = (datetime.now() - cached_at).total_seconds()

        if age < self.config.cache_ttl:
            # Move to end (most recently used) for LRU
            self.cache.move_to_end(profile_id)
            logger.debug(f"Cache hit for {profile_id} (age: {age:.0f}s)")
            return cached_data
        else:
            # Expired - remove
            del self.cache[profile_id]
            return None
    
    def _cache_profile(self, profile_id: str, profile: ProfileData):
        """Store in cache with LRU eviction"""
        # Remove oldest entries if at capacity
        while len(self.cache) >= self.MAX_CACHE_SIZE:
            self.cache.popitem(last=False)  # Remove oldest (FIFO/LRU)

        self.cache[profile_id] = (profile, datetime.now())


# ==============================================================================
# FACTORY FUNCTION
# ==============================================================================

def get_provider(config: FacebookConfig) -> DataProvider:
    """
    Create appropriate data provider based on configuration.
    
    Args:
        config: FacebookConfig with provider settings
        
    Returns:
        Configured DataProvider instance
        
    Example:
        config = FacebookConfig.from_env()
        provider = get_provider(config)
        profile = provider.get_profile('123456789')
    """
    errors = config.validate()
    if errors:
        raise ValueError(f"Invalid configuration: {', '.join(errors)}")
    
    if config.provider_type == 'api':
        if not config.has_api_credentials():
            raise ValueError("API provider requires credentials")
        return GraphAPIProvider(config)
    
    elif config.provider_type == 'hybrid':
        scraper = ScraperProvider(config)
        api = GraphAPIProvider(config) if config.has_api_credentials() else None
        return HybridProvider(config, scraper, api)
    
    else:  # Default to scraper
        return ScraperProvider(config)


# ==============================================================================
# EXAMPLE USAGE
# ==============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Load config from environment
    config = FacebookConfig.from_env()
    
    print("Facebook Data Provider Demo")
    print("=" * 60)
    print(f"Provider type: {config.provider_type}")
    print(f"Browser: {config.browser_type}")
    print(f"API credentials: {config.has_api_credentials()}")
    print()
    
    # Create provider
    provider = get_provider(config)
    
    # Check availability
    if provider.is_available():
        print("✅ Provider is available")
        
        # Show rate limits
        rate_info = provider.get_rate_limit_info()
        print(f"Rate limit: {rate_info.provider}")
        if rate_info.limit_total:
            print(f"  Remaining: {rate_info.limit_remaining}/{rate_info.limit_total}")
        else:
            print(f"  Recommended delay: {rate_info.recommended_delay}s")
        
        # Example: Fetch a profile
        # profile = provider.get_profile('61550649184857')
        # if profile:
        #     print(f"\nProfile: {profile.fb_name}")
        #     print(f"Source: {profile.source}")
    else:
        print("❌ Provider is not available")
