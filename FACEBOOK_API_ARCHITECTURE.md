# Facebook API Integration Architecture - Future-Proofing Plan

**Current State:** Web scraping with Selenium/Playwright  
**Future State:** Official Facebook Graph API & Messenger Platform  
**Migration Path:** Hybrid approach with graceful transition

---

## CRITICAL UNDERSTANDING

### What Facebook APIs Actually Provide:

**✅ Available via Official API:**
- Marketplace listings YOU own/manage (Content Library API)
- Messenger conversations for YOUR Pages
- Commerce Manager data (your products/orders)
- Page management and insights

**❌ NOT Available via Official API:**
- Public Marketplace listings from other sellers
- Arbitrary user profiles
- Other sellers' data
- Public Marketplace search

### Current Project Status:

**What we're doing:** Scraping public Marketplace seller profiles  
**Why it works:** Using browser automation (Selenium/Playwright)  
**API alternative:** NONE - Facebook doesn't provide this data via API

---

## FUTURE-PROOFING STRATEGY

### Phase 1: Architecture Preparation (Now)

**Goal:** Structure code to support both scraping AND API when available

**Key Principles:**
1. **Data Layer Abstraction** - Separate data acquisition from storage
2. **Provider Pattern** - Multiple data sources (scraper, API, hybrid)
3. **Schema Compatibility** - Database schema matches Graph API structure
4. **Token Management** - Prepare for OAuth/API authentication
5. **Rate Limiting** - Built-in throttling for API compliance

### Phase 2: Hybrid Implementation (6-12 months)

**Scenario:** User gains approved API access

**Capabilities:**
- API for owned listings/commerce data
- Scraper for public seller profiles (unchanged)
- Unified interface for both sources

### Phase 3: Full API Migration (If Facebook Opens Access)

**Scenario:** Facebook provides public Marketplace API

**Migration:** Switch data source without code rewrite

---

## ARCHITECTURE DESIGN

### 1. Data Provider Interface

**Purpose:** Abstract data acquisition regardless of source

```python
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class ProfileData:
    """Unified profile data structure"""
    fb_id: str
    fb_name: Optional[str]
    fb_location_name: Optional[str]
    fb_join_date: Optional[str]
    fb_picture_url: Optional[str]
    fb_active_listings_count: Optional[int]
    fb_response_rate: Optional[str]
    fb_seller_badges: Optional[List[str]]
    source: str  # 'scraper', 'api', 'cache'
    acquired_at: str

class DataProvider(ABC):
    """Abstract base for all data providers"""
    
    @abstractmethod
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Fetch single profile"""
        pass
    
    @abstractmethod
    def get_profiles_batch(self, profile_ids: List[str]) -> List[ProfileData]:
        """Fetch multiple profiles"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available"""
        pass
    
    @abstractmethod
    def get_rate_limit_info(self) -> Dict:
        """Return current rate limit status"""
        pass
```

### 2. Scraper Provider (Current)

```python
class ScraperProvider(DataProvider):
    """Browser-based scraping provider"""
    
    def __init__(self, browser_type='firefox'):
        self.browser_type = browser_type
        self.driver = None
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Fetch profile via Selenium/Playwright"""
        # Current selenium_enricher logic
        profile_data = self._scrape_profile(profile_id)
        return ProfileData(
            **profile_data,
            source='scraper',
            acquired_at=datetime.now().isoformat()
        )
    
    def is_available(self) -> bool:
        """Check if browser is ready"""
        return self._check_browser_connection()
    
    def get_rate_limit_info(self) -> Dict:
        """Scraper has no official limits, but respect timing"""
        return {
            'provider': 'scraper',
            'limit': None,
            'remaining': None,
            'recommended_delay': 2.0  # seconds between requests
        }
```

### 3. Graph API Provider (Future)

```python
class GraphAPIProvider(DataProvider):
    """Official Facebook Graph API provider"""
    
    def __init__(self, access_token: str, api_version='v20.0'):
        self.access_token = access_token
        self.api_version = api_version
        self.base_url = f'https://graph.facebook.com/{api_version}'
        self._rate_limit = {
            'limit': 200,
            'remaining': 200,
            'reset_at': None
        }
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Fetch profile via Graph API"""
        # Only works for profiles/pages you have access to
        url = f'{self.base_url}/{profile_id}'
        params = {
            'access_token': self.access_token,
            'fields': 'id,name,location,created_time,picture,page_metadata'
        }
        
        response = requests.get(url, params=params)
        self._update_rate_limits(response.headers)
        
        if response.status_code == 200:
            data = response.json()
            return self._map_to_profile_data(data)
        
        return None
    
    def is_available(self) -> bool:
        """Check if API credentials are valid"""
        return self._verify_access_token()
    
    def get_rate_limit_info(self) -> Dict:
        """Return Graph API rate limit info"""
        return {
            'provider': 'graph_api',
            **self._rate_limit
        }
```

