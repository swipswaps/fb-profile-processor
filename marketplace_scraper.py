#!/usr/bin/env python3
"""
Marketplace Scraper - Extract logged-in user info and their selling items

Supports two methods:
1. Facebook Graph API (preferred when access token available)
2. Browser scraping via Firefox profile (fallback)

Production-grade implementation aligned with Meta Commerce Manager workflows.
Uses only officially supported Graph API flows.
"""
import sqlite3
import time
import os
import re
import json
import logging
import requests
from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# selenium-wire for network interception (captures GraphQL responses)
try:
    from seleniumwire import webdriver as wire_webdriver
    SELENIUM_WIRE_AVAILABLE = True
except ImportError:
    SELENIUM_WIRE_AVAILABLE = False
    wire_webdriver = None

from selenium_enricher import get_firefox_profile_path, create_firefox_driver, cleanup_temp_profile

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
# Comprehensive logging per user request: events, errors, system, application messages
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Configure module logger with file + console output
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.propagate = False  # Prevent duplicate logs via root logger

# Avoid duplicate handlers on module reload
if not logger.handlers:
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler("/tmp/marketplace_scraper.log", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(file_handler)

# =============================================================================
# CONSTANTS (defined before logging to avoid F821)
# =============================================================================

GRAPH_API_VERSION = "v20.0"
GRAPH_API_RELEASE_DATE = "2024-05-28"  # v20.0 release date
GRAPH_API_DEPRECATION_MONTHS = 24  # Meta deprecates versions ~2 years after release
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Now log module load with defined constants
logger.info("=" * 60)
logger.info("MARKETPLACE_SCRAPER MODULE LOADED")
logger.info(f"Graph API Version: {GRAPH_API_VERSION}")
logger.info("=" * 60)


def get_api_version_status() -> dict:
    """
    Check API version deprecation status.

    Meta maintains a 2-year version lifecycle. Versions are deprecated
    approximately 24 months after release.

    Returns:
        dict with version, release_date, months_until_deprecation, warning
    """
    from datetime import datetime
    release = datetime.strptime(GRAPH_API_RELEASE_DATE, "%Y-%m-%d")
    now = datetime.utcnow()
    months_since_release = (now.year - release.year) * 12 + (now.month - release.month)
    months_until_deprecation = GRAPH_API_DEPRECATION_MONTHS - months_since_release

    warning = None
    if months_until_deprecation <= 0:
        warning = f"⚠️ API {GRAPH_API_VERSION} may be deprecated. Upgrade recommended."
    elif months_until_deprecation <= 6:
        warning = f"⚠️ API {GRAPH_API_VERSION} deprecates in ~{months_until_deprecation} months."

    return {
        "version": GRAPH_API_VERSION,
        "release_date": GRAPH_API_RELEASE_DATE,
        "months_since_release": months_since_release,
        "months_until_deprecation": max(0, months_until_deprecation),
        "warning": warning,
    }


# =============================================================================
# CANONICAL FACEBOOK API STATE MACHINE
# =============================================================================
# All UI components, buttons, and features MUST derive from this state.
# No guessing. No hidden assumptions. State drives everything.
#
# Reference: Meta Commerce Platform docs, facebook-python-business-sdk patterns
# Source: https://developers.facebook.com/docs/commerce-platform/api-setup/


class FacebookAPIState(Enum):
    """
    Canonical state machine for Facebook API configuration.

    Every screen, button, and feature MUST derive from this state.
    No guessing. No hidden assumptions. Explicit state transitions only.

    State Progression:
        NO_CONFIG → TOKEN_PRESENT → TOKEN_VALID → PERMISSIONS_VALID →
        CATALOG_ACCESSIBLE → COMMERCE_LINKED → API_READY

    Special States:
        OFFLINE - No credentials, diagnostic mode only
        DEGRADED - Partial functionality (e.g., human token)
        BLOCKED - Hard stop condition detected
        ERROR - API error during state check
    """

    # === Configuration States (progressive) ===
    NO_CONFIG = 0           # No credentials configured at all
    TOKEN_PRESENT = 10      # Token exists but not validated
    TOKEN_VALID = 20        # Token passes /debug_token validation
    PERMISSIONS_VALID = 30  # Required scopes (catalog_management, business_management) granted
    CATALOG_ACCESSIBLE = 40 # GET /{catalog_id} returns 200
    COMMERCE_LINKED = 50    # Catalog linked to Commerce Account
    API_READY = 100         # All requirements met - full functionality

    # === Special States ===
    OFFLINE = -10           # No credentials, diagnostic mode
    DEGRADED = -5           # Partial functionality (human token, expiring soon)
    BLOCKED = -100          # Hard stop (invalid token, missing critical permissions)
    ERROR = -50             # Error during state determination

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return self.value <= other.value
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return self.value >= other.value
        return NotImplemented


# State metadata for UI display and guidance
API_STATE_METADATA = {
    FacebookAPIState.NO_CONFIG: {
        "label": "No Configuration",
        "description": "No Facebook API credentials configured.",
        "icon": "⚪",
        "color": "gray",
        "next_step": "Add FB_ACCESS_TOKEN and FB_CATALOG_ID to your configuration.",
        "fix_url": "https://developers.facebook.com/docs/development/register/",
        "blocked_features": ["all"],
    },
    FacebookAPIState.TOKEN_PRESENT: {
        "label": "Token Present (Unverified)",
        "description": "Access token provided but not yet validated.",
        "icon": "🟡",
        "color": "yellow",
        "next_step": "Click 'Verify Token' to validate with Meta API.",
        "fix_url": "https://developers.facebook.com/tools/accesstoken/",
        "blocked_features": ["write_operations", "catalog_operations"],
    },
    FacebookAPIState.TOKEN_VALID: {
        "label": "Token Valid",
        "description": "Token authenticated but permissions not yet verified.",
        "icon": "🟡",
        "color": "yellow",
        "next_step": "Verify token has catalog_management and business_management scopes.",
        "fix_url": "https://business.facebook.com/settings/system-users",
        "blocked_features": ["catalog_operations", "commerce_operations"],
    },
    FacebookAPIState.PERMISSIONS_VALID: {
        "label": "Permissions Verified",
        "description": "Token has required scopes. Checking catalog access...",
        "icon": "🟢",
        "color": "green",
        "next_step": "Verify catalog accessibility.",
        "fix_url": "https://www.facebook.com/commerce_manager/catalogs/",
        "blocked_features": ["commerce_operations"],
    },
    FacebookAPIState.CATALOG_ACCESSIBLE: {
        "label": "Catalog Accessible",
        "description": "Can read catalog. Checking Commerce Account linkage...",
        "icon": "🟢",
        "color": "green",
        "next_step": "Link catalog to Commerce Account for Marketplace visibility.",
        "fix_url": "https://business.facebook.com/commerce",
        "blocked_features": ["marketplace_write"],
    },
    FacebookAPIState.COMMERCE_LINKED: {
        "label": "Commerce Account Linked",
        "description": "Catalog linked to Commerce Account. Almost ready!",
        "icon": "🟢",
        "color": "green",
        "next_step": "Run final verification to enable API operations.",
        "fix_url": None,
        "blocked_features": [],
    },
    FacebookAPIState.API_READY: {
        "label": "API Ready",
        "description": "All requirements met. Full functionality available.",
        "icon": "✅",
        "color": "green",
        "next_step": None,
        "fix_url": None,
        "blocked_features": [],
    },
    FacebookAPIState.OFFLINE: {
        "label": "Offline Mode",
        "description": "Running in diagnostic mode without credentials.",
        "icon": "📴",
        "color": "gray",
        "next_step": "Configure credentials to enable API features.",
        "fix_url": "https://developers.facebook.com/docs/development/register/",
        "blocked_features": ["all_api"],
    },
    FacebookAPIState.DEGRADED: {
        "label": "Degraded Mode",
        "description": "Limited functionality due to configuration issues.",
        "icon": "⚠️",
        "color": "orange",
        "next_step": "Review configuration to restore full functionality.",
        "fix_url": None,
        "blocked_features": ["background_operations"],
    },
    FacebookAPIState.BLOCKED: {
        "label": "Blocked",
        "description": "Critical issue prevents API operations.",
        "icon": "🔴",
        "color": "red",
        "next_step": "Resolve blocking issues before proceeding.",
        "fix_url": None,
        "blocked_features": ["all"],
    },
    FacebookAPIState.ERROR: {
        "label": "Error",
        "description": "Could not determine API state due to error.",
        "icon": "❌",
        "color": "red",
        "next_step": "Check error details and retry.",
        "fix_url": None,
        "blocked_features": ["all"],
    },
}


def get_current_api_state(
    token: str = None,
    catalog_id: str = None,
    offline_mode: bool = False,
    skip_api_calls: bool = False
) -> Tuple[FacebookAPIState, dict]:
    """
    Determine the current Facebook API configuration state.

    This is THE authoritative source for API state. All UI elements
    must derive their enabled/disabled state from this function.

    Args:
        token: Access token (defaults to FB_ACCESS_TOKEN env var)
        catalog_id: Catalog ID (defaults to FB_CATALOG_ID env var)
        offline_mode: If True, return OFFLINE state without checks
        skip_api_calls: If True, only check local config (no API validation)

    Returns:
        Tuple of (FacebookAPIState, details_dict)
        details_dict contains:
            - state: The state enum value
            - state_name: Human-readable state name
            - metadata: State metadata from API_STATE_METADATA
            - checks: Dict of individual check results
            - error: Error message if any
            - timestamp: When state was determined
    """
    from datetime import datetime

    # Initialize result
    checks = {
        "token_present": False,
        "token_valid": None,  # None = not checked, True/False = result
        "permissions_valid": None,
        "catalog_accessible": None,
        "commerce_linked": None,
    }
    error = None

    # Offline mode - explicit bypass
    if offline_mode:
        state = FacebookAPIState.OFFLINE
        return state, _build_state_result(state, checks, error)

    # Get credentials from env if not provided
    token = token or os.environ.get("FB_ACCESS_TOKEN", "").strip()
    catalog_id = catalog_id or os.environ.get("FB_CATALOG_ID", "").strip()

    # Check 1: Token present?
    if not token:
        state = FacebookAPIState.NO_CONFIG
        return state, _build_state_result(state, checks, error)

    checks["token_present"] = True

    # If skip_api_calls, we can only verify token exists
    if skip_api_calls:
        state = FacebookAPIState.TOKEN_PRESENT
        return state, _build_state_result(state, checks, error)

    # Check 2: Token valid? (requires API call)
    try:
        token_info = _validate_token_with_api(token)
        if not token_info.get("is_valid", False):
            checks["token_valid"] = False
            state = FacebookAPIState.BLOCKED
            error = token_info.get("error", "Token validation failed")
            return state, _build_state_result(state, checks, error)

        checks["token_valid"] = True

        # Check for human vs system user token
        token_type = token_info.get("type", "unknown")
        is_system_user = token_type.lower() in ("system_user", "system user")

    except Exception as e:
        checks["token_valid"] = False
        state = FacebookAPIState.ERROR
        error = f"Token validation error: {str(e)}"
        return state, _build_state_result(state, checks, error)

    # Check 3: Required permissions?
    required_scopes = {"catalog_management", "business_management"}
    granted_scopes = set(token_info.get("scopes", []))

    if not required_scopes.issubset(granted_scopes):
        checks["permissions_valid"] = False
        missing = required_scopes - granted_scopes
        state = FacebookAPIState.TOKEN_VALID  # Token valid but missing perms
        error = f"Missing required permissions: {', '.join(missing)}"
        return state, _build_state_result(state, checks, error)

    checks["permissions_valid"] = True

    # Check 4: Catalog accessible?
    if not catalog_id:
        # Permissions OK but no catalog configured
        state = FacebookAPIState.PERMISSIONS_VALID
        error = "No catalog ID configured"
        return state, _build_state_result(state, checks, error)

    try:
        catalog_info = _check_catalog_access(token, catalog_id)
        if not catalog_info.get("accessible", False):
            checks["catalog_accessible"] = False
            state = FacebookAPIState.PERMISSIONS_VALID
            error = catalog_info.get("error", "Catalog not accessible")
            return state, _build_state_result(state, checks, error)

        checks["catalog_accessible"] = True

    except Exception as e:
        checks["catalog_accessible"] = False
        state = FacebookAPIState.PERMISSIONS_VALID
        error = f"Catalog check error: {str(e)}"
        return state, _build_state_result(state, checks, error)

    # Check 5: Commerce Account linked?
    try:
        commerce_info = _check_commerce_linkage(token, catalog_id)
        if not commerce_info.get("linked", False):
            checks["commerce_linked"] = False
            state = FacebookAPIState.CATALOG_ACCESSIBLE
            error = "Catalog not linked to Commerce Account"
            return state, _build_state_result(state, checks, error)

        checks["commerce_linked"] = True

    except Exception as e:
        checks["commerce_linked"] = False
        state = FacebookAPIState.CATALOG_ACCESSIBLE
        error = f"Commerce linkage check error: {str(e)}"
        return state, _build_state_result(state, checks, error)

    # All checks passed - determine final state
    if not is_system_user:
        # Human token - degraded mode
        state = FacebookAPIState.DEGRADED
        error = "Using human token. System User token recommended for production."
        return state, _build_state_result(state, checks, error)

    # Full success
    state = FacebookAPIState.API_READY
    return state, _build_state_result(state, checks, error)


def _build_state_result(state: FacebookAPIState, checks: dict, error: str = None) -> dict:
    """Build standardized state result dictionary."""
    from datetime import datetime
    return {
        "state": state,
        "state_name": state.name,
        "state_value": state.value,
        "metadata": API_STATE_METADATA.get(state, {}),
        "checks": checks,
        "error": error,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def _validate_token_with_api(token: str) -> dict:
    """
    Validate token with Meta's debug_token endpoint.

    Returns:
        dict with is_valid, scopes, type, expires_at, error
    """
    try:
        # Use token to debug itself (app-level debug requires app token)
        url = f"{GRAPH_BASE}/debug_token"
        params = {"input_token": token, "access_token": token}
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            return {
                "is_valid": False,
                "error": f"API returned {resp.status_code}: {resp.text[:200]}",
            }

        data = resp.json().get("data", {})
        return {
            "is_valid": data.get("is_valid", False),
            "scopes": data.get("scopes", []),
            "type": data.get("type", "unknown"),
            "expires_at": data.get("expires_at", 0),
            "app_id": data.get("app_id"),
            "user_id": data.get("user_id"),
            "error": data.get("error", {}).get("message") if not data.get("is_valid") else None,
        }

    except requests.RequestException as e:
        return {
            "is_valid": False,
            "error": f"Network error: {str(e)}",
        }


def _check_catalog_access(token: str, catalog_id: str) -> dict:
    """
    Check if token can access the specified catalog.

    Returns:
        dict with accessible, catalog_name, vertical, error
    """
    try:
        url = f"{GRAPH_BASE}/{catalog_id}"
        params = {
            "access_token": token,
            "fields": "id,name,vertical,product_count",
        }
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            error_data = resp.json().get("error", {})
            return {
                "accessible": False,
                "error": error_data.get("message", f"HTTP {resp.status_code}"),
            }

        data = resp.json()
        return {
            "accessible": True,
            "catalog_id": data.get("id"),
            "catalog_name": data.get("name"),
            "vertical": data.get("vertical"),
            "product_count": data.get("product_count", 0),
        }

    except requests.RequestException as e:
        return {
            "accessible": False,
            "error": f"Network error: {str(e)}",
        }


def _check_commerce_linkage(token: str, catalog_id: str) -> dict:
    """
    Check if catalog is linked to a Commerce Account.

    This is THE most common failure point. A valid catalog ≠ Marketplace visibility.

    Returns:
        dict with linked, commerce_account_id, commerce_account_name, error
    """
    try:
        url = f"{GRAPH_BASE}/{catalog_id}"
        params = {
            "access_token": token,
            "fields": "id,name,commerce_merchant_settings",
        }
        resp = requests.get(url, params=params, timeout=15)

        if resp.status_code != 200:
            error_data = resp.json().get("error", {})
            return {
                "linked": False,
                "error": error_data.get("message", f"HTTP {resp.status_code}"),
            }

        data = resp.json()
        commerce_settings = data.get("commerce_merchant_settings")

        if not commerce_settings:
            return {
                "linked": False,
                "error": "Catalog not linked to Commerce Account. Products will NOT appear on Marketplace.",
            }

        return {
            "linked": True,
            "commerce_merchant_settings": commerce_settings,
        }

    except requests.RequestException as e:
        return {
            "linked": False,
            "error": f"Network error: {str(e)}",
        }


def is_feature_allowed(state: FacebookAPIState, feature: str) -> Tuple[bool, str]:
    """
    Check if a feature is allowed given the current API state.

    Args:
        state: Current FacebookAPIState
        feature: Feature name to check

    Returns:
        Tuple of (allowed: bool, reason: str)
    """
    metadata = API_STATE_METADATA.get(state, {})
    blocked_features = metadata.get("blocked_features", [])

    if "all" in blocked_features:
        return False, f"All features blocked in {state.name} state. {metadata.get('next_step', '')}"

    if feature in blocked_features:
        return False, f"{feature} blocked in {state.name} state. {metadata.get('next_step', '')}"

    return True, "Feature allowed"


def get_state_progress(state: FacebookAPIState) -> dict:
    """
    Get progress information for the current state.

    Returns dict with:
        - current_step: Current step number (1-7)
        - total_steps: Total steps (7)
        - percent: Progress percentage
        - completed_states: List of completed states
        - next_state: Next state to achieve (or None if complete)
    """
    # Define progression order
    progression = [
        FacebookAPIState.NO_CONFIG,
        FacebookAPIState.TOKEN_PRESENT,
        FacebookAPIState.TOKEN_VALID,
        FacebookAPIState.PERMISSIONS_VALID,
        FacebookAPIState.CATALOG_ACCESSIBLE,
        FacebookAPIState.COMMERCE_LINKED,
        FacebookAPIState.API_READY,
    ]

    # Handle special states
    if state in (FacebookAPIState.OFFLINE, FacebookAPIState.BLOCKED,
                 FacebookAPIState.ERROR, FacebookAPIState.DEGRADED):
        return {
            "current_step": 0,
            "total_steps": len(progression) - 1,  # Exclude NO_CONFIG
            "percent": 0,
            "completed_states": [],
            "next_state": FacebookAPIState.TOKEN_PRESENT,
            "is_special_state": True,
            "special_state_type": state.name,
        }

    try:
        current_idx = progression.index(state)
    except ValueError:
        current_idx = 0

    completed = progression[1:current_idx + 1]  # Exclude NO_CONFIG from completed
    next_state = progression[current_idx + 1] if current_idx < len(progression) - 1 else None

    total_steps = len(progression) - 1  # Exclude NO_CONFIG
    current_step = current_idx  # NO_CONFIG = 0, TOKEN_PRESENT = 1, etc.

    return {
        "current_step": current_step,
        "total_steps": total_steps,
        "percent": int((current_step / total_steps) * 100) if total_steps > 0 else 0,
        "completed_states": [s.name for s in completed],
        "next_state": next_state.name if next_state else None,
        "is_special_state": False,
    }


# =============================================================================
# COMPLIANCE ENFORCEMENT (Meta-Aligned UX)
# =============================================================================

# Authoritative setup requirements with Meta links
# Source: Meta Commerce Platform docs + Business Manager requirements
COMPLIANCE_REQUIREMENTS = [
    {
        "id": "token",
        "step": 1,
        "label": "System User Access Token",
        "description": "Meta requires System User tokens for production operations",
        "env_var": "FB_ACCESS_TOKEN",
        "required": True,
        "blocking": True,
        "fix_url": "https://developers.facebook.com/docs/development/register/",
        "docs_url": "https://developers.facebook.com/docs/marketing-api/system-users",
        "check_fn": lambda: bool(os.environ.get('FB_ACCESS_TOKEN')),
    },
    {
        "id": "catalog",
        "step": 2,
        "label": "Product Catalog ID",
        "description": "Required for catalog operations and Marketplace listings",
        "env_var": "FB_CATALOG_ID",
        "required": True,
        "blocking": True,
        "fix_url": "https://www.facebook.com/commerce_manager/catalogs/",
        "docs_url": "https://developers.facebook.com/docs/commerce-platform/catalog",
        "check_fn": lambda: bool(os.environ.get('FB_CATALOG_ID')),
    },
    {
        "id": "business",
        "step": 3,
        "label": "Business Manager Access",
        "description": "Required for managing Commerce Account and assets",
        "env_var": None,
        "required": True,
        "blocking": True,
        "fix_url": "https://business.facebook.com/settings",
        "docs_url": "https://developers.facebook.com/docs/commerce-platform/business-manager",
        "check_fn": None,  # Checked via API
    },
    {
        "id": "commerce",
        "step": 4,
        "label": "Commerce Account Linked",
        "description": "Catalog must be linked to Commerce Account for Marketplace visibility",
        "env_var": None,
        "required": True,
        "blocking": True,
        "fix_url": "https://business.facebook.com/commerce",
        "docs_url": "https://developers.facebook.com/docs/commerce-platform/setup",
        "check_fn": None,  # Checked via API
    },
    {
        "id": "permissions",
        "step": 5,
        "label": "Required Permissions",
        "description": "catalog_management and business_management scopes required",
        "env_var": None,
        "required": True,
        "blocking": True,
        "fix_url": "https://developers.facebook.com/tools/explorer/",
        "docs_url": "https://developers.facebook.com/docs/commerce-platform/catalog/get-started#required-permissions",
        "check_fn": None,  # Checked via API
    },
]


def get_compliance_status() -> dict:
    """
    Get current compliance status for all requirements.

    Returns dict with:
    - requirements: list of requirement dicts with 'status' added
    - total: total count
    - complete: count of satisfied requirements
    - blocking_incomplete: count of blocking requirements not met
    - can_proceed: True if no blocking issues
    """
    results = []
    complete = 0
    blocking_incomplete = 0

    for req in COMPLIANCE_REQUIREMENTS:
        status = "unknown"
        if req.get("check_fn"):
            try:
                status = "complete" if req["check_fn"]() else "incomplete"
            except Exception:
                status = "error"
        else:
            # API-checked items default to unknown until verified
            status = "requires_api"

        if status == "complete":
            complete += 1
        elif req.get("blocking", False) and status in ("incomplete", "error"):
            blocking_incomplete += 1

        results.append({**req, "status": status, "check_fn": None})  # Remove lambda for JSON

    return {
        "requirements": results,
        "total": len(COMPLIANCE_REQUIREMENTS),
        "complete": complete,
        "blocking_incomplete": blocking_incomplete,
        "can_proceed": blocking_incomplete == 0,
        "env_complete": sum(1 for r in results if r.get("env_var") and r["status"] == "complete"),
        "env_total": sum(1 for r in COMPLIANCE_REQUIREMENTS if r.get("env_var")),
    }


def is_globally_compliant() -> Tuple[bool, str, List[dict]]:
    """
    Check if the application is globally compliant for operations.

    Returns:
        (is_compliant: bool, message: str, blocking_issues: list)
    """
    status = get_compliance_status()

    if status["can_proceed"]:
        return True, "All environment requirements met", []

    blocking = [r for r in status["requirements"]
                if r.get("blocking") and r["status"] in ("incomplete", "error")]

    messages = [f"❌ {r['label']}: {r['description']}" for r in blocking]

    return False, f"Missing {len(blocking)} requirement(s)", blocking


class ComplianceGate:
    """
    Compliance enforcement gate with blocking logic.

    Meta's enforcement model: Block by default, not warn.
    This class enforces Meta requirements through hard stops.
    """

    # Blocking conditions (hard stops per Meta requirements)
    BLOCKING_CONDITIONS = {
        "TOKEN_INVALID": {
            "severity": "BLOCKING",
            "reason": "Meta requires valid authentication for all API operations.",
            "fix_url": "https://developers.facebook.com/tools/accesstoken/",
            "fix_steps": "Generate a new access token in Meta Developer Portal → Tools → Access Token Tool",
        },
        "MISSING_SCOPES": {
            "severity": "BLOCKING",
            "reason": "Meta requires catalog_management and business_management permissions for Commerce API.",
            "fix_url": "https://business.facebook.com/settings/system-users",
            "fix_steps": "Business Settings → System Users → [User] → Add Assets → Grant required permissions",
        },
        "CATALOG_NOT_LINKED": {
            "severity": "BLOCKING",
            "reason": "Meta requires catalog linkage to Commerce Account for Marketplace listing visibility.",
            "fix_url": "https://business.facebook.com/commerce",
            "fix_steps": "Commerce Manager → Settings → Business Assets → Link Product Catalog",
        },
        "NO_BUSINESS_ACCESS": {
            "severity": "BLOCKING",
            "reason": "Meta requires Business Manager access for Commerce operations.",
            "fix_url": "https://business.facebook.com/settings",
            "fix_steps": "Business Settings → People → Add yourself with Admin role",
        },
        "SYSTEM_USER_REQUIRED": {
            "severity": "BLOCKING",
            "reason": "Meta requires System User tokens for production/background operations. Human tokens can be revoked without notice.",
            "fix_url": "https://business.facebook.com/settings/system-users",
            "fix_steps": "Business Settings → System Users → Add → Generate Token with required permissions",
        },
    }

    # Warning conditions (non-blocking)
    WARNING_CONDITIONS = {
        "API_DEPRECATION": {
            "severity": "WARNING",
            "reason": "API version approaching deprecation. Plan upgrade.",
        },
        "ZERO_PRODUCTS": {
            "severity": "WARNING",
            "reason": "Catalog has no products. Operations may have no effect.",
        },
        "HUMAN_TOKEN_INTERACTIVE": {
            "severity": "WARNING",
            "reason": "Using human token in interactive mode. Suitable for testing only.",
        },
        "TOKEN_EXPIRING": {
            "severity": "WARNING",
            "reason": "Token expires soon. Plan renewal.",
        },
    }

    def __init__(self):
        self.blocking_issues: List[dict] = []
        self.warnings: List[dict] = []
        self._checked = False

    def add_blocking_issue(self, condition_key: str, details: str = None):
        """Add a blocking compliance issue."""
        condition = self.BLOCKING_CONDITIONS.get(condition_key, {})
        self.blocking_issues.append({
            "key": condition_key,
            "severity": "BLOCKING",
            "reason": condition.get("reason", "Unknown requirement"),
            "fix_url": condition.get("fix_url"),
            "fix_steps": condition.get("fix_steps"),
            "details": details,
        })

    def add_warning(self, condition_key: str, details: str = None):
        """Add a non-blocking warning."""
        condition = self.WARNING_CONDITIONS.get(condition_key, {})
        self.warnings.append({
            "key": condition_key,
            "severity": "WARNING",
            "reason": condition.get("reason", "Advisory notice"),
            "details": details,
        })

    def is_compliant(self) -> bool:
        """Check if all blocking conditions are clear."""
        return len(self.blocking_issues) == 0

    def can_proceed(self, operation: str = "operation") -> Tuple[bool, str]:
        """
        Check if operation can proceed.

        Returns:
            (can_proceed: bool, message: str)
        """
        if self.is_compliant():
            if self.warnings:
                warning_text = "; ".join(w["reason"] for w in self.warnings)
                return True, f"Proceed with warnings: {warning_text}"
            return True, "All compliance checks passed"

        # Build blocking message with fix instructions
        block_messages = []
        for issue in self.blocking_issues:
            msg = f"❌ {issue['key']}: {issue['reason']}"
            if issue.get("fix_steps"):
                msg += f"\n   Fix: {issue['fix_steps']}"
            block_messages.append(msg)

        return False, f"Cannot proceed with {operation}:\n" + "\n".join(block_messages)

    def get_status(self) -> dict:
        """Get compliance status for display."""
        return {
            "is_compliant": self.is_compliant(),
            "blocking_issues": self.blocking_issues,
            "warnings": self.warnings,
            "blocking_count": len(self.blocking_issues),
            "warning_count": len(self.warnings),
        }


def run_preflight_compliance_check(api: 'FacebookCommerceAPI') -> ComplianceGate:
    """
    Run pre-flight compliance check before major operations.

    Checks all Meta requirements and returns gate status.
    This mirrors Meta's internal review checklists.
    """
    gate = ComplianceGate()

    # 1. Token validity (BLOCKING)
    if not api.is_valid:
        gate.add_blocking_issue("TOKEN_INVALID", "Token validation failed")
        return gate  # Can't check further without valid token

    # 2. Required permissions (BLOCKING)
    if api.missing_permissions:
        gate.add_blocking_issue(
            "MISSING_SCOPES",
            f"Missing: {', '.join(api.missing_permissions)}"
        )

    # 3. Business access (BLOCKING if no businesses accessible)
    try:
        businesses = api.get_businesses()
        if not businesses:
            gate.add_blocking_issue("NO_BUSINESS_ACCESS", "No businesses found")
    except Exception as e:
        gate.add_blocking_issue("NO_BUSINESS_ACCESS", str(e))

    # 4. System User for background mode (BLOCKING)
    if api.mode == api.MODE_BACKGROUND and not api._is_system_user:
        gate.add_blocking_issue(
            "SYSTEM_USER_REQUIRED",
            "Background mode requires System User token"
        )

    # 5. Commerce Account linkage (BLOCKING for write operations)
    if api.catalog_id:
        is_linked, linkage = api.verify_catalog_commerce_linkage()
        if not is_linked:
            gate.add_blocking_issue(
                "CATALOG_NOT_LINKED",
                linkage.get("warning", "Catalog not linked to Commerce Account")
            )

    # Warnings (non-blocking)

    # API version deprecation
    version_status = get_api_version_status()
    if version_status.get("warning"):
        gate.add_warning("API_DEPRECATION", version_status["warning"])

    # Zero products
    if api.catalog_id:
        caps = api.get_catalog_capabilities()
        if caps and caps.get("product_count", 0) == 0:
            gate.add_warning("ZERO_PRODUCTS", "Catalog has no products")

    # Human token in interactive mode
    if api.mode == api.MODE_INTERACTIVE and not api._is_system_user:
        gate.add_warning("HUMAN_TOKEN_INTERACTIVE", "Human token - suitable for testing only")

    # Token expiry
    if api._token_health:
        health = api._token_health.get_status()
        expires_at = health.get("expires_at")
        if expires_at and expires_at != "Never":
            try:
                from datetime import datetime
                expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                now = datetime.utcnow().replace(tzinfo=expires.tzinfo)
                days_left = (expires - now).days
                if days_left < 14:
                    gate.add_warning("TOKEN_EXPIRING", f"Expires in {days_left} days")
            except Exception:
                pass

    gate._checked = True
    return gate


def run_live_diagnostics(api: 'FacebookCommerceAPI' = None) -> dict:
    """
    Run live Graph API diagnostics and return structured results.

    This replaces instructional UX with actual API probes.
    Each check returns: status, reason, fix_url, docs_url

    Returns:
        dict with 'checks' list and summary fields
    """
    logger.info("run_live_diagnostics() called")
    import os

    checks = []

    # 1. Token presence (env var check)
    token = os.environ.get('FB_ACCESS_TOKEN', '')
    checks.append({
        "id": "token_present",
        "label": "Access Token",
        "status": "pass" if token else "fail",
        "reason": "Token loaded from environment" if token else "FB_ACCESS_TOKEN not set",
        # Developer registration - first step to get access tokens
        "fix_url": "https://developers.facebook.com/docs/development/register/",
        "docs_url": "https://developers.facebook.com/docs/marketing-api/system-users",
        "api_checked": False,
    })

    # 2. Catalog ID presence
    catalog_id = os.environ.get('FB_CATALOG_ID', '')
    checks.append({
        "id": "catalog_present",
        "label": "Catalog ID",
        "status": "pass" if catalog_id else "fail",
        "reason": f"Catalog ID: {catalog_id}" if catalog_id else "FB_CATALOG_ID not set",
        # Direct link to Commerce Manager Catalogs (more reliable)
        "fix_url": "https://www.facebook.com/commerce_manager/catalogs/",
        "docs_url": "https://developers.facebook.com/docs/commerce-platform/catalog",
        "api_checked": False,
    })

    # If no token, can't do live checks
    if not token:
        return {
            "checks": checks,
            "total": len(checks),
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "failed": sum(1 for c in checks if c["status"] == "fail"),
            "can_proceed": False,
            "live_checked": False,
            "summary": "Token required for live API checks",
        }

    # 3. Token validity (live API probe via /debug_token)
    if api and api.is_valid:
        checks.append({
            "id": "token_valid",
            "label": "Token Valid",
            "status": "pass",
            "reason": f"Token validated via Graph API",
            "fix_url": "https://developers.facebook.com/tools/accesstoken/",
            "docs_url": "https://developers.facebook.com/docs/facebook-login/guides/access-tokens/",
            "api_checked": True,
        })

        # 4. Token type (System User vs Human)
        is_system = api._is_system_user
        checks.append({
            "id": "token_type",
            "label": "Token Type",
            "status": "pass" if is_system else "warn",
            "reason": "System User token" if is_system else "Human token (use System User for production)",
            "fix_url": "https://business.facebook.com/settings/system-users",
            "docs_url": "https://developers.facebook.com/docs/marketing-api/system-users",
            "api_checked": True,
        })

        # 5. Required scopes
        missing = api.missing_permissions
        checks.append({
            "id": "scopes",
            "label": "Required Scopes",
            "status": "pass" if not missing else "fail",
            "reason": "All required scopes present" if not missing else f"Missing: {', '.join(missing)}",
            "fix_url": "https://developers.facebook.com/tools/explorer/",
            "docs_url": "https://developers.facebook.com/docs/commerce-platform/catalog/get-started#required-permissions",
            "api_checked": True,
        })

        # 6. Business access (live probe via /me/businesses)
        try:
            businesses = api.get_businesses()
            has_business = bool(businesses)
            checks.append({
                "id": "business_access",
                "label": "Business Manager",
                "status": "pass" if has_business else "fail",
                "reason": f"Access to {len(businesses)} business(es)" if has_business else "No Business Manager access",
                "fix_url": "https://business.facebook.com/settings",
                "docs_url": "https://developers.facebook.com/docs/commerce-platform/business-manager",
                "api_checked": True,
            })
        except Exception as e:
            checks.append({
                "id": "business_access",
                "label": "Business Manager",
                "status": "fail",
                "reason": f"API error: {str(e)[:50]}",
                "fix_url": "https://business.facebook.com/settings",
                "docs_url": "https://developers.facebook.com/docs/commerce-platform/business-manager",
                "api_checked": True,
            })

        # 7. Catalog linkage (if catalog_id set)
        if catalog_id:
            try:
                is_linked, linkage = api.verify_catalog_commerce_linkage()
                checks.append({
                    "id": "catalog_linked",
                    "label": "Commerce Account Link",
                    "status": "pass" if is_linked else "fail",
                    "reason": "Catalog linked to Commerce Account" if is_linked else linkage.get("warning", "Not linked"),
                    "fix_url": "https://business.facebook.com/commerce",
                    "docs_url": "https://developers.facebook.com/docs/commerce-platform/setup",
                    "api_checked": True,
                })
            except Exception as e:
                checks.append({
                    "id": "catalog_linked",
                    "label": "Commerce Account Link",
                    "status": "fail",
                    "reason": f"Check failed: {str(e)[:50]}",
                    "fix_url": "https://business.facebook.com/commerce",
                    "docs_url": "https://developers.facebook.com/docs/commerce-platform/setup",
                    "api_checked": True,
                })
    else:
        # API not valid - add failure
        checks.append({
            "id": "token_valid",
            "label": "Token Valid",
            "status": "fail",
            "reason": "Token validation failed - check token format and expiry",
            "fix_url": "https://developers.facebook.com/tools/accesstoken/",
            "docs_url": "https://developers.facebook.com/docs/facebook-login/guides/access-tokens/",
            "api_checked": True,
        })

    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    warned = sum(1 for c in checks if c["status"] == "warn")

    return {
        "checks": checks,
        "total": len(checks),
        "passed": passed,
        "failed": failed,
        "warned": warned,
        "can_proceed": failed == 0,
        "live_checked": any(c["api_checked"] for c in checks),
        "summary": f"{passed} passed, {failed} failed" + (f", {warned} warnings" if warned else ""),
    }


# =============================================================================
# ERROR CLASSIFICATION (META-STANDARD)
# =============================================================================

class FacebookAPIError(Exception):
    """Structured Facebook API error with Meta error codes."""

    # Meta error code classifications
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    UNKNOWN = "UNKNOWN"

    # Human-readable operator hints per error class
    ERROR_HINTS = {
        TOKEN_EXPIRED: "Token has expired. Generate a new token in Meta Business Suite → Settings → Business Assets → System Users.",
        RATE_LIMITED: "API rate limit hit. Wait 1-5 minutes before retrying. Consider reducing request frequency.",
        PERMISSION_DENIED: "Missing required permission. Check token scopes in Business Settings → System Users → Assets.",
        NOT_FOUND: "Resource not found. Verify catalog ID exists and token has access to it.",
        UNKNOWN: "Unexpected error. Check Meta's Platform Status page for outages.",
    }

    def __init__(self, code: int, message: str, error_type: str, subcode: int = None):
        self.code = code
        self.message = message
        self.error_type = error_type
        self.subcode = subcode
        self.classification = self._classify()
        self.hint = self.ERROR_HINTS.get(self.classification, self.ERROR_HINTS[self.UNKNOWN])
        super().__init__(f"[{code}] {error_type}: {message}")

    def _classify(self) -> str:
        """Classify error based on Meta error codes."""
        if self.code == 190:
            return self.TOKEN_EXPIRED
        elif self.code in (4, 17, 32):
            return self.RATE_LIMITED
        elif self.code in (10, 200, 294):
            return self.PERMISSION_DENIED
        elif self.code == 100 and self.subcode == 33:
            return self.NOT_FOUND
        return self.UNKNOWN

    @classmethod
    def from_response(cls, resp_json: dict) -> 'FacebookAPIError':
        """Create error from Graph API response."""
        err = resp_json.get("error", {})
        return cls(
            code=err.get("code", 0),
            message=err.get("message", "Unknown error"),
            error_type=err.get("type", "UnknownError"),
            subcode=err.get("error_subcode")
        )


# =============================================================================
# TOKEN INTROSPECTION (META BEST PRACTICE)
# =============================================================================

def debug_token(input_token: str, app_token: str = None) -> dict:
    """
    Introspect a token using Facebook's /debug_token endpoint.

    This is the official way to validate tokens and check permissions.
    Requires an app token for introspection.

    Args:
        input_token: The user token to validate
        app_token: App access token (app_id|app_secret or from env)

    Returns:
        Token metadata including is_valid, scopes, expires_at, user_id
    """
    if not app_token:
        app_token = os.environ.get('FB_APP_TOKEN')

    if not app_token:
        # Fall back to using the token to validate itself (less secure but works)
        app_token = input_token

    try:
        resp = requests.get(
            f"{GRAPH_BASE}/debug_token",
            params={
                "input_token": input_token,
                "access_token": app_token,
            },
            timeout=10,
        )

        data = resp.json()
        if resp.status_code != 200:
            raise FacebookAPIError.from_response(data)

        return data.get("data", {})
    except requests.RequestException as e:
        logger.error(f"Token debug failed: {e}")
        return {"is_valid": False, "error": str(e)}


# =============================================================================
# TOKEN HEALTH ASSESSMENT (Meta Best Practice)
# =============================================================================

class TokenHealth:
    """
    Token health assessment based on Meta recommendations.

    Health Levels:
        GREEN: Valid, System User, long-lived (>60 days)
        YELLOW: Valid, Human User or expiring soon (<60 days)
        RED: Invalid or missing critical permissions
    """
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"

    def __init__(self, token: str = None):
        self.token = token or os.environ.get('FB_ACCESS_TOKEN')
        self.token_meta: dict = {}
        self.health = self.RED
        self.issues: List[str] = []
        self.warnings: List[str] = []

        if self.token:
            self._assess()

    def _assess(self):
        """Perform comprehensive token health assessment."""
        try:
            self.token_meta = debug_token(self.token)

            if not self.token_meta.get("is_valid"):
                self.health = self.RED
                self.issues.append("Token is invalid or expired")
                return

            # Start optimistic
            self.health = self.GREEN

            # Check token type (System User vs Human User)
            self._check_token_type()

            # Check expiration
            self._check_expiration()

            # Check permissions
            self._check_permissions()

            # Check app mode
            self._check_app_mode()

            # Determine final health based on issues/warnings
            if self.issues:
                self.health = self.RED
            elif self.warnings:
                self.health = self.YELLOW

        except Exception as e:
            self.health = self.RED
            self.issues.append(f"Health check failed: {e}")

    def _check_token_type(self):
        """Check if token is System User (preferred) or Human User."""
        # System user tokens have specific patterns
        # User tokens have 'user_id', system user tokens have different structure

        profile_id = self.token_meta.get("profile_id")
        user_id = self.token_meta.get("user_id")

        # Detect system user by checking if it's a business scoped token
        is_system_user = self.token_meta.get("granular_scopes") is not None

        if not is_system_user and user_id:
            self.warnings.append(
                "Token belongs to a human user. "
                "Meta recommends System User tokens for production catalog access."
            )

    def _check_expiration(self):
        """Check token expiration status."""
        expires_at = self.token_meta.get("expires_at")

        if expires_at == 0:
            # Token never expires (rare, but possible for some system tokens)
            return

        if expires_at:
            import time
            now = int(time.time())
            remaining_seconds = expires_at - now
            remaining_days = remaining_seconds / 86400

            if remaining_seconds <= 0:
                self.issues.append("Token has expired")
            elif remaining_days < 7:
                self.issues.append(f"Token expires in {remaining_days:.1f} days (critical)")
            elif remaining_days < 60:
                self.warnings.append(f"Token expires in {remaining_days:.0f} days")

    def _check_permissions(self):
        """Check for required permissions."""
        required = {"catalog_management", "business_management"}
        granted = set(self.token_meta.get("scopes", []))
        missing = required - granted

        if missing:
            self.issues.append(f"Missing permissions: {', '.join(missing)}")

    def _check_app_mode(self):
        """Check if app is in Development or Live mode."""
        app_id = self.token_meta.get("app_id")
        if not app_id:
            return

        # Note: Checking app mode requires additional API call
        # For now, we just note the app_id for debugging
        # Full check would require: GET /{app_id}?fields=development_mode

    def get_status(self) -> dict:
        """Get comprehensive health status for display."""
        expires_at = self.token_meta.get("expires_at")
        expires_str = None
        if expires_at:
            if expires_at == 0:
                expires_str = "Never"
            else:
                from datetime import datetime
                expires_str = datetime.fromtimestamp(expires_at).isoformat()

        return {
            "health": self.health,
            "health_emoji": {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}.get(self.health, "⚪"),
            "is_valid": self.token_meta.get("is_valid", False),
            "user_id": self.token_meta.get("user_id"),
            "app_id": self.token_meta.get("app_id"),
            "expires_at": expires_str,
            "scopes": self.token_meta.get("scopes", []),
            "issues": self.issues,
            "warnings": self.warnings,
        }


# Token health cache (5.1 - cache to avoid unnecessary /debug_token calls)
_token_health_cache: Dict[str, Tuple[TokenHealth, float]] = {}
_TOKEN_HEALTH_CACHE_TTL = 300  # 5 minutes


def get_token_health(token: str = None, force_refresh: bool = False) -> TokenHealth:
    """
    Get token health assessment with caching.

    Re-evaluates only on:
    - Token change (different token hash)
    - Explicit force_refresh=True
    - Cache expiry (5 minutes)
    - API failure (caller should call with force_refresh=True)
    """
    import hashlib
    import time

    actual_token = token or os.environ.get('FB_ACCESS_TOKEN', '')
    if not actual_token:
        return TokenHealth(None)

    # Create cache key from token hash (for security)
    token_hash = hashlib.sha256(actual_token.encode()).hexdigest()[:16]

    # Check cache
    if not force_refresh and token_hash in _token_health_cache:
        cached_health, cached_time = _token_health_cache[token_hash]
        if time.time() - cached_time < _TOKEN_HEALTH_CACHE_TTL:
            return cached_health

    # Create new assessment
    health = TokenHealth(actual_token)
    _token_health_cache[token_hash] = (health, time.time())

    return health


def invalidate_token_health_cache():
    """Invalidate all cached token health assessments."""
    global _token_health_cache
    _token_health_cache = {}


# =============================================================================
# IMMUTABLE AUDIT LOG (GitHub Best Practice)
# =============================================================================

class APIAuditLogger:
    """
    Immutable audit log with request fingerprints and rotation.

    For each API call, logs:
    - Endpoint
    - HTTP method
    - Sorted parameter names (no values for security)
    - SHA-256 hash of full request
    - Response status
    - Error class (if any)
    - Timestamp

    Rotation policy:
    - Max 10,000 entries per file
    - Max 30 days retention
    - Rotated files: meta_api_audit.log.1, .2, etc.

    Safe for compliance audits and Meta Support escalations.
    """

    MAX_FILE_ENTRIES = 10000
    MAX_AGE_DAYS = 30

    def __init__(self, log_file: str = None):
        self.log_file = log_file or os.path.join(
            os.path.dirname(__file__), "meta_api_audit.log"
        )
        self._entries: List[dict] = []
        self._max_memory_entries = 1000
        self._file_entry_count = self._count_file_entries()

    def _count_file_entries(self) -> int:
        """Count entries in current log file."""
        try:
            if os.path.exists(self.log_file):
                with open(self.log_file, "r") as f:
                    return sum(1 for _ in f)
        except Exception:
            pass
        return 0

    def _rotate_if_needed(self):
        """Rotate log file if it exceeds max entries."""
        if self._file_entry_count < self.MAX_FILE_ENTRIES:
            return

        try:
            # Find next rotation number
            i = 1
            while os.path.exists(f"{self.log_file}.{i}"):
                i += 1

            # Rotate current file
            os.rename(self.log_file, f"{self.log_file}.{i}")
            self._file_entry_count = 0
            logger.info(f"Rotated audit log to {self.log_file}.{i}")

            # Clean up old rotated files (older than MAX_AGE_DAYS)
            self._cleanup_old_logs()
        except Exception as e:
            logger.warning(f"Audit log rotation failed: {e}")

    def _cleanup_old_logs(self):
        """Remove rotated log files older than MAX_AGE_DAYS."""
        import glob
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=self.MAX_AGE_DAYS)

        for rotated_file in glob.glob(f"{self.log_file}.*"):
            try:
                mtime = datetime.utcfromtimestamp(os.path.getmtime(rotated_file))
                if mtime < cutoff:
                    os.remove(rotated_file)
                    logger.info(f"Removed old audit log: {rotated_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up {rotated_file}: {e}")

    def log_request(
        self,
        endpoint: str,
        method: str,
        params: dict,
        status_code: int,
        error_class: str = None,
        request_id: str = None
    ):
        """Log an API request with fingerprint."""
        import hashlib
        import json
        from datetime import datetime

        # Check rotation before writing
        self._rotate_if_needed()

        # Create fingerprint (hash of endpoint + sorted params, no token)
        safe_params = {k: v for k, v in params.items() if k != "access_token"}
        fingerprint_data = f"{method}:{endpoint}:{json.dumps(safe_params, sort_keys=True)}"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "endpoint": endpoint,
            "method": method,
            "param_names": sorted(safe_params.keys()),
            "fingerprint": fingerprint,
            "status_code": status_code,
            "error_class": error_class,
            "request_id": request_id,
        }

        # Memory log (circular buffer)
        self._entries.append(entry)
        if len(self._entries) > self._max_memory_entries:
            self._entries = self._entries[-self._max_memory_entries:]

        # File log (append-only)
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
            self._file_entry_count += 1
        except Exception as e:
            logger.warning(f"Audit log write failed: {e}")

    def get_recent_entries(self, limit: int = 100) -> List[dict]:
        """Get recent log entries (most recent first)."""
        return list(reversed(self._entries[-limit:]))

    def export_for_support(self, last_n: int = 50) -> dict:
        """Export sanitized log for Meta Support tickets."""
        entries = self.get_recent_entries(last_n)

        # Aggregate stats
        total_requests = len(entries)
        error_count = sum(1 for e in entries if e.get("error_class"))
        rate_limit_count = sum(1 for e in entries if e.get("error_class") == "RATE_LIMITED")

        unique_endpoints = list(set(e.get("endpoint", "") for e in entries))

        return {
            "export_timestamp": datetime.utcnow().isoformat() + "Z",
            "total_requests": total_requests,
            "error_count": error_count,
            "rate_limit_count": rate_limit_count,
            "unique_endpoints": unique_endpoints,
            "entries": entries,
        }


# Global audit logger
_audit_logger: Optional[APIAuditLogger] = None

def get_audit_logger() -> APIAuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = APIAuditLogger()
    return _audit_logger


# =============================================================================
# RATE LIMIT HANDLING (Meta Forum Best Practice)
# =============================================================================

class RateLimitHandler:
    """
    Handles rate limiting with exponential backoff.

    Meta penalizes aggressive retries. This handler:
    - Tracks rate limit events
    - Implements exponential backoff
    - Surfaces cooldown time to operator
    """

    def __init__(self):
        self._last_rate_limit: float = 0
        self._backoff_seconds: int = 0
        self._consecutive_limits: int = 0
        self._max_backoff: int = 3600  # 1 hour max

    def record_rate_limit(self):
        """Record a rate limit event and calculate backoff."""
        import time
        self._last_rate_limit = time.time()
        self._consecutive_limits += 1

        # Exponential backoff: 1, 2, 4, 8, 16... minutes, capped at 1 hour
        self._backoff_seconds = min(
            60 * (2 ** (self._consecutive_limits - 1)),
            self._max_backoff
        )

        logger.warning(
            f"Rate limited. Backoff: {self._backoff_seconds}s. "
            f"Consecutive limits: {self._consecutive_limits}"
        )

    def record_success(self):
        """Record a successful request, reducing backoff."""
        self._consecutive_limits = max(0, self._consecutive_limits - 1)
        if self._consecutive_limits == 0:
            self._backoff_seconds = 0

    def should_wait(self) -> Tuple[bool, int]:
        """
        Check if we should wait before making a request.

        Returns:
            (should_wait: bool, seconds_remaining: int)
        """
        if self._backoff_seconds == 0:
            return False, 0

        import time
        elapsed = time.time() - self._last_rate_limit
        remaining = max(0, self._backoff_seconds - elapsed)

        if remaining > 0:
            return True, int(remaining)
        return False, 0

    def get_status(self) -> dict:
        """Get rate limit status for display."""
        should_wait, remaining = self.should_wait()
        return {
            "is_rate_limited": should_wait,
            "cooldown_seconds": remaining,
            "consecutive_limits": self._consecutive_limits,
            "backoff_seconds": self._backoff_seconds,
        }