### 4. Content Library API Provider (For Marketplace)

```python
class ContentLibraryProvider(DataProvider):
    """Meta Content Library API for approved access"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = 'https://graph.facebook.com/v20.0'
    
    def search_marketplace_listings(
        self,
        query: str,
        location: Optional[str] = None,
        limit: int = 25
    ) -> List[Dict]:
        """
        Search marketplace listings (requires approved access)
        
        Note: This only works if you have Content Library API access
        approved by Meta for research/academic purposes.
        """
        url = f'{self.base_url}/facebook/marketplace-listings/preview'
        params = {
            'access_token': self.access_token,
            'query': query,
            'limit': limit,
            'fields': 'listing_id,title,price,location,seller_id'
        }
        
        if location:
            params['location'] = location
        
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            return response.json().get('data', [])
        
        return []
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Content Library API doesn't provide profile data directly"""
        # Would need to combine with Graph API
        return None
```

### 5. Hybrid Provider (Intelligent Routing)

```python
class HybridProvider(DataProvider):
    """
    Intelligent routing between scraper and API
    
    Strategy:
    1. Try API first (faster, official)
    2. Fall back to scraper if API unavailable
    3. Cache results to minimize requests
    """
    
    def __init__(
        self,
        scraper: ScraperProvider,
        api: Optional[GraphAPIProvider] = None,
        cache_ttl: int = 3600
    ):
        self.scraper = scraper
        self.api = api
        self.cache = {}
        self.cache_ttl = cache_ttl
    
    def get_profile(self, profile_id: str) -> Optional[ProfileData]:
        """Smart profile fetching with fallback"""
        
        # Check cache first
        cached = self._get_from_cache(profile_id)
        if cached:
            return cached
        
        # Try API if available
        if self.api and self.api.is_available():
            try:
                data = self.api.get_profile(profile_id)
                if data:
                    self._cache_profile(profile_id, data)
                    return data
            except Exception as e:
                logger.warning(f"API failed, falling back to scraper: {e}")
        
        # Fall back to scraper
        data = self.scraper.get_profile(profile_id)
        if data:
            self._cache_profile(profile_id, data)
        
        return data
    
    def is_available(self) -> bool:
        """Available if either provider works"""
        return self.scraper.is_available() or (
            self.api and self.api.is_available()
        )
```

---

## DATABASE SCHEMA (API-Compatible)

### Current Schema Enhancement:

```sql
-- Add API-specific fields
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS api_accessible BOOLEAN DEFAULT FALSE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS api_last_sync TIMESTAMP;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS data_source VARCHAR(20); -- 'scraper' or 'api'

-- Add API tokens table
CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_type VARCHAR(50), -- 'page_access', 'user_access', 'app_access'
    access_token TEXT NOT NULL,
    token_expires_at TIMESTAMP,
    scopes TEXT, -- JSON array of permissions
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);

-- Add rate limiting tracking
CREATE TABLE IF NOT EXISTS api_rate_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider VARCHAR(50), -- 'graph_api', 'content_library'
    endpoint VARCHAR(200),
    limit_total INTEGER,
    limit_remaining INTEGER,
    reset_at TIMESTAMP,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## CONFIGURATION MANAGEMENT

### Environment Variables:

```bash
# Current (Scraper)
BROWSER_TYPE=firefox
SCRAPER_ENABLED=true

# Future (API)
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_ACCESS_TOKEN=
FACEBOOK_API_VERSION=v20.0