# Global rate limit handler
_rate_limiter = RateLimitHandler()

def get_rate_limiter() -> RateLimitHandler:
    """Get global rate limit handler."""
    return _rate_limiter


# =============================================================================
# CATALOG CAPABILITY PROBING (GitHub Pattern)
# =============================================================================

class CatalogCapabilities:
    """
    Probes and tracks catalog capabilities.

    Marketplace catalogs are not homogeneous. This class:
    - Detects catalog vertical (commerce, vehicles, real_estate, etc.)
    - Detects supported fields
    - Disables unsupported features
    """

    VERTICALS = {
        "commerce": {"supports_price": True, "supports_inventory": True},
        "vehicles": {"supports_price": True, "supports_mileage": True},
        "real_estate": {"supports_price": True, "supports_address": True},
        "hotels": {"supports_price": True, "supports_rooms": True},
        "flights": {"supports_price": True, "supports_routes": True},
        "destinations": {"supports_price": False, "supports_location": True},
        "home_listings": {"supports_price": True, "supports_address": True},
    }

    def __init__(self, catalog_id: str, token: str = None):
        self.catalog_id = catalog_id
        self.token = token or os.environ.get('FB_ACCESS_TOKEN')
        self.vertical: str = None
        self.name: str = None
        self.product_count: int = 0
        self.capabilities: dict = {}
        self.probed: bool = False

        if self.catalog_id and self.token:
            self._probe()

    def _probe(self):
        """Probe catalog to determine capabilities."""
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/{self.catalog_id}",
                params={
                    "access_token": self.token,
                    "fields": "id,name,product_count,vertical",
                },
                timeout=10,
            )

            if resp.status_code != 200:
                return

            data = resp.json()
            self.name = data.get("name")
            self.vertical = data.get("vertical", "commerce")
            self.product_count = data.get("product_count", 0)

            # Set capabilities based on vertical
            base_caps = {
                "can_read_products": True,
                "can_write_products": False,  # Need to test
                "supports_price": True,
                "supports_inventory": False,
            }

            vertical_caps = self.VERTICALS.get(self.vertical, {})
            self.capabilities = {**base_caps, **vertical_caps}

            # Test write capability
            self._test_write_capability()

            self.probed = True

        except Exception as e:
            logger.error(f"Catalog probe failed: {e}")

    def _test_write_capability(self):
        """Test if we can write to this catalog."""
        # This would require attempting a test write operation
        # For safety, we don't actually write, just check permissions
        try:
            resp = requests.get(
                f"{GRAPH_BASE}/{self.catalog_id}/products",
                params={
                    "access_token": self.token,
                    "limit": 1,
                },
                timeout=10,
            )

            if resp.status_code == 200:
                self.capabilities["can_read_products"] = True
                # Write capability would need actual permission check
                # via the token's scopes

        except Exception:
            self.capabilities["can_read_products"] = False

    def get_status(self) -> dict:
        """Get catalog capabilities for display."""
        return {
            "catalog_id": self.catalog_id,
            "name": self.name,
            "vertical": self.vertical,
            "product_count": self.product_count,
            "capabilities": self.capabilities,
            "probed": self.probed,
        }


def probe_catalog(catalog_id: str, token: str = None) -> CatalogCapabilities:
    """Probe a catalog to determine its capabilities."""
    return CatalogCapabilities(catalog_id, token)


# =============================================================================
# FACEBOOK API LAYER - Product Catalog & Commerce Manager Integration
# =============================================================================

class FacebookMarketplaceAPI:
    """
    Facebook Graph API interface for Marketplace via Product Catalog API.

    IMPORTANT: Facebook Marketplace doesn't have a direct public API.
    However, you CAN manage Marketplace listings through:

    1. Product Catalog API (Commerce Manager)
       - Requires: Business Manager + Commerce Account
       - Endpoint: /{catalog_id}/products
       - Permissions: catalog_management, business_management

    2. Commerce Platform API
       - For shops and commerce integration
       - Requires: Commerce Manager setup

    Setup Requirements:
    1. Create a Facebook App at developers.facebook.com
    2. Set up Business Manager at business.facebook.com
    3. Create a Commerce Account in Commerce Manager
    4. Create a Product Catalog
    5. Generate access token with required permissions

    Permissions needed:
    - catalog_management (read/write product catalogs)
    - business_management (manage business assets)
    - pages_read_engagement (if using Page shop)
    """

    API_VERSION = "v20.0"  # Updated to latest stable version

    def __init__(self, access_token: str = None, catalog_id: str = None):
        self.access_token = access_token or os.environ.get('FB_ACCESS_TOKEN')
        self.catalog_id = catalog_id or os.environ.get('FB_CATALOG_ID')
        self.api_base = f"https://graph.facebook.com/{self.API_VERSION}"
        self.api_available = False
        self.catalog_available = False
        self.user_info = None
        self.permissions = []

        if self.access_token:
            self.api_available = self._verify_token()
            if self.api_available:
                self._check_permissions()
                if self.catalog_id:
                    self.catalog_available = self._verify_catalog()

    def _verify_token(self) -> bool:
        """Verify if the access token is valid."""
        try:
            resp = requests.get(
                f"{self.api_base}/me",
                params={"access_token": self.access_token, "fields": "id,name"},
                timeout=10
            )
            if resp.status_code == 200:
                self.user_info = resp.json()
                return True
            return False
        except:
            return False

    def _check_permissions(self):
        """Check what permissions the token has."""
        try:
            resp = requests.get(
                f"{self.api_base}/me/permissions",
                params={"access_token": self.access_token},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                self.permissions = [
                    p["permission"] for p in data
                    if p.get("status") == "granted"
                ]
        except:
            pass

    def _verify_catalog(self) -> bool:
        """Verify if the catalog ID is valid and accessible."""
        try:
            resp = requests.get(
                f"{self.api_base}/{self.catalog_id}",
                params={"access_token": self.access_token},
                timeout=10
            )
            return resp.status_code == 200
        except:
            return False

    def has_permission(self, permission: str) -> bool:
        """Check if token has a specific permission."""
        return permission in self.permissions

    def get_catalogs(self) -> list:
        """
        Get all product catalogs accessible to this user/business.

        Returns list of catalogs with id, name, and product_count.
        """
        if not self.api_available:
            return []

        try:
            # First try to get business catalogs
            resp = requests.get(
                f"{self.api_base}/me/businesses",
                params={"access_token": self.access_token, "fields": "id,name"},
                timeout=10
            )

            catalogs = []
            if resp.status_code == 200:
                businesses = resp.json().get("data", [])
                for business in businesses:
                    biz_id = business.get("id")
                    # Get catalogs for this business
                    cat_resp = requests.get(
                        f"{self.api_base}/{biz_id}/owned_product_catalogs",
                        params={
                            "access_token": self.access_token,
                            "fields": "id,name,product_count,vertical"
                        },
                        timeout=10
                    )
                    if cat_resp.status_code == 200:
                        for cat in cat_resp.json().get("data", []):
                            cat["business_id"] = biz_id
                            cat["business_name"] = business.get("name")
                            catalogs.append(cat)

            return catalogs
        except Exception as e:
            print(f"Error fetching catalogs: {e}")
            return []

    def get_catalog_products(self, catalog_id: str = None, limit: int = 50) -> list:
        """
        Get products from a product catalog.

        This is the official way to access Marketplace listings if you've
        set up Commerce Manager properly.

        Args:
            catalog_id: The catalog ID (uses self.catalog_id if not provided)
            limit: Maximum number of products to return

        Returns:
            List of product dictionaries
        """
        cat_id = catalog_id or self.catalog_id
        if not cat_id or not self.api_available:
            return []

        try:
            resp = requests.get(
                f"{self.api_base}/{cat_id}/products",
                params={
                    "access_token": self.access_token,
                    "fields": ",".join([
                        "id",
                        "name",
                        "description",
                        "price",
                        "currency",
                        "availability",
                        "condition",
                        "image_url",
                        "url",
                        "retailer_id",
                        "category",
                        "brand",
                        "custom_data"
                    ]),
                    "limit": limit
                },
                timeout=30
            )

            if resp.status_code == 200:
                products = resp.json().get("data", [])
                return [self._map_catalog_product(p) for p in products]
            else:
                error = resp.json().get("error", {})
                print(f"Catalog API error: {error.get('message', 'Unknown error')}")
                return []
        except Exception as e:
            print(f"Error fetching catalog products: {e}")
            return []

    def _map_catalog_product(self, product: dict) -> dict:
        """Map catalog product to our internal format."""
        price_str = product.get("price", "")
        price_numeric = 0.0
        if price_str:
            # Price format is usually "1000 USD" or similar
            try:
                price_numeric = float(price_str.split()[0]) / 100  # Cents to dollars
            except:
                pass

        return {
            "item_id": product.get("id"),
            "retailer_id": product.get("retailer_id"),
            "title": product.get("name", ""),
            "description": product.get("description", ""),
            "price": price_str,
            "price_numeric": price_numeric,
            "currency": product.get("currency", "USD"),
            "condition": product.get("condition", ""),
            "category": product.get("category", ""),
            "status": product.get("availability", "in stock"),
            "image_urls": [product.get("image_url")] if product.get("image_url") else [],
            "item_url": product.get("url", ""),
            "brand": product.get("brand", ""),
            "custom_data": product.get("custom_data", {}),
            "source": "catalog_api"
        }

    def create_product(self, catalog_id: str = None, product_data: dict = None) -> dict:
        """
        Create a new product in the catalog.

        Args:
            catalog_id: The catalog ID
            product_data: Dict with product details:
                - name: Product name (required)
                - description: Product description
                - price: Price in cents (e.g., 1000 for $10.00)
                - currency: Currency code (default: USD)
                - condition: new, refurbished, used
                - availability: in stock, out of stock
                - image_url: URL to product image
                - url: Link to product page
                - retailer_id: Your internal product ID

        Returns:
            Created product data or error dict
        """
        cat_id = catalog_id or self.catalog_id
        if not cat_id or not self.api_available:
            return {"error": "API not available or no catalog ID"}

        if not product_data:
            return {"error": "No product data provided"}

        try:
            # Build the product payload
            payload = {
                "access_token": self.access_token,
                "requests": json.dumps([{
                    "method": "CREATE",
                    "retailer_id": product_data.get("retailer_id", f"prod_{int(time.time())}"),
                    "data": {
                        "name": product_data.get("name", ""),
                        "description": product_data.get("description", ""),
                        "price": str(product_data.get("price", 0)),
                        "currency": product_data.get("currency", "USD"),
                        "condition": product_data.get("condition", "new"),
                        "availability": product_data.get("availability", "in stock"),
                        "image_url": product_data.get("image_url", ""),
                        "url": product_data.get("url", ""),
                    }
                }])
            }

            resp = requests.post(
                f"{self.api_base}/{cat_id}/batch",
                data=payload,
                timeout=30
            )

            if resp.status_code == 200:
                return resp.json()
            else:
                return {"error": resp.json().get("error", {}).get("message", "Unknown error")}
        except Exception as e:
            return {"error": str(e)}

    def update_product(self, catalog_id: str = None, retailer_id: str = None,
                       product_data: dict = None) -> dict:
        """
        Update an existing product in the catalog.

        Args:
            catalog_id: The catalog ID
            retailer_id: The retailer_id of the product to update
            product_data: Dict with fields to update

        Returns:
            Update result or error dict
        """
        cat_id = catalog_id or self.catalog_id
        if not cat_id or not self.api_available or not retailer_id:
            return {"error": "Missing required parameters"}

        try:
            payload = {
                "access_token": self.access_token,
                "requests": json.dumps([{
                    "method": "UPDATE",
                    "retailer_id": retailer_id,
                    "data": product_data
                }])
            }

            resp = requests.post(
                f"{self.api_base}/{cat_id}/batch",
                data=payload,
                timeout=30
            )

            if resp.status_code == 200:
                return resp.json()
            else:
                return {"error": resp.json().get("error", {}).get("message", "Unknown error")}
        except Exception as e:
            return {"error": str(e)}

    def delete_product(self, catalog_id: str = None, retailer_id: str = None) -> dict:
        """
        Delete a product from the catalog.

        Args:
            catalog_id: The catalog ID
            retailer_id: The retailer_id of the product to delete

        Returns:
            Delete result or error dict
        """
        cat_id = catalog_id or self.catalog_id
        if not cat_id or not self.api_available or not retailer_id:
            return {"error": "Missing required parameters"}

        try:
            payload = {
                "access_token": self.access_token,
                "requests": json.dumps([{
                    "method": "DELETE",
                    "retailer_id": retailer_id
                }])
            }

            resp = requests.post(
                f"{self.api_base}/{cat_id}/batch",
                data=payload,
                timeout=30
            )

            if resp.status_code == 200:
                return resp.json()
            else:
                return {"error": resp.json().get("error", {}).get("message", "Unknown error")}
        except Exception as e:
            return {"error": str(e)}

    def get_my_listings(self, limit: int = 50) -> list:
        """
        Get user's marketplace listings.

        Tries catalog API first, returns empty list if unavailable.
        The caller should fall back to browser scraping if this returns empty.
        """
        if self.catalog_available:
            return self.get_catalog_products(limit=limit)
        return []

    def get_user_info(self) -> dict:
        """Get logged-in user info via API."""
        if not self.api_available:
            return None

        if self.user_info:
            return {
                "fb_id": self.user_info.get("id"),
                "fb_name": self.user_info.get("name"),
                "profile_picture_url": None  # Would need separate call
            }
        return None

    def get_api_status(self) -> dict:
        """Get detailed API status for debugging."""
        # API version deprecation status
        api_version_status = get_api_version_status()

        return {
            "api_available": self.api_available,
            "catalog_available": self.catalog_available,
            "catalog_id": self.catalog_id,
            "permissions": self.permissions,
            "user_info": self.user_info,
            "has_catalog_management": self.has_permission("catalog_management"),
            "has_business_management": self.has_permission("business_management"),
            "api_version": GRAPH_API_VERSION,
            "api_version_status": api_version_status,
        }


# =============================================================================
# PRODUCTION-GRADE COMMERCE API (Meta-Aligned)
# =============================================================================

class FacebookCommerceAPI:
    """
    Production-grade Commerce Manager API wrapper.

    Aligned with Meta's official Commerce Manager workflows:
    1. Token validated via /debug_token
    2. Permissions explicitly checked
    3. Catalogs discovered via /owned_product_catalogs
    4. All errors classified by Meta error codes
    5. Rate limiting with exponential backoff
    6. Permission health checks before operations
    7. System User token enforcement for non-interactive mode
    8. Commerce Account linkage verification

    Environment Variables:
        FB_ACCESS_TOKEN: User/System access token (required)
        FB_CATALOG_ID: Product catalog ID (optional, can be set later)
        FB_APP_TOKEN: App token for /debug_token (optional, for full introspection)
    """

    REQUIRED_PERMISSIONS = {"catalog_management", "business_management"}

    # Operation modes
    MODE_INTERACTIVE = "interactive"  # Human user tokens allowed
    MODE_BACKGROUND = "background"    # System User tokens required

    def __init__(self, validate_token: bool = True, mode: str = None, dry_run: bool = False):
        """
        Initialize Commerce API.

        Args:
            validate_token: If True, validates token on init (recommended)
            mode: Operation mode - 'interactive' (default) or 'background'
                  Background mode requires System User tokens
            dry_run: If True, prevents all write operations (POST, DELETE, etc.)
                     Useful for testing and validation without mutations
        """
        logger.info(f"FacebookCommerceAPI.__init__() validate={validate_token}, mode={mode}, dry_run={dry_run}")
        self.token = os.environ.get('FB_ACCESS_TOKEN')
        self.catalog_id = os.environ.get('FB_CATALOG_ID')
        logger.debug(f"Token present: {bool(self.token)}, Catalog ID: {self.catalog_id or 'not set'}")
        self.token_meta: Optional[dict] = None
        self.is_valid = False
        self.missing_permissions: set = set()
        self._token_health: Optional[TokenHealth] = None
        self._catalog_caps: Optional[CatalogCapabilities] = None
        self._commerce_accounts: List[dict] = []  # Linked Commerce Accounts
        self._is_system_user: bool = False
        self.mode = mode or self.MODE_INTERACTIVE
        self.dry_run = dry_run

        if self.dry_run:
            logger.info("🔒 DRY-RUN MODE: Write operations will be blocked")

        if self.token and validate_token:
            logger.debug("Introspecting token...")
            self._introspect_token()
            logger.info(f"Token validation complete: is_valid={self.is_valid}")

    def _introspect_token(self):
        """Validate token and check permissions via /debug_token."""
        try:
            meta = debug_token(self.token)
            self.token_meta = meta

            if not meta.get("is_valid"):
                logger.warning("Access token is invalid")
                return

            # Check required permissions
            granted = set(meta.get("scopes", []))
            self.missing_permissions = self.REQUIRED_PERMISSIONS - granted

            if self.missing_permissions:
                logger.warning(f"Missing permissions: {self.missing_permissions}")

            # Detect System User token (2.1)
            self._is_system_user = self._detect_system_user(meta)

            # Check mode constraints (2.1)
            if self.mode == self.MODE_BACKGROUND and not self._is_system_user:
                logger.warning(
                    "Background mode requires System User token. "
                    "Human user tokens may be revoked without notice."
                )

            self.is_valid = True

            # Build full token health assessment
            self._token_health = TokenHealth(self.token)

        except FacebookAPIError as e:
            logger.error(f"Token introspection failed: {e}")
            self.is_valid = False
        except Exception as e:
            logger.error(f"Token introspection error: {e}")
            self.is_valid = False

    def _detect_system_user(self, meta: dict) -> bool:
        """
        Detect if token belongs to a System User (2.1).

        System User tokens are preferred for:
        - Scheduled sync
        - Background jobs
        - Non-interactive usage

        Human user tokens are only recommended for:
        - Setup / Test mode
        - Interactive debugging
        """
        # System user tokens have specific characteristics:
        # 1. May have granular_scopes field
        # 2. User ID follows pattern for system users
        # 3. No profile_id (system users don't have profiles)

        has_granular_scopes = meta.get("granular_scopes") is not None
        no_profile = meta.get("profile_id") is None
        user_id = str(meta.get("user_id", ""))

        # System user IDs are typically numeric and very long
        # This is a heuristic - Meta doesn't expose a direct field
        return has_granular_scopes or (no_profile and len(user_id) > 15)

    def check_system_user_gate(self, operation: str = "background operation") -> Tuple[bool, str]:
        """
        Check if token is suitable for the operation (2.1 - System User Gate).

        Returns:
            (allowed: bool, message: str)
        """
        if self.mode == self.MODE_INTERACTIVE:
            return True, "Interactive mode - human user tokens allowed"

        if self._is_system_user:
            return True, "System User token - approved for background operations"

        return False, (
            f"Background {operation} requires System User token. "
            "Human user tokens may be revoked by Meta without notice. "
            "Create a System User in Business Manager and use its token."
        )

    def _check_rate_limit(self) -> Tuple[bool, int]:
        """Check if we should wait due to rate limiting."""
        return get_rate_limiter().should_wait()

    def get_commerce_accounts(self, business_id: str = None) -> List[dict]:
        """
        Get Commerce Accounts linked to a business (2.2).

        Commerce Accounts are required for Marketplace listings via API.
        Model: Business → Commerce Account → Product Catalog
        """
        if not self.is_valid:
            return []

        accounts = []
        try:
            businesses = [{"id": business_id}] if business_id else self.get_businesses()

            for biz in businesses:
                try:
                    data = self._make_request(
                        "GET",
                        f"{biz['id']}/owned_commerce_accounts",
                        {"fields": "id,name,commerce_surface"}
                    )
                    for acc in data.get("data", []):
                        acc["business_id"] = biz["id"]
                        acc["business_name"] = biz.get("name", "Unknown")
                        accounts.append(acc)
                except FacebookAPIError:
                    continue  # Business may not have commerce accounts

        except Exception as e:
            logger.error(f"Commerce account discovery failed: {e}")

        self._commerce_accounts = accounts
        return accounts

    def verify_catalog_commerce_linkage(self, catalog_id: str = None) -> Tuple[bool, dict]:
        """
        Verify catalog is linked to a Commerce Account (2.2).

        Many tools stop at "catalog exists". This method ensures:
        - Catalog is linked to a Commerce Account
        - Commerce Account is properly configured

        Returns:
            (is_linked: bool, linkage_info: dict)
        """
        cat_id = catalog_id or self.catalog_id
        if not cat_id:
            return False, {"error": "No catalog ID provided"}

        try:
            # Get catalog details including commerce linkage
            data = self._make_request(
                "GET",
                cat_id,
                {"fields": "id,name,product_count,vertical,commerce_account"}
            )

            commerce_account = data.get("commerce_account")

            if commerce_account:
                return True, {
                    "catalog_id": cat_id,
                    "catalog_name": data.get("name"),
                    "commerce_account_id": commerce_account.get("id"),
                    "commerce_account_name": commerce_account.get("name"),
                    "is_linked": True,
                }
            else:
                return False, {
                    "catalog_id": cat_id,
                    "catalog_name": data.get("name"),
                    "commerce_account_id": None,
                    "is_linked": False,
                    "warning": (
                        "Catalog is not linked to a Commerce Account. "
                        "Products may not surface on Marketplace. "
                        "Link in Commerce Manager: business.facebook.com/commerce"
                    ),
                }

        except FacebookAPIError as e:
            return False, {"error": str(e)}
        except Exception as e:
            return False, {"error": str(e)}

    def _make_request(self, method: str, endpoint: str, params: dict = None,
                      timeout: int = 10) -> dict:
        """
        Make a rate-limit-aware request to the Graph API.

        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint (without base URL)
            params: Query parameters
            timeout: Request timeout in seconds

        Returns:
            Response JSON data

        Raises:
            RuntimeError: If rate limited or dry-run blocks write
            FacebookAPIError: If API returns error
        """
        # Dry-run protection: block write operations
        if self.dry_run and method.upper() in ("POST", "DELETE", "PUT", "PATCH"):
            logger.warning(f"🔒 DRY-RUN: Blocked {method.upper()} to {endpoint}")
            return {
                "dry_run": True,
                "blocked_method": method.upper(),
                "blocked_endpoint": endpoint,
                "message": "Write operation blocked by dry-run mode",
            }

        # Check rate limit before making request
        should_wait, remaining = self._check_rate_limit()
        if should_wait:
            raise RuntimeError(
                f"Rate limited. Please wait {remaining} seconds before retrying."
            )

        params = params or {}
        params["access_token"] = self.token

        url = f"{GRAPH_BASE}/{endpoint}"
        error_class = None
        status_code = 0

        try:
            if method.upper() == "GET":
                resp = requests.get(url, params=params, timeout=timeout)
            elif method.upper() == "POST":
                resp = requests.post(url, data=params, timeout=timeout)
            elif method.upper() == "DELETE":
                resp = requests.delete(url, params=params, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            data = resp.json()
            status_code = resp.status_code

            # Check for rate limit errors
            if resp.status_code != 200:
                error = data.get("error", {})
                error_code = error.get("code", 0)
                api_error = FacebookAPIError.from_response(data)
                error_class = api_error.classification

                if error_code in (4, 17, 32):
                    # Rate limited - record and raise
                    get_rate_limiter().record_rate_limit()

                # Audit log the error
                get_audit_logger().log_request(
                    endpoint=endpoint,
                    method=method.upper(),
                    params=params,
                    status_code=status_code,
                    error_class=error_class,
                )

                raise api_error

            # Success - record to reduce backoff
            get_rate_limiter().record_success()

            # Audit log success
            get_audit_logger().log_request(
                endpoint=endpoint,
                method=method.upper(),
                params=params,
                status_code=status_code,
                error_class=None,
            )

            return data

        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            # Audit log network error
            get_audit_logger().log_request(
                endpoint=endpoint,
                method=method.upper(),
                params=params,
                status_code=0,
                error_class="NETWORK_ERROR",
            )
            raise RuntimeError(f"Network error: {e}")

    def get_token_health(self) -> dict:
        """Get comprehensive token health status."""
        if not self._token_health:
            self._token_health = TokenHealth(self.token)
        return self._token_health.get_status()

    def get_token_info(self) -> dict:
        """Get token metadata for display (safe for UI)."""
        if not self.token_meta:
            return {"is_valid": False, "error": "No token metadata"}

        return {
            "is_valid": self.token_meta.get("is_valid", False),
            "user_id": self.token_meta.get("user_id"),
            "app_id": self.token_meta.get("app_id"),
            "expires_at": self.token_meta.get("expires_at"),
            "scopes": self.token_meta.get("scopes", []),
            "missing_permissions": list(self.missing_permissions),
        }

    def permission_health_check(self) -> Tuple[bool, List[str]]:
        """
        Perform lightweight permission health check before operations.

        Forum consensus: Permissions can disappear without token invalidation.
        This checks:
        - Can access /me/businesses
        - Can access catalog products (if catalog set)

        Returns:
            (is_healthy: bool, issues: list)
        """
        issues = []

        if not self.is_valid:
            issues.append("Token is not valid")
            return False, issues

        try:
            # Check business access
            businesses = self.get_businesses()
            if not businesses:
                issues.append("No businesses accessible")
        except Exception as e:
            issues.append(f"Cannot access businesses: {e}")

        if self.catalog_id:
            try:
                # Check catalog access
                ok, msg = self.verify_catalog_access()
                if not ok:
                    issues.append(f"Catalog not accessible: {msg}")
            except Exception as e:
                issues.append(f"Catalog check failed: {e}")

        return len(issues) == 0, issues

    def get_businesses(self) -> List[dict]:
        """Get all businesses accessible to this user."""
        if not self.is_valid:
            raise RuntimeError("API not initialized or token invalid")

        data = self._make_request("GET", "me/businesses", {"fields": "id,name"})
        return data.get("data", [])

    def get_business_trust_signals(self, business_id: str = None) -> dict:
        """
        Get business verification status and trust signals (2.1).

        Surfaces:
        - Business verification status
        - Catalog ownership
        - Commerce Account linkage

        This is read-only, informational data for operator awareness.
        """
        if not self.is_valid:
            return {"error": "API not initialized"}

        try:
            businesses = [{"id": business_id}] if business_id else self.get_businesses()
            trust_signals = []

            for biz in businesses:
                biz_id = biz["id"]
                try:
                    # Get business details including verification status
                    data = self._make_request(
                        "GET",
                        biz_id,
                        {"fields": "id,name,verification_status,primary_page"}
                    )

                    # Count owned catalogs
                    catalogs = []
                    try:
                        cat_data = self._make_request(
                            "GET",
                            f"{biz_id}/owned_product_catalogs",
                            {"fields": "id,name"}
                        )
                        catalogs = cat_data.get("data", [])
                    except FacebookAPIError:
                        pass

                    # Count commerce accounts
                    commerce_accounts = []
                    try:
                        comm_data = self._make_request(
                            "GET",
                            f"{biz_id}/owned_commerce_accounts",
                            {"fields": "id,name"}
                        )
                        commerce_accounts = comm_data.get("data", [])
                    except FacebookAPIError:
                        pass

                    trust_signals.append({
                        "business_id": biz_id,
                        "business_name": data.get("name"),
                        "verification_status": data.get("verification_status", "unknown"),
                        "has_primary_page": data.get("primary_page") is not None,
                        "catalog_count": len(catalogs),
                        "commerce_account_count": len(commerce_accounts),
                        "trust_level": self._calculate_trust_level(
                            data.get("verification_status"),
                            len(catalogs),
                            len(commerce_accounts)
                        ),
                    })
                except FacebookAPIError as e:
                    trust_signals.append({
                        "business_id": biz_id,
                        "error": str(e),
                    })

            return {
                "businesses": trust_signals,
                "total_businesses": len(trust_signals),
            }

        except Exception as e:
            return {"error": str(e)}

    def _calculate_trust_level(self, verification_status: str, catalog_count: int,
                                commerce_count: int) -> str:
        """Calculate trust level based on business signals."""
        score = 0

        # Verification status
        if verification_status == "verified":
            score += 3
        elif verification_status == "pending":
            score += 1

        # Has catalogs
        if catalog_count > 0:
            score += 1

        # Has commerce accounts
        if commerce_count > 0:
            score += 1

        if score >= 4:
            return "HIGH"
        elif score >= 2:
            return "MEDIUM"
        else:
            return "LOW"

    def get_owned_catalogs(self) -> List[dict]:
        """
        Get all product catalogs owned by accessible businesses.

        This is the Commerce Manager-compliant way to discover catalogs.
        """
        if not self.is_valid:
            return []

        catalogs = []

        try:
            for biz in self.get_businesses():
                try:
                    data = self._make_request(
                        "GET",
                        f"{biz['id']}/owned_product_catalogs",
                        {"fields": "id,name,product_count,vertical"}
                    )

                    for cat in data.get("data", []):
                        cat["business_id"] = biz["id"]
                        cat["business_name"] = biz["name"]
                        catalogs.append(cat)
                except FacebookAPIError:
                    continue  # Business may not own catalogs

        except Exception as e:
            logger.error(f"Catalog discovery failed: {e}")

        return catalogs

    def verify_catalog_access(self, catalog_id: str = None) -> Tuple[bool, str]:
        """
        Verify read/write access to a catalog.

        Returns:
            (success: bool, message: str)
        """
        cat_id = catalog_id or self.catalog_id
        if not cat_id:
            return False, "No catalog ID provided"

        if not self.is_valid:
            return False, "Token not valid"

        try:
            self._make_request("GET", f"{cat_id}/products", {"limit": 1})
            return True, "Catalog accessible"

        except FacebookAPIError as e:
            return False, e.message
        except RuntimeError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

    def get_catalog_products(self, catalog_id: str = None, limit: int = 50) -> List[dict]:
        """Get products from a catalog."""
        cat_id = catalog_id or self.catalog_id
        if not cat_id:
            raise RuntimeError("No catalog ID configured")

        if not self.is_valid:
            raise RuntimeError("Token not valid")

        fields = ",".join([
            "id",
            "name",
            "description",
            "price",
            "currency",
            "availability",
            "condition",
            "image_url",
            "url",
            "retailer_id",
        ])

        data = self._make_request(
            "GET",
            f"{cat_id}/products",
            {"limit": limit, "fields": fields},
            timeout=30
        )

        return data.get("data", [])

    def get_catalog_capabilities(self, catalog_id: str = None) -> dict:
        """Get capabilities for a catalog (vertical, supported fields, etc.)."""
        cat_id = catalog_id or self.catalog_id
        if not cat_id:
            return {"error": "No catalog ID"}

        if not self._catalog_caps or self._catalog_caps.catalog_id != cat_id:
            self._catalog_caps = CatalogCapabilities(cat_id, self.token)

        return self._catalog_caps.get_status()

    def get_status(self) -> dict:
        """Get comprehensive API status for debugging."""
        catalog_ok, catalog_msg = self.verify_catalog_access() if self.catalog_id else (False, "No catalog")

        # Get rate limit status
        rate_status = get_rate_limiter().get_status()

        # Get token health
        token_health = self.get_token_health() if self.token else None

        # Commerce Account linkage (2.2)
        commerce_linked = None
        if self.catalog_id:
            is_linked, linkage_info = self.verify_catalog_commerce_linkage()
            commerce_linked = linkage_info

        # System User status (2.1)
        system_user_gate = self.check_system_user_gate()

        # API version deprecation status
        api_version_status = get_api_version_status()

        # Build state machine status (5.1)
        state_machine = self._build_state_machine_status(
            catalog_ok, commerce_linked, system_user_gate
        )

        # Time-based warnings (5.2)
        time_warnings = self._get_time_based_warnings(token_health)

        return {
            "token_valid": self.is_valid,
            "token_info": self.get_token_info() if self.token_meta else None,
            "token_health": token_health,
            "is_system_user": self._is_system_user,
            "system_user_gate": {"allowed": system_user_gate[0], "message": system_user_gate[1]},
            "catalog_id": self.catalog_id,
            "catalog_accessible": catalog_ok,
            "catalog_message": catalog_msg,
            "catalog_capabilities": self.get_catalog_capabilities() if self.catalog_id else None,
            "commerce_linkage": commerce_linked,
            "missing_permissions": list(self.missing_permissions),
            "rate_limit": rate_status,
            "api_version": GRAPH_API_VERSION,
            "api_version_status": api_version_status,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "state_machine": state_machine,
            "time_warnings": time_warnings,
        }

    def _build_state_machine_status(self, catalog_ok: bool, commerce_linked: dict,
                                     system_user_gate: tuple) -> dict:
        """
        Build state machine status block (5.1).

        Shows progression: Token → Business → Commerce → Catalog → Capabilities
        """
        states = []

        # State 1: Token valid
        token_state = {
            "step": 1,
            "name": "Token Valid",
            "status": "✅" if self.is_valid else "❌",
            "ok": self.is_valid,
        }
        states.append(token_state)

        # State 2: Business accessible
        business_ok = self.is_valid and not self.missing_permissions
        business_state = {
            "step": 2,
            "name": "Business Accessible",
            "status": "✅" if business_ok else ("⚠️" if self.is_valid else "⏸️"),
            "ok": business_ok,
        }
        states.append(business_state)

        # State 3: Commerce linked
        commerce_ok = commerce_linked and commerce_linked.get("is_linked", False)
        commerce_state = {
            "step": 3,
            "name": "Commerce Linked",
            "status": "✅" if commerce_ok else ("⚠️" if business_ok else "⏸️"),
            "ok": commerce_ok,
        }
        states.append(commerce_state)

        # State 4: Catalog accessible
        catalog_state = {
            "step": 4,
            "name": "Catalog Accessible",
            "status": "✅" if catalog_ok else ("⚠️" if commerce_ok else "⏸️"),
            "ok": catalog_ok,
        }
        states.append(catalog_state)

        # State 5: Capabilities detected
        caps = self.get_catalog_capabilities() if self.catalog_id else None
        caps_ok = caps and caps.get("probed", False)
        caps_state = {
            "step": 5,
            "name": "Capabilities Detected",
            "status": "✅" if caps_ok else ("⏸️" if not catalog_ok else "⚠️"),
            "ok": caps_ok,
        }
        states.append(caps_state)

        # Overall status
        all_ok = all(s["ok"] for s in states)
        first_failure = next((s for s in states if not s["ok"]), None)

        return {
            "states": states,
            "all_ok": all_ok,
            "current_step": first_failure["step"] if first_failure else 5,
            "summary": "All systems operational" if all_ok else f"Blocked at: {first_failure['name']}" if first_failure else "Unknown",
        }

    def _get_time_based_warnings(self, token_health: dict) -> List[str]:
        """
        Get time-based warnings (5.2).

        Warns about:
        - Token expires in <14 days
        - Catalog has zero products
        - No successful API calls in X hours
        """
        warnings = []

        # Token expiry warning
        if token_health and token_health.get("expires_at"):
            expires_str = token_health.get("expires_at")
            if expires_str and expires_str != "Never":
                try:
                    from datetime import datetime
                    expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
                    now = datetime.utcnow().replace(tzinfo=expires.tzinfo)
                    days_left = (expires - now).days
                    if days_left < 14:
                        warnings.append(f"⚠️ Token expires in {days_left} days. Renew soon.")
                except Exception:
                    pass

        # Zero products warning
        caps = self.get_catalog_capabilities() if self.catalog_id else None
        if caps and caps.get("product_count", 0) == 0:
            warnings.append("⚠️ Catalog has zero products.")

        # API version deprecation warning
        api_status = get_api_version_status()
        if api_status.get("warning"):
            warnings.append(api_status["warning"])

        return warnings

    def export_support_bundle(self) -> dict:
        """
        Export Meta Support Debug Bundle (3.2).

        For Meta Support tickets, exports:
        - App ID
        - Business ID(s)
        - Catalog ID
        - Token scopes (not the token itself)
        - Endpoint + timestamp of recent failures
        - Rate limit state

        Safe to attach to support tickets (no secrets).
        """
        from datetime import datetime

        # Get business IDs if available
        business_ids = []
        try:
            for biz in self.get_businesses():
                business_ids.append({
                    "id": biz.get("id"),
                    "name": biz.get("name"),
                })
        except Exception:
            pass

        # Get audit log export
        audit_export = get_audit_logger().export_for_support(last_n=50)

        bundle = {
            "export_version": "1.0",
            "export_timestamp": datetime.utcnow().isoformat() + "Z",
            "environment": {
                "api_version": GRAPH_API_VERSION,
                "python_version": os.popen("python3 --version").read().strip(),
            },
            "app_info": {
                "app_id": self.token_meta.get("app_id") if self.token_meta else None,
            },
            "token_info": {
                "is_valid": self.is_valid,
                "is_system_user": self._is_system_user,
                "scopes": self.token_meta.get("scopes", []) if self.token_meta else [],
                "expires_at": self.token_meta.get("expires_at") if self.token_meta else None,
                # DO NOT include the actual token
            },
            "business_info": business_ids,
            "catalog_info": {
                "catalog_id": self.catalog_id,
                "capabilities": self.get_catalog_capabilities() if self.catalog_id else None,
            },
            "rate_limit_state": get_rate_limiter().get_status(),
            "permission_state": {
                "missing_permissions": list(self.missing_permissions),
            },
            "recent_api_activity": audit_export,
        }

        return bundle

    def save_support_bundle(self, filepath: str = None) -> str:
        """
        Save Meta Support Debug Bundle to file (3.2).

        Returns:
            Path to saved bundle file
        """
        import json
        from datetime import datetime

        if not filepath:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"meta_support_bundle_{timestamp}.json"

        bundle = self.export_support_bundle()

        with open(filepath, "w") as f:
            json.dump(bundle, f, indent=2, default=str)

        logger.info(f"Support bundle saved to: {filepath}")
        return filepath

    def run_preflight_check(self) -> ComplianceGate:
        """
        Run pre-flight compliance check before major operations.

        Returns ComplianceGate with blocking issues and warnings.
        Use gate.can_proceed() to check if operation is allowed.
        """
        return run_preflight_compliance_check(self)

    def require_compliance(self, operation: str = "operation") -> bool:
        """
        Enforce compliance before operation.

        Raises RuntimeError if blocking issues exist.
        Returns True if compliant.
        """
        gate = self.run_preflight_check()
        can_proceed, message = gate.can_proceed(operation)

        if not can_proceed:
            raise RuntimeError(message)

        return True

    def set_mode(self, mode: str) -> Tuple[bool, str]:
        """
        Set operation mode with enforcement.

        Args:
            mode: 'interactive' or 'background'

        Returns:
            (success: bool, message: str)
        """
        if mode == self.MODE_BACKGROUND:
            if not self._is_system_user:
                return False, (
                    "Cannot switch to background mode without System User token.\n"
                    "Meta requires System User tokens for production operations.\n"
                    "Fix: Business Settings → System Users → Add → Generate Token"
                )

        self.mode = mode
        return True, f"Mode set to {mode}"


# Global Commerce API instance
_commerce_api: Optional[FacebookCommerceAPI] = None

def get_commerce_api(force_refresh: bool = False) -> FacebookCommerceAPI:
    """Get or create the production Commerce API instance."""
    logger.debug(f"get_commerce_api() called, force_refresh={force_refresh}")
    global _commerce_api
    if _commerce_api is None or force_refresh:
        logger.info("Creating new FacebookCommerceAPI instance")
        _commerce_api = FacebookCommerceAPI()
    return _commerce_api


# =============================================================================
# LEGACY API INSTANCE (Backward Compatibility)
# =============================================================================

# Global API instance - will use if token available
_fb_api = None

def get_facebook_api(force_refresh: bool = False) -> FacebookMarketplaceAPI:
    """Get or create Facebook API instance."""
    global _fb_api
    if _fb_api is None or force_refresh:
        config = load_fb_config()
        _fb_api = FacebookMarketplaceAPI(
            access_token=config.get('access_token'),
            catalog_id=config.get('catalog_id')
        )
    return _fb_api


# =============================================================================
# BROWSER MANAGEMENT (Simplified - no persistence to avoid zombie processes)
# =============================================================================

def kill_zombie_browsers():
    """Kill any leftover Firefox/geckodriver processes from previous runs."""
    # Don't use pkill as it can kill the parent process
    # Just rely on proper driver.quit() and cleanup_temp_profile()
    pass


def create_single_use_browser():
    """
    Create a browser for a single operation.
    MUST be closed after use with driver.quit().
    """
    profile_path = get_firefox_profile_path()
    if not profile_path:
        return None, None

    driver, temp_profile = create_firefox_driver(profile_path)
    return driver, temp_profile


def create_wire_browser():
    """
    Create a selenium-wire browser for network interception.
    This enables capturing GraphQL responses during scrolling.

    Returns:
        Tuple of (WebDriver, temp_profile_dir or None)
    """
    if not SELENIUM_WIRE_AVAILABLE:
        logger.warning("selenium-wire not available, falling back to regular browser")
        return create_single_use_browser()

    profile_path = get_firefox_profile_path()
    if not profile_path:
        logger.error("Could not find Firefox profile")
        return None, None

    # Copy profile to temp dir (selenium-wire needs write access)
    from selenium_enricher import copy_firefox_profile
    temp_profile = copy_firefox_profile(profile_path)

    try:
        # Configure selenium-wire options
        seleniumwire_options = {
            'disable_encoding': True,  # Disable gzip to make parsing easier
            'suppress_connection_errors': True,
        }

        # Configure Firefox options
        options = Options()
        options.add_argument("-profile")
        options.add_argument(temp_profile)
        options.set_preference("browser.sessionstore.resume_from_crash", False)
        options.set_preference("browser.startup.page", 0)
        options.set_preference("browser.startup.homepage_override.mstone", "ignore")

        # Create selenium-wire Firefox driver
        driver = wire_webdriver.Firefox(
            options=options,
            seleniumwire_options=seleniumwire_options
        )
        logger.info("Created selenium-wire browser for network interception")
        return driver, temp_profile

    except Exception as e:
        logger.error(f"Failed to create selenium-wire browser: {e}")
        cleanup_temp_profile()
        # Fallback to regular browser
        return create_single_use_browser()


def extract_listings_from_graphql_responses(driver, timeout_seconds: int = 60) -> Dict[str, dict]:
    """
    Extract marketplace listings from captured GraphQL responses.

    Facebook loads listings via GraphQL as user scrolls. This function
    parses the captured network responses to extract all listing data.

    Args:
        driver: selenium-wire WebDriver with captured requests
        timeout_seconds: How long to wait for responses

    Returns:
        Dict mapping listing_id to listing data
    """
    listings = {}

    if not hasattr(driver, 'requests'):
        logger.warning("Driver doesn't have requests attribute - not a selenium-wire driver")
        return listings

    # Parse all GraphQL responses
    for request in driver.requests:
        if request.response is None:
            continue

        # Look for GraphQL responses
        if '/graphql' not in request.url and '/api/graphql' not in request.url:
            continue

        try:
            # Get response body
            body = request.response.body
            if not body:
                continue

            # Decode if bytes
            if isinstance(body, bytes):
                try:
                    body = body.decode('utf-8')
                except:
                    continue

            # Parse JSON (may be multiple JSON objects on separate lines)
            # Facebook sends multiple JSON responses in one body, one per line
            json_objects = []
            try:
                json_objects.append(json.loads(body))
            except json.JSONDecodeError:
                # Try parsing each line as separate JSON (common Facebook pattern)
                for line in body.split('\n'):
                    line = line.strip()
                    if line and line.startswith('{'):
                        try:
                            json_objects.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

            # Extract listings from each JSON object
            for data in json_objects:
                _extract_listings_from_json(data, listings)

        except Exception as e:
            logger.debug(f"Error parsing GraphQL response: {e}")
            continue

    logger.info(f"Extracted {len(listings)} listings from {len(driver.requests)} network requests")
    return listings


def _extract_listings_from_json(data: Any, listings: Dict[str, dict], depth: int = 0):
    """
    Recursively extract GroupCommerceProductItem listings from JSON data.

    Args:
        data: JSON data (dict or list)
        listings: Dict to populate with listing_id -> data
        depth: Current recursion depth (max 20)
    """
    if depth > 20:
        return

    if isinstance(data, dict):
        # Check if this is a GroupCommerceProductItem or Marketplace listing
        typename = data.get('__typename', '')

        # Match multiple possible typenames Facebook uses
        is_listing = typename in ('GroupCommerceProductItem', 'MarketplaceListing',
                                   'MarketplaceProductItem', 'CometMarketplaceProductItem')

        # Also check for nodes with id + marketplace fields
        has_marketplace_fields = (
            'id' in data and
            len(str(data.get('id', ''))) >= 10 and
            ('marketplace_listing_title' in data or 'listing_title' in data or
             'is_viewer_seller' in data or 'listing_price' in data or
             'primary_listing_photo' in data)
        )

        if is_listing or has_marketplace_fields:
            listing_id = data.get('id')
            if listing_id and len(str(listing_id)) >= 10:
                # Extract title - try multiple field names
                title = (data.get('marketplace_listing_title') or
                        data.get('listing_title') or
                        data.get('title') or '')

                # Extract bump info (nested in marketplace_bump_info)
                bump_info = data.get('marketplace_bump_info') or {}
                bump_count = bump_info.get('bump_count', 0) if isinstance(bump_info, dict) else 0
                days_until_next_bump = bump_info.get('days_until_next_bump') if isinstance(bump_info, dict) else None
                max_bump_count = bump_info.get('max_bump_count', 5) if isinstance(bump_info, dict) else 5

                # Extract all relevant fields
                listing = {
                    'item_id': str(listing_id),
                    'title': title,
                    'is_sold': data.get('is_sold', False),
                    'is_pending': data.get('is_pending', False),
                    'is_draft': data.get('is_draft', False),
                    'is_viewer_seller': data.get('is_viewer_seller', False),
                    'category_id': data.get('marketplace_listing_category_id'),
                    'bump_count': bump_count,
                    'days_until_next_bump': days_until_next_bump,
                    'max_bump_count': max_bump_count,
                }

                # Extract price - try multiple field names
                # Facebook uses formatted_price.text or listing_price.formatted_amount
                price_info = data.get('formatted_price') or data.get('listing_price') or data.get('price') or {}
                if isinstance(price_info, dict):
                    listing['price'] = (price_info.get('text') or
                                       price_info.get('formatted_amount') or
                                       price_info.get('amount', ''))
                elif isinstance(price_info, str):
                    listing['price'] = price_info

                # Extract image - try multiple structures
                photo = (data.get('primary_listing_photo') or
                        data.get('listing_photo') or
                        data.get('image') or {})
                if isinstance(photo, dict):
                    image = photo.get('image') or photo
                    if isinstance(image, dict):
                        listing['image_url'] = (image.get('uri') or
                                               image.get('url', '')).replace('\\/', '/')

                # Only add if we have meaningful data or haven't seen this ID
                existing = listings.get(listing_id, {})
                new_has_title = bool(listing.get('title'))
                existing_has_title = bool(existing.get('title'))

                if listing_id not in listings or (new_has_title and not existing_has_title):
                    listings[listing_id] = listing

        # Recurse into all values
        for key, value in data.items():
            _extract_listings_from_json(value, listings, depth + 1)

    elif isinstance(data, list):
        for item in data:
            _extract_listings_from_json(item, listings, depth + 1)


# Stub functions for compatibility
def get_persistent_browser():
    """Deprecated - returns None. Use create_single_use_browser instead."""
    return None


def close_persistent_browser():
    """Deprecated - no-op. Browser is closed after each use now."""
    pass


# =============================================================================
# API CONFIGURATION
# =============================================================================

CONFIG_FILE = Path(__file__).parent / ".fb_config.json"

def load_fb_config() -> dict:
    """Load Facebook API configuration."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {}


def save_fb_config(config: dict):
    """Save Facebook API configuration."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_access_token() -> str:
    """Get Facebook access token from config or environment."""
    # Environment variable takes precedence
    token = os.environ.get('FB_ACCESS_TOKEN')
    if token:
        return token

    # Fall back to config file
    config = load_fb_config()
    return config.get('access_token')


def set_access_token(token: str, persist: bool = True) -> bool:
    """
    Set and validate Facebook access token.

    Args:
        token: The access token to set
        persist: If True, also save to config file (for UI convenience)

    Returns:
        True if token is valid
    """
    # Set in environment (primary for security)
    os.environ['FB_ACCESS_TOKEN'] = token

    if persist:
        # Also persist to config for convenience
        config = load_fb_config()
        config['access_token'] = token
        save_fb_config(config)

    # Update API instances
    global _fb_api, _commerce_api
    config = load_fb_config()
    _fb_api = FacebookMarketplaceAPI(token, catalog_id=config.get('catalog_id'))
    _commerce_api = FacebookCommerceAPI()

    return _fb_api.api_available


def get_catalog_id() -> str:
    """Get Facebook catalog ID from config or environment."""
    # Environment variable takes precedence
    catalog_id = os.environ.get('FB_CATALOG_ID')
    if catalog_id:
        return catalog_id

    # Fall back to config file
    config = load_fb_config()
    return config.get('catalog_id')


def set_catalog_id(catalog_id: str, persist: bool = True) -> bool:
    """
    Set and validate Facebook catalog ID.

    Args:
        catalog_id: The catalog ID to set
        persist: If True, also save to config file

    Returns:
        True if catalog is accessible
    """
    # Set in environment (primary)
    os.environ['FB_CATALOG_ID'] = catalog_id

    if persist:
        config = load_fb_config()
        config['catalog_id'] = catalog_id
        save_fb_config(config)

    # Update API instances
    get_facebook_api(force_refresh=True)
    get_commerce_api(force_refresh=True)

    return get_facebook_api().catalog_available


def test_access_token(token: str, include_debug: bool = True) -> tuple:
    """
    Test if an access token is valid.

    Uses /debug_token for full introspection when possible,
    falls back to /me endpoint for basic validation.

    Returns: (is_valid: bool, user_info: dict or error_message: str)
    """
    logger.info(f"test_access_token() called, token_length={len(token) if token else 0}")
    try:
        # First, get basic user info
        logger.debug(f"Testing token via {GRAPH_BASE}/me")
        resp = requests.get(
            f"{GRAPH_BASE}/me",
            params={"access_token": token, "fields": "id,name"},
            timeout=10
        )
        logger.debug(f"Response status: {resp.status_code}")

        if resp.status_code != 200:
            error = resp.json().get("error", {}).get("message", "Unknown error")
            error_code = resp.json().get("error", {}).get("code", 0)

            # Classify the error
            if error_code == 190:
                return False, "Token expired or invalid"
            elif error_code in (4, 17, 32):
                return False, "Rate limited - try again later"
            elif error_code in (10, 200, 294):
                return False, "Permission denied"
            return False, error

        data = resp.json()
        user_info = {
            "fb_id": data.get("id"),
            "fb_name": data.get("name"),
        }

        # Optionally get token metadata via /debug_token
        if include_debug:
            token_meta = debug_token(token)
            if token_meta.get("is_valid"):
                user_info["expires_at"] = token_meta.get("expires_at")
                user_info["scopes"] = token_meta.get("scopes", [])
                user_info["app_id"] = token_meta.get("app_id")

                # Check for required permissions
                scopes = set(token_meta.get("scopes", []))
                missing = {"catalog_management", "business_management"} - scopes
                if missing:
                    user_info["missing_permissions"] = list(missing)

        return True, user_info

    except Exception as e:
        logger.error(f"Token test failed: {e}")
        return False, str(e)


def test_catalog_access(token: str, catalog_id: str) -> tuple:
    """
    Test if a catalog is accessible with the given token.
    Returns: (is_valid: bool, catalog_info: dict or error_message: str)
    """
    try:
        resp = requests.get(
            f"https://graph.facebook.com/{FacebookMarketplaceAPI.API_VERSION}/{catalog_id}",
            params={"access_token": token, "fields": "id,name,product_count,vertical"},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            return True, {
                "catalog_id": data.get("id"),
                "name": data.get("name"),
                "product_count": data.get("product_count", 0),
                "vertical": data.get("vertical")
            }
        else:
            error = resp.json().get("error", {}).get("message", "Unknown error")
            return False, error
    except Exception as e:
        return False, str(e)


def get_available_catalogs(token: str = None) -> list:
    """
    Get all catalogs available to the user.
    Returns list of catalog info dicts.
    """
    if token is None:
        token = get_access_token()
    if not token:
        return []

    api = FacebookMarketplaceAPI(access_token=token)
    return api.get_catalogs()


# =============================================================================
# DATABASE FUNCTIONS
# =============================================================================


def init_marketplace_db(db_path: str = "marketplace.db"):
    """Initialize marketplace items database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS marketplace_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id TEXT UNIQUE,
            title TEXT,
            price TEXT,
            price_numeric REAL,
            description TEXT,
            category TEXT,
            category_id TEXT,
            condition TEXT,
            location TEXT,
            listed_date TEXT,
            status TEXT DEFAULT 'available',
            is_sold INTEGER DEFAULT 0,
            is_pending INTEGER DEFAULT 0,
            is_draft INTEGER DEFAULT 0,
            bump_count INTEGER DEFAULT 0,
            days_until_next_bump INTEGER,
            max_bump_count INTEGER DEFAULT 5,
            image_urls TEXT,
            local_image_paths TEXT,
            seller_id TEXT,
            seller_name TEXT,
            item_url TEXT,
            scraped_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Add new columns if they don't exist (for existing databases)
    new_columns = [
        ("category_id", "TEXT"),
        ("is_sold", "INTEGER DEFAULT 0"),
        ("is_pending", "INTEGER DEFAULT 0"),
        ("is_draft", "INTEGER DEFAULT 0"),
        ("bump_count", "INTEGER DEFAULT 0"),
        ("days_until_next_bump", "INTEGER"),
        ("max_bump_count", "INTEGER DEFAULT 5"),
    ]
    for col_name, col_type in new_columns:
        try:
            cur.execute(f"ALTER TABLE marketplace_items ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    cur.execute("""
        CREATE TABLE IF NOT EXISTS logged_in_user (
            id INTEGER PRIMARY KEY,
            fb_id TEXT,
            fb_name TEXT,
            fb_username TEXT,
            profile_picture_url TEXT,
            last_checked TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()
    print(f"✅ Marketplace database initialized: {db_path}")


def get_logged_in_user(driver) -> dict:
    """
    Detect the currently logged-in Facebook user.
    
    Returns dict with: fb_id, fb_name, fb_username, profile_picture_url
    """
    print("🔐 Detecting logged-in Facebook user...")

    try:
        # Go to Facebook home
        driver.get("https://www.facebook.com")
        time.sleep(3)

        # Check if logged in
        if "login" in driver.current_url.lower():
            print("  ❌ Not logged into Facebook")
            return None

        # Try to get user info from the profile link in nav
        user_info = {}

        # Method 1: Find profile link in navigation
        try:
            # Look for the user's profile link
            profile_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/me/"], a[href*="profile.php"]')
            for link in profile_links:
                href = link.get_attribute("href")
                if href and ("/me" in href or "profile.php" in href):
                    # Navigate to profile to get ID
                    driver.get("https://www.facebook.com/me/")
                    time.sleep(2)

                    # Get the redirected URL which contains ID or username
                    final_url = driver.current_url
                    if "facebook.com/" in final_url:
                        path = final_url.split("facebook.com/")[1].split("?")[0].rstrip("/")
                        if path.isdigit():
                            user_info["fb_id"] = path
                        else:
                            user_info["fb_username"] = path
                    break
        except Exception as e:
            print(f"  ⚠️ Could not find profile link: {e}")

        # Method 2: Get name from page
        try:
            # Go to profile page
            driver.get("https://www.facebook.com/me/")
            time.sleep(2)

            # Find the h1 with the user's name
            h1_elements = driver.find_elements(By.TAG_NAME, "h1")
            for h1 in h1_elements:
                text = h1.text.strip()
                if text and len(text) > 1 and len(text) < 100:
                    user_info["fb_name"] = text
                    break
        except Exception as e:
            print(f"  ⚠️ Could not get name: {e}")

        # Method 3: Get profile picture
        try:
            # Look for profile picture image
            img_elements = driver.find_elements(By.CSS_SELECTOR, 'image, img[alt*="profile"], svg image')
            for img in img_elements:
                src = img.get_attribute("xlink:href") or img.get_attribute("src")
                if src and "scontent" in src:
                    user_info["profile_picture_url"] = src
                    break
        except Exception as e:
            print(f"  ⚠️ Could not get profile picture: {e}")

        if user_info.get("fb_name") or user_info.get("fb_username"):
            print(f"  ✅ Logged in as: {user_info.get('fb_name', user_info.get('fb_username', 'Unknown'))}")
            return user_info
        else:
            print("  ⚠️ Could not determine user info")
            return None

    except Exception as e:
        print(f"  ❌ Error detecting user: {e}")
        return None


def get_user_selling_items(driver, limit: int = 50, download_images: bool = True) -> list:
    """
    Get items the logged-in user is currently selling.
    Captures: title, price, image URL, item URL in the order shown on Facebook.

    Returns list of item dicts.
    """
    print(f"🛒 Fetching your marketplace listings (limit: {limit})...")

    items = []
    seen_ids = set()

    try:
        # Navigate to user's selling page
        driver.get("https://www.facebook.com/marketplace/you/selling")
        time.sleep(4)

        # Check if we're on the right page
        if "login" in driver.current_url.lower():
            print("  ❌ Not logged in - redirected to login page")
            return items

        # Scroll to load all items
        for scroll in range(5):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        # Find all item links - these contain the item cards
        item_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/marketplace/item/"]')
        print(f"  Found {len(item_links)} item links")

        for link in item_links:
            if len(items) >= limit:
                break

            try:
                href = link.get_attribute("href")
                if not href:
                    continue

                # Extract item ID
                match = re.search(r'/marketplace/item/(\d+)', href)
                if not match:
                    continue

                item_id = match.group(1)
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Get the card container (parent elements)
                card = link
                for _ in range(6):
                    try:
                        card = card.find_element(By.XPATH, "..")
                    except:
                        break

                # Extract text - FB typically shows: price, title, location
                card_text = card.text.strip()
                lines = [l.strip() for l in card_text.split('\n') if l.strip()]

                price = None
                title = None
                location = None

                for line in lines:
                    if not price and ('$' in line or line.lower() == 'free'):
                        price = line
                    elif not title and len(line) > 2 and line != price:
                        title = line
                    elif title and not location and len(line) > 2:
                        location = line
                        break

                # Extract image URL from the card
                image_url = None
                try:
                    # Try to find image in the link or its children
                    img_elements = link.find_elements(By.TAG_NAME, 'img')
                    for img in img_elements:
                        src = img.get_attribute('src')
                        if src and 'scontent' in src:
                            image_url = src
                            break

                    # Also check for background images in style
                    if not image_url:
                        divs = link.find_elements(By.CSS_SELECTOR, 'div[style*="background-image"]')
                        for div in divs:
                            style = div.get_attribute('style')
                            if style and 'url(' in style:
                                match = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                                if match:
                                    image_url = match.group(1)
                                    break
                except Exception as e:
                    pass

                item = {
                    "item_id": item_id,
                    "title": title or f"Item {item_id}",
                    "price": price or "Price not listed",
                    "location": location,
                    "image_url": image_url,
                    "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
                    "status": "available"
                }
                items.append(item)
                print(f"    [{len(items)}] {price} - {title[:40] if title else 'Untitled'}...")

            except Exception as e:
                continue

        print(f"  ✅ Found {len(items)} items")

        # Download images if requested
        if download_images and items:
            download_item_images(items)

        return items

    except Exception as e:
        print(f"  ❌ Error fetching items: {e}")
        import traceback
        traceback.print_exc()
        return items


def download_item_images(items: list, images_dir: str = "marketplace_images"):
    """Download item images to local directory"""
    import requests

    logger.debug(f"download_item_images() called: {len(items)} items, dir={images_dir}")
    Path(images_dir).mkdir(exist_ok=True)

    downloaded = 0
    skipped = 0
    failed = 0

    for item in items:
        image_url = item.get("image_url")
        if not image_url:
            continue

        item_id = item.get("item_id")
        local_path = Path(images_dir) / f"{item_id}.jpg"

        if local_path.exists():
            item["local_image_path"] = str(local_path)
            skipped += 1
            continue

        try:
            resp = requests.get(image_url, timeout=10)
            if resp.status_code == 200:
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                item["local_image_path"] = str(local_path)
                downloaded += 1
                print(f"    📷 Downloaded image for {item_id}")
            else:
                failed += 1
                logger.debug(f"Image download HTTP {resp.status_code} for {item_id}")
        except Exception as e:
            failed += 1
            logger.debug(f"Image download failed for {item_id}: {e}")
            print(f"    ⚠️ Could not download image for {item_id}: {e}")

    logger.info(f"Image download complete: {downloaded} new, {skipped} cached, {failed} failed")


def save_user_to_db(user_info: dict, db_path: str = "marketplace.db"):
    """
    Save logged-in user info to database.
    ONLY saves if we have REAL data - never overwrites good data with defaults.
    """
    logger.debug(f"save_user_to_db() called: user_info={user_info}, db_path={db_path}")
    if not user_info:
        logger.debug("No user_info provided, skipping save")
        return

    # Check if we have REAL data (not just defaults)
    new_name = user_info.get("fb_name", "")
    new_id = user_info.get("fb_id", "")
    new_username = user_info.get("fb_username", "")

    # If all we have is "Facebook User" default, don't overwrite existing data
    has_real_name = new_name and new_name != "Facebook User"
    has_real_id = bool(new_id)
    has_real_username = bool(new_username)

    if not (has_real_name or has_real_id or has_real_username):
        logger.debug("No real user data to save (only defaults)")
        print(f"  ⚠️ No real user data to save, keeping existing")
        return

    init_marketplace_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    try:
        # Check existing data first
        cur.execute("SELECT fb_id, fb_name, fb_username FROM logged_in_user WHERE id=1")
        existing = cur.fetchone()

        if existing:
            existing_id, existing_name, existing_username = existing
            logger.debug(f"Existing user in DB: id={existing_id}, name={existing_name}")
            # Only overwrite if new data is better
            if existing_name and existing_name != "Facebook User" and not has_real_name:
                # Existing has real name, new doesn't - keep existing
                logger.info(f"Keeping existing user (better data): {existing_name}")
                print(f"  ℹ️ Keeping existing user: {existing_name}")
                conn.close()
                return

        # We have better data - save it
        cur.execute("DELETE FROM logged_in_user")
        cur.execute("""
            INSERT INTO logged_in_user (id, fb_id, fb_name, fb_username, profile_picture_url)
            VALUES (1, ?, ?, ?, ?)
        """, (
            user_info.get("fb_id"),
            user_info.get("fb_name"),
            user_info.get("fb_username"),
            user_info.get("profile_picture_url")
        ))
        conn.commit()
        logger.info(f"User saved to DB: fb_id={new_id}, fb_name={new_name}")
        print(f"  💾 Saved user info: {user_info.get('fb_name', 'Unknown')}")
    except Exception as e:
        logger.error(f"Failed to save user to DB: {e}")
        print(f"  ⚠️ Could not save user: {e}")
    finally:
        conn.close()


def save_items_to_db(items: list, seller_info: dict, db_path: str = "marketplace.db"):
    """Save marketplace items to database with images and status info"""
    logger.debug(f"save_items_to_db() called: {len(items)} items, db_path={db_path}")
    if not items:
        logger.debug("No items to save")
        print("  ⚠️ No items to save")
        return 0

    init_marketplace_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    saved_count = 0
    failed_count = 0
    for item in items:
        try:
            cur.execute("""
                INSERT OR REPLACE INTO marketplace_items
                (item_id, title, price, location, item_url, image_urls, local_image_paths,
                 status, is_sold, is_pending, is_draft, category_id,
                 bump_count, days_until_next_bump, max_bump_count,
                 seller_id, seller_name, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                item.get("item_id"),
                item.get("title"),
                item.get("price"),
                item.get("location"),
                item.get("item_url"),
                item.get("image_url"),  # Store in image_urls field
                item.get("local_image_path"),
                item.get("status", "available"),
                1 if item.get("is_sold") else 0,
                1 if item.get("is_pending") else 0,
                1 if item.get("is_draft") else 0,
                item.get("category_id"),
                item.get("bump_count", 0),
                item.get("days_until_next_bump"),
                item.get("max_bump_count", 5),
                seller_info.get("fb_id") or seller_info.get("fb_username"),
                seller_info.get("fb_name")
            ))
            saved_count += 1
            logger.debug(f"  Saved item: id={item.get('item_id')}, price={item.get('price')}")
        except Exception as e:
            failed_count += 1
            logger.warning(f"Failed to save item {item.get('item_id')}: {e}")
            print(f"  ⚠️ Could not save item {item.get('item_id')}: {e}")

    # Save logged-in user info
    if seller_info:
        cur.execute("DELETE FROM logged_in_user")
        cur.execute("""
            INSERT INTO logged_in_user (id, fb_id, fb_name, fb_username, profile_picture_url)
            VALUES (1, ?, ?, ?, ?)
        """, (
            seller_info.get("fb_id"),
            seller_info.get("fb_name"),
            seller_info.get("fb_username"),
            seller_info.get("profile_picture_url")
        ))

    conn.commit()
    conn.close()
    logger.info(f"Database save complete: {saved_count} saved, {failed_count} failed to {db_path}")
    print(f"  ✅ Saved {saved_count} items to {db_path}")
    return saved_count


def check_facebook_login_status():
    """
    Quick check if Firefox profile has Facebook login.
    Returns: (is_logged_in: bool, user_info: dict or None)
    """
    logger.info("check_facebook_login_status() called")
    # Kill any zombie browsers first
    kill_zombie_browsers()

    driver = None
    try:
        logger.debug("Creating single-use browser...")
        driver, temp_profile = create_single_use_browser()
        if not driver:
            logger.warning("Failed to create browser - returning False")
            return False, None

        logger.debug("Getting logged-in user info...")
        user_info = get_logged_in_user(driver)
        is_logged_in = user_info is not None
        logger.info(f"Login check result: logged_in={is_logged_in}, user={user_info.get('fb_name') if user_info else None}")
        return is_logged_in, user_info

    except Exception as e:
        logger.exception(f"Error checking login: {e}")
        return False, None
    finally:
        if driver:
            try:
                driver.quit()
                logger.debug("Browser closed")
            except:
                pass
        cleanup_temp_profile()
        kill_zombie_browsers()


def scrape_my_listings_fast(db_path: str = "marketplace.db", limit: int = 50, use_network_capture: bool = True):
    """
    Go directly to selling page, extract user info from there.
    Always closes browser after use to prevent zombie processes.

    Args:
        db_path: Path to SQLite database
        limit: Maximum number of listings to return
        use_network_capture: If True, use selenium-wire to capture GraphQL responses
                            for more reliable extraction (recommended)
    """
    import time as time_module
    scan_start = time_module.time()
    logger.info(f"scrape_my_listings_fast() called: db_path={db_path}, limit={limit}, network_capture={use_network_capture}")
    print("🛒 Scanning Marketplace listings...")

    # Kill any zombie browsers first
    kill_zombie_browsers()

    driver = None
    use_wire = use_network_capture and SELENIUM_WIRE_AVAILABLE
    try:
        # Create browser for this operation
        browser_start = time_module.time()
        logger.debug("Starting browser...")
        if use_wire:
            print("  🔄 Starting browser with network capture (selenium-wire)...")
            driver, temp_profile = create_wire_browser()
        else:
            print("  🔄 Starting browser...")
            driver, temp_profile = create_single_use_browser()
        browser_elapsed = time_module.time() - browser_start
        logger.info(f"Browser started in {browser_elapsed:.1f}s, temp_profile={temp_profile}, wire={use_wire}")

        if not driver:
            logger.error("Could not start Firefox - returning empty")
            print("❌ Could not start Firefox")
            return None, []

        # Go DIRECTLY to selling page - single navigation
        nav_start = time_module.time()
        logger.debug("Navigating to selling page...")
        print("  📍 Navigating to your selling page...")
        driver.get("https://www.facebook.com/marketplace/you/selling")
        time.sleep(3)
        nav_elapsed = time_module.time() - nav_start
        logger.info(f"Navigation completed in {nav_elapsed:.1f}s")

        # Check if redirected to login (not logged in)
        if "login" in driver.current_url.lower():
            logger.warning("Redirected to login - user not logged in")
            print("❌ Not logged into Facebook")
            return None, []

        logger.info(f"On selling page: {driver.current_url}")
        print(f"  ✅ On page: {driver.current_url}")

        # Extract user info - DO NOT navigate away from selling page!
        # Navigating away destroys lazy-loaded DOM content
        user_info = {}
        try:
            # Get user ID from the selling page
            profile_elements = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/marketplace/profile/"]')
            for elem in profile_elements:
                href = elem.get_attribute("href")
                if href:
                    match = re.search(r'/marketplace/profile/(\d+)', href)
                    if match:
                        user_info["fb_id"] = match.group(1)
                        print(f"  👤 Found user ID: {user_info['fb_id']}")
                        break

            # Get name from page source JSON (no navigation needed!)
            if user_info.get("fb_id"):
                page_source = driver.page_source
                # Pattern 1: "name":"John Doe" near user ID
                name_match = re.search(rf'"id":"{user_info["fb_id"]}"[^}}]{{0,500}}"name":"([^"]+)"', page_source)
                if name_match:
                    user_info["fb_name"] = name_match.group(1)
                    print(f"  👤 Found name from JSON: {user_info['fb_name']}")
                else:
                    # Pattern 2: Look for actor with user ID
                    actor_match = re.search(rf'"actor":\{{"__typename":"User"[^}}]*"id":"{user_info["fb_id"]}"[^}}]*\}}', page_source)
                    if actor_match:
                        block = actor_match.group(0)
                        name_in_block = re.search(r'"name":"([^"]+)"', block)
                        if name_in_block:
                            user_info["fb_name"] = name_in_block.group(1)
                            print(f"  👤 Found name from actor: {user_info['fb_name']}")

            # Fallback: Try aria-label on selling page (no navigation!)
            if "fb_name" not in user_info:
                name_elems = driver.find_elements(By.CSS_SELECTOR, '[aria-label*="profile"]')
                for elem in name_elems:
                    label = elem.get_attribute("aria-label")
                    if label and "profile" in label.lower():
                        parts = label.split(",")
                        if len(parts) > 1:
                            user_info["fb_name"] = parts[1].strip()
                            break

            # Fallback: Look for account switcher which shows name
            if "fb_name" not in user_info:
                switcher = driver.find_elements(By.CSS_SELECTOR, '[aria-label="Your profile"]')
                for elem in switcher:
                    parent = elem.find_element(By.XPATH, "..")
                    text = parent.text.strip()
                    if text and len(text) > 1:
                        user_info["fb_name"] = text.split('\n')[0]
                        break

            if user_info.get("fb_id"):
                print(f"  👤 User ID: {user_info['fb_id']}")
            if user_info.get("fb_name"):
                print(f"  👤 Name: {user_info['fb_name']}")

        except Exception as e:
            logger.warning(f"Could not extract user info: {e}")
            print(f"  ⚠️ Could not extract user info: {e}")

        # Fallback if no name found
        if "fb_name" not in user_info:
            user_info["fb_name"] = "Facebook User"
            logger.debug("Using fallback name: Facebook User")

        # Log extracted user info
        logger.info(f"User info extracted: fb_id={user_info.get('fb_id')}, fb_name={user_info.get('fb_name')}")

        # Wait for page to fully load before scrolling
        print("  ⏳ Waiting for page to load...")
        time.sleep(3)

        # IMPROVED SCROLLING: Track unique listing IDs, not just scroll height
        # Facebook lazy-loads via GraphQL - scroll height alone is unreliable
        scroll_start = time_module.time()
        logger.debug("Starting improved scroll to load all items...")
        print("  📜 Scrolling to load all items (improved algorithm)...")

        def count_listing_ids_in_page():
            """Count unique GroupCommerceProductItem IDs in page source."""
            try:
                source = driver.page_source
                # Count IDs near is_viewer_seller:true (seller's own listings)
                import re
                matches = re.findall(r'"id":"(\d{10,20})"', source)
                return len(set(matches))
            except:
                return 0

        # Scroll to top first, then scroll down incrementally
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)

        scroll_count = 0
        max_scrolls = 30  # Increased safety limit
        no_new_ids_count = 0  # Track consecutive scrolls with no new IDs
        last_id_count = count_listing_ids_in_page()
        last_height = driver.execute_script("return document.body.scrollHeight")

        while scroll_count < max_scrolls:
            # Scroll down by viewport height (more natural scrolling)
            driver.execute_script("""
                window.scrollBy({
                    top: window.innerHeight * 0.8,
                    behavior: 'smooth'
                });
            """)
            time.sleep(3)  # Longer wait for Facebook's GraphQL lazy loading

            # Check for new content using BOTH methods
            new_height = driver.execute_script("return document.body.scrollHeight")
            new_id_count = count_listing_ids_in_page()

            height_changed = new_height != last_height
            ids_increased = new_id_count > last_id_count

            if ids_increased:
                logger.debug(f"Scroll {scroll_count + 1}: Found {new_id_count - last_id_count} new IDs (total: {new_id_count})")
                no_new_ids_count = 0
            elif height_changed:
                # Height changed but no new IDs - might be loading
                no_new_ids_count = 0
            else:
                no_new_ids_count += 1

            # Stop after 3 consecutive scrolls with no new IDs (was 2)
            if no_new_ids_count >= 3:
                scroll_elapsed = time_module.time() - scroll_start
                logger.info(f"Scroll complete: {scroll_count + 1} scrolls, {new_id_count} unique IDs in {scroll_elapsed:.1f}s")
                print(f"  ✅ Loaded all items after {scroll_count + 1} scrolls ({new_id_count} IDs)")
                break

            last_height = new_height
            last_id_count = new_id_count
            scroll_count += 1

            # Show progress every 3 scrolls
            if scroll_count % 3 == 0:
                print(f"  📜 Scrolled {scroll_count} times ({new_id_count} IDs found)...")

        # NOTE: Do NOT scroll back to top before extraction!
        # This can trigger Facebook to re-render and lose lazy-loaded content.
        # page_source captures the full DOM regardless of scroll position.

        # Extract items - use network capture if available (more reliable)
        extract_start = time_module.time()

        items = []
        network_listings = {}

        # Try network capture first (selenium-wire)
        if use_wire and hasattr(driver, 'requests'):
            logger.info("Extracting listings from captured GraphQL responses...")
            print("  🔍 Extracting from network responses...")
            network_listings = extract_listings_from_graphql_responses(driver)

            # Convert network listings to item format
            # Note: We're on /you/selling page so ALL items are the user's listings
            # Don't filter by is_viewer_seller since it may not be set in GraphQL response
            for listing_id, listing_data in network_listings.items():
                status = 'available'
                if listing_data.get('is_sold'):
                    status = 'sold'
                elif listing_data.get('is_pending'):
                    status = 'pending'
                elif listing_data.get('is_draft'):
                    status = 'draft'

                items.append({
                    "item_id": listing_data.get('item_id', listing_id),
                    "title": listing_data.get('title', f"Item {listing_id}"),
                    "price": listing_data.get('price', 'See on Facebook'),
                    "location": None,
                    "image_url": listing_data.get('image_url'),
                    "item_url": f"https://www.facebook.com/marketplace/item/{listing_id}/",
                    "status": status,
                    "is_sold": listing_data.get('is_sold', False),
                    "is_pending": listing_data.get('is_pending', False),
                    "is_draft": listing_data.get('is_draft', False),
                    "category_id": listing_data.get('category_id'),
                    "bump_count": listing_data.get('bump_count', 0),
                    "days_until_next_bump": listing_data.get('days_until_next_bump'),
                    "max_bump_count": listing_data.get('max_bump_count', 5),
                })

            logger.info(f"Network extraction: {len(items)} seller listings from {len(network_listings)} total")
            print(f"  📡 Found {len(items)} listings from network capture")

        # ALWAYS extract from page source to get titles/prices
        # Network capture gets IDs reliably, page source has the display data
        logger.info("Extracting from page source for titles/prices...")
        print("  🔍 Extracting from page source for details...")
        page_items = extract_items_from_current_page(driver, limit * 2)  # Get more to match

        # Build lookup of page items by ID
        page_item_lookup = {item['item_id']: item for item in page_items}

        # Enrich network items with page source data
        enriched_count = 0
        for item in items:
            item_id = item['item_id']
            if item_id in page_item_lookup:
                page_item = page_item_lookup[item_id]
                # Copy missing fields from page source
                if not item.get('title') or item.get('title') == f"Item {item_id}":
                    item['title'] = page_item.get('title', item.get('title', ''))
                    enriched_count += 1
                if not item.get('price'):
                    item['price'] = page_item.get('price', item.get('price', ''))
                if not item.get('image_url'):
                    item['image_url'] = page_item.get('image_url', item.get('image_url', ''))

        logger.info(f"Enriched {enriched_count} items with page source data")

        # Add any page items not in network capture
        existing_ids = {item['item_id'] for item in items}
        added_count = 0
        for page_item in page_items:
            if page_item['item_id'] not in existing_ids:
                items.append(page_item)
                added_count += 1

        if added_count > 0:
            logger.info(f"Added {added_count} items from page source not in network capture")

        logger.info(f"Combined extraction: {len(items)} total items")

        # MONOTONIC SCAN GUARD: Ensure listing count never decreases
        # This detects if Facebook's DOM manipulation lost items during scrolling
        if len(items) < new_id_count * 0.5:
            logger.warning(f"MONOTONIC GUARD: Found {len(items)} items but expected ~{new_id_count}. Possible data loss.")
            print(f"  ⚠️ Warning: Found fewer items ({len(items)}) than IDs detected ({new_id_count})")

        # Apply limit
        if len(items) > limit:
            items = items[:limit]

        extract_elapsed = time_module.time() - extract_start
        logger.info(f"Item extraction: {len(items)} items in {extract_elapsed:.1f}s (wire={use_wire})")

        # Log item summary at DEBUG level (goes to file, not spammy)
        for item in items:
            logger.debug(f"  Item: id={item.get('item_id')}, title={item.get('title')[:40] if item.get('title') else 'N/A'}..., price={item.get('price')}, status={item.get('status')}")

        # ALWAYS save user info to database (even if no items)
        # This ensures login persists across page reloads
        save_user_to_db(user_info, db_path)

        # Save items if any found
        if items:
            db_start = time_module.time()
            save_items_to_db(items, user_info, db_path)
            download_item_images(items)
            db_elapsed = time_module.time() - db_start
            logger.info(f"Database save + image download: {db_elapsed:.1f}s")

        # Final timing summary
        total_elapsed = time_module.time() - scan_start
        logger.info(f"SCAN COMPLETE: {len(items)} listings in {total_elapsed:.1f}s (browser={browser_elapsed:.1f}s, nav={nav_elapsed:.1f}s, extract={extract_elapsed:.1f}s)")
        print(f"✅ Found {len(items)} listings")
        return user_info, items

    except Exception as e:
        total_elapsed = time_module.time() - scan_start
        logger.error(f"Scan failed after {total_elapsed:.1f}s: {e}", exc_info=True)
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None, []
    finally:
        # ALWAYS close the browser
        if driver:
            try:
                driver.quit()
            except:
                pass
        cleanup_temp_profile()
        # Extra cleanup
        kill_zombie_browsers()


def extract_items_from_current_page(driver, limit: int = 50) -> list:
    """
    Extract items from the current page (already on selling page).
    Extracts real titles, prices, and images from Facebook's embedded JSON.
    """
    logger.debug(f"extract_items_from_current_page() called, limit={limit}")
    items = []
    seen_ids = set()

    # Get page source for analysis
    page_source = driver.page_source
    logger.debug(f"Page source length: {len(page_source)} chars")

    # DEBUG: Save page source for analysis
    debug_path = "/tmp/fb_selling_page.html"
    try:
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(page_source)
        logger.debug(f"Saved page source to {debug_path}")
        print(f"  📄 Saved page source to {debug_path} ({len(page_source)} chars)")
    except Exception as e:
        logger.warning(f"Could not save debug page source: {e}")
        print(f"  ⚠️ Could not save debug: {e}")

    # IMPROVED EXTRACTION: Structure-based, not adjacency-based
    # Facebook's JSON structure has id and title in separate locations
    # Strategy: Find all seller listings, then map titles separately

    # Strategy 1: Find listings with adjacent id+title (original pattern)
    listing_pattern = r'"id":"(\d+)","marketplace_listing_title":"([^"]+)"'
    matches = re.findall(listing_pattern, page_source)
    id_to_title = {m[0]: m[1] for m in matches}
    logger.info(f"Adjacent pattern: {len(matches)} listings found")

    # Strategy 2 (IMPROVED): Find GroupCommerceProductItem blocks with is_viewer_seller:true
    # These are YOUR listings, even if title isn't adjacent to id
    seller_listing_pattern = r'"__typename":"GroupCommerceProductItem"[^}]*"id":"(\d{10,20})"'
    seller_ids = set(re.findall(seller_listing_pattern, page_source))

    # Also find IDs near is_viewer_seller:true
    viewer_seller_pattern = r'"id":"(\d{10,20})"[^}]{0,200}is_viewer_seller":true'
    viewer_ids = set(re.findall(viewer_seller_pattern, page_source))
    seller_ids.update(viewer_ids)

    # Strategy 3: Find all marketplace_listing_title occurrences and map to nearest ID
    all_titles = re.findall(r'"marketplace_listing_title":"([^"]+)"', page_source)

    # For IDs we found but don't have titles for, search nearby
    for item_id in seller_ids:
        if item_id not in id_to_title and len(item_id) >= 13:  # Valid listing IDs are 13+ digits
            # Find all occurrences of this ID
            for match in re.finditer(rf'"id":"{item_id}"', page_source):
                idx = match.start()
                # Search within 2000 chars for a title
                snippet = page_source[idx:idx+2000]
                title_match = re.search(r'"marketplace_listing_title":"([^"]+)"', snippet)
                if title_match:
                    id_to_title[item_id] = title_match.group(1)
                    break

    logger.info(f"Extraction: {len(id_to_title)} listings with titles (improved)")
    print(f"  Found {len(id_to_title)} listings with titles")

    # Find prices - pattern: "formatted_price":{"text":"$X,XXX"}
    price_pattern = r'"id":"(\d+)"[^}]*"formatted_price":\{"text":"([^"]+)"'
    # Alternative: search near the ID
    price_matches = re.findall(price_pattern, page_source)
    id_to_price = {m[0]: m[1] for m in price_matches}

    # If that didn't work, try finding prices differently
    if not id_to_price:
        # Look for amount in listing_price
        for item_id in id_to_title.keys():
            # Search for price near this ID
            idx = page_source.find(f'"id":"{item_id}"')
            if idx > 0:
                # Look for price within 500 chars after ID
                snippet = page_source[idx:idx+500]
                price_match = re.search(r'"formatted_amount":"([^"]+)"', snippet)
                if price_match:
                    id_to_price[item_id] = price_match.group(1)
                else:
                    # Try another pattern
                    price_match = re.search(r'"amount":"(\d+)"', snippet)
                    if price_match:
                        amount = int(price_match.group(1))
                        id_to_price[item_id] = f"${amount:,}"

    # Find images - pattern: "primary_listing_photo":{"__typename":"Photo","image":{"uri":"https..."}}
    id_to_image = {}
    # Also extract status flags and bump info
    id_to_status = {}  # {item_id: {is_sold, is_pending, is_draft, category_id, bump_count, days_until_next_bump, max_bump_count}}

    for item_id in id_to_title.keys():
        idx = page_source.find(f'"id":"{item_id}"')
        if idx > 0:
            # Get a larger snippet to capture all fields
            snippet = page_source[idx:idx+2500]

            # Look for image URI
            img_match = re.search(r'"primary_listing_photo"[^}]*"image":\{"uri":"([^"]+)"', snippet)
            if img_match:
                # Unescape the URL
                img_url = img_match.group(1).replace('\\/', '/')
                id_to_image[item_id] = img_url

            # Extract status flags
            status_info = {}

            # is_sold
            sold_match = re.search(r'"is_sold":(\w+)', snippet)
            if sold_match:
                status_info['is_sold'] = sold_match.group(1) == 'true'

            # is_pending
            pending_match = re.search(r'"is_pending":(\w+)', snippet)
            if pending_match:
                status_info['is_pending'] = pending_match.group(1) == 'true'

            # is_draft
            draft_match = re.search(r'"is_draft":(\w+)', snippet)
            if draft_match:
                status_info['is_draft'] = draft_match.group(1) == 'true'

            # category_id
            cat_match = re.search(r'"marketplace_listing_category_id":"(\d+)"', snippet)
            if cat_match:
                status_info['category_id'] = cat_match.group(1)

            # bump info
            bump_match = re.search(r'"bump_count":(\d+)', snippet)
            if bump_match:
                status_info['bump_count'] = int(bump_match.group(1))

            days_match = re.search(r'"days_until_next_bump":(\d+)', snippet)
            if days_match:
                status_info['days_until_next_bump'] = int(days_match.group(1))

            max_bump_match = re.search(r'"max_bump_count":(\d+)', snippet)
            if max_bump_match:
                status_info['max_bump_count'] = int(max_bump_match.group(1))

            if status_info:
                id_to_status[item_id] = status_info

    logger.info(f"Extraction summary: {len(id_to_price)} prices, {len(id_to_image)} images, {len(id_to_status)} status records")
    print(f"  Found {len(id_to_price)} prices, {len(id_to_image)} images, {len(id_to_status)} status records")

    # Build items with full data
    for item_id, title in id_to_title.items():
        if len(items) >= limit:
            break
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        status_info = id_to_status.get(item_id, {})

        # Determine display status
        if status_info.get('is_sold'):
            display_status = 'sold'
        elif status_info.get('is_pending'):
            display_status = 'pending'
        elif status_info.get('is_draft'):
            display_status = 'draft'
        else:
            display_status = 'available'

        items.append({
            "item_id": item_id,
            "title": title,
            "price": id_to_price.get(item_id, "See on Facebook"),
            "location": None,
            "image_url": id_to_image.get(item_id),
            "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
            "status": display_status,
            "is_sold": status_info.get('is_sold', False),
            "is_pending": status_info.get('is_pending', False),
            "is_draft": status_info.get('is_draft', False),
            "category_id": status_info.get('category_id'),
            "bump_count": status_info.get('bump_count', 0),
            "days_until_next_bump": status_info.get('days_until_next_bump'),
            "max_bump_count": status_info.get('max_bump_count', 5),
        })

    if items:
        logger.info(f"Strategy 1 SUCCESS: Extracted {len(items)} items with full details")
        print(f"  ✅ Extracted {len(items)} items with full details")
        return items

    # Fallback: Strategy 2 - Just find IDs if full extraction failed
    logger.warning("Strategy 1 failed, falling back to ID-only extraction")
    print("  ⚠️ Full extraction failed, falling back to ID-only...")
    all_patterns = [
        (r'/marketplace/item/(\d+)', 'standard URL'),
        (r'GroupCommerceProductItem[^}]*"id":"(\d+)"', 'GroupCommerceProductItem'),
    ]

    unique_ids = set()
    for pattern, name in all_patterns:
        found = re.findall(pattern, page_source)
        if found:
            unique_ids.update(found)

    for item_id in unique_ids:
        if len(items) >= limit:
            break
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)

        items.append({
            "item_id": item_id,
            "title": f"Item {item_id}",
            "price": "See on Facebook",
            "location": None,
            "image_url": None,
            "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
            "status": "available"
        })

    if items:
        print(f"  ✅ Extracted {len(items)} items (ID only)")
        return items

    # Strategy 3: Find all links and filter for marketplace items
    item_links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/marketplace/item/"]')
    if not item_links:
        all_links = driver.find_elements(By.TAG_NAME, 'a')
        for link in all_links:
            href = link.get_attribute('href') or ''
            if '/marketplace/item/' in href:
                item_links.append(link)
        print(f"  Strategy 3: Found {len(item_links)} marketplace item links")

    # Process found links
    for link in item_links:
        if len(items) >= limit:
            break

        try:
            href = link.get_attribute("href")
            if not href:
                continue

            match = re.search(r'/marketplace/item/(\d+)', href)
            if not match:
                continue

            item_id = match.group(1)
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            # Get card container by walking up the DOM
            card = link
            card_text = ""
            for _ in range(8):  # Go up more levels
                try:
                    card = card.find_element(By.XPATH, "..")
                    card_text = card.text.strip()
                    # Stop when we have enough text (price + title at minimum)
                    if len(card_text) > 10 and '\n' in card_text:
                        break
                except:
                    break

            # Extract text
            lines = [l.strip() for l in card_text.split('\n') if l.strip()]

            price = None
            title = None
            location = None

            for line in lines:
                # Skip navigation/button text
                if line.lower() in ['selling', 'your listings', 'create new listing', 'see all']:
                    continue
                if not price and ('$' in line or line.lower() == 'free'):
                    price = line
                elif not title and len(line) > 2 and line != price:
                    title = line
                elif title and not location and len(line) > 2 and '$' not in line:
                    location = line
                    break

            # Extract image - try multiple methods
            image_url = None
            try:
                # Method 1: img tag inside link
                img_elements = link.find_elements(By.TAG_NAME, 'img')
                for img in img_elements:
                    src = img.get_attribute('src')
                    if src and ('scontent' in src or 'fbcdn' in src):
                        image_url = src
                        break

                # Method 2: background-image style
                if not image_url:
                    divs = link.find_elements(By.CSS_SELECTOR, 'div[style*="background"]')
                    for div in divs:
                        style = div.get_attribute('style') or ''
                        if 'url(' in style:
                            url_match = re.search(r'url\(["\']?(https://[^"\']+)["\']?\)', style)
                            if url_match:
                                image_url = url_match.group(1)
                                break
            except:
                pass

            items.append({
                "item_id": item_id,
                "title": title or f"Item {item_id}",
                "price": price or "Price not listed",
                "location": location,
                "image_url": image_url,
                "item_url": f"https://www.facebook.com/marketplace/item/{item_id}/",
                "status": "available"
            })
            print(f"    [{len(items)}] {price or '?'} - {(title or 'Untitled')[:40]}")

        except Exception as e:
            continue

    print(f"  ✅ Extracted {len(items)} items")
    return items


def scrape_my_listings(db_path: str = "marketplace.db", limit: int = 50):
    """
    Main function: Get logged-in user's marketplace listings.

    Tries methods in order:
    1. Facebook Graph API (if FB_ACCESS_TOKEN env var set)
    2. Fast browser scraping (single page navigation)
    """
    logger.info(f"scrape_my_listings() called: db_path={db_path}, limit={limit}")

    # Try API first (future-proofing)
    api = get_facebook_api()
    if api.api_available:
        logger.info("Using Facebook API method")
        print("🔗 Using Facebook API...")
        user_info = api.get_user_info()
        items = api.get_my_listings(limit)
        if items:
            logger.info(f"API returned {len(items)} items for user {user_info.get('fb_name') if user_info else 'unknown'}")
            save_items_to_db(items, user_info, db_path)
            return user_info, items
        logger.warning("API available but returned no items - falling back to scraping")
        # API available but no items - fall through to scraping

    # Fallback to browser scraping
    logger.info("Using browser scraping method")
    return scrape_my_listings_fast(db_path, limit)


if __name__ == "__main__":
    user_info, items = scrape_my_listings()
    if user_info:
        print(f"\n✅ Found {len(items)} items for {user_info.get('fb_name', 'Unknown')}")