# Hybrid
DATA_PROVIDER=hybrid  # 'scraper', 'api', 'hybrid'
API_FALLBACK_TO_SCRAPER=true
CACHE_TTL_SECONDS=3600
```

### Config Class:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class FacebookConfig:
    """Centralized Facebook integration config"""
    
    # Scraper settings
    browser_type: str = 'firefox'
    scraper_enabled: bool = True
    
    # API settings (optional)
    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    access_token: Optional[str] = None
    api_version: str = 'v20.0'
    
    # Hybrid settings
    provider_type: str = 'scraper'  # 'scraper', 'api', 'hybrid'
    api_fallback: bool = True
    cache_ttl: int = 3600
    
    @classmethod
    def from_env(cls):
        """Load config from environment"""
        return cls(
            browser_type=os.getenv('BROWSER_TYPE', 'firefox'),
            scraper_enabled=os.getenv('SCRAPER_ENABLED', 'true').lower() == 'true',
            app_id=os.getenv('FACEBOOK_APP_ID'),
            app_secret=os.getenv('FACEBOOK_APP_SECRET'),
            access_token=os.getenv('FACEBOOK_ACCESS_TOKEN'),
            api_version=os.getenv('FACEBOOK_API_VERSION', 'v20.0'),
            provider_type=os.getenv('DATA_PROVIDER', 'scraper'),
            api_fallback=os.getenv('API_FALLBACK_TO_SCRAPER', 'true').lower() == 'true',
            cache_ttl=int(os.getenv('CACHE_TTL_SECONDS', '3600'))
        )
    
    def has_api_credentials(self) -> bool:
        """Check if API credentials are configured"""
        return bool(self.app_id and self.app_secret and self.access_token)
```

---

## INTEGRATION POINTS

### Dashboard Updates:

```python
# In dashboard_integrated.py

from data_providers import (
    ScraperProvider,
    GraphAPIProvider,
    HybridProvider,
    FacebookConfig
)

# Initialize provider based on config
config = FacebookConfig.from_env()

if config.provider_type == 'api' and config.has_api_credentials():
    provider = GraphAPIProvider(
        access_token=config.access_token,
        api_version=config.api_version
    )
elif config.provider_type == 'hybrid':
    scraper = ScraperProvider(browser_type=config.browser_type)
    api = GraphAPIProvider(config.access_token) if config.has_api_credentials() else None
    provider = HybridProvider(scraper, api, cache_ttl=config.cache_ttl)
else:
    # Default to scraper (current behavior)
    provider = ScraperProvider(browser_type=config.browser_type)

# Use provider uniformly
def enrich_profile(fb_id: str):
    """Enrichment now provider-agnostic"""
    profile_data = provider.get_profile(fb_id)
    if profile_data:
        save_to_database(profile_data)
        return True
    return False
```

---

## MIGRATION CHECKLIST

### Immediate (Now):

- [ ] Implement DataProvider interface
- [ ] Create ScraperProvider wrapper around existing code
- [ ] Add database schema enhancements
- [ ] Add configuration management
- [ ] Test with scraper provider only

### Short Term (1-3 months):

- [ ] Implement GraphAPIProvider (stub for testing)
- [ ] Add token management UI
- [ ] Implement rate limit tracking
- [ ] Add provider status indicators to dashboard
- [ ] Document API prerequisites

### Long Term (6-12 months):

- [ ] Apply for Content Library API access (if applicable)
- [ ] Implement HybridProvider with intelligent routing
- [ ] Add API-specific analytics
- [ ] Performance comparison (API vs scraper)
- [ ] Gradual migration tooling

---

## BENEFITS OF THIS APPROACH

### 1. **Zero Disruption**
Current scraping continues to work exactly as is

### 2. **Future-Ready**
Drop in GraphAPIProvider when credentials available

### 3. **Flexible**
Support multiple data sources simultaneously

### 4. **Testable**
Each provider can be tested independently

### 5. **Maintainable**
Clear separation of concerns

### 6. **Compliant**
Respects Facebook's ToS and rate limits

---

## RISKS & MITIGATION

### Risk 1: Facebook Never Opens Public Marketplace API

**Mitigation:** ScraperProvider remains primary, architecture still valuable for:
- Owned listings via Content Library API
- Messenger integration
- Page management

### Risk 2: API Access Requires Business Verification

**Mitigation:** Architecture supports gradual adoption:
- Start with scraper
- Add API for owned content only
- Keep scraper for public data

### Risk 3: Rate Limits Too Restrictive

**Mitigation:** HybridProvider uses:
- Intelligent caching
- Request batching
- Scraper fallback

---

## NEXT STEPS

1. **Review this architecture** - Ensure it meets requirements
2. **Implement Phase 1** - DataProvider interface + ScraperProvider
3. **Add GraphAPIProvider stub** - Prepare for future API integration
4. **Update documentation** - Architecture diagrams and API readiness
5. **Create migration guide** - For when API access is obtained

This architecture future-proofs the project while maintaining current functionality.
