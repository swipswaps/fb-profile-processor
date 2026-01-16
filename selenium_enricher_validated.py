#!/usr/bin/env python3
"""
Validated Selenium Enricher Functions

Provides extraction functions with built-in validation.
Wraps selenium_enricher_enhanced.py functions with validation logic.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from selenium_enricher_enhanced import (
    extract_profile_picture,
    extract_cover_photo,
    extract_join_date,
    extract_active_listings_count,
    extract_response_info,
    extract_seller_badges,
    extract_location,
)


@dataclass
class ExtractionReport:
    """Report of extraction results for validation"""
    fields_extracted: int = 0
    fields_total: int = 7
    critical_fields_present: List[str] = field(default_factory=list)
    optional_fields_present: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    
    def calculate_success_rate(self):
        self.success_rate = (self.fields_extracted / self.fields_total) * 100 if self.fields_total > 0 else 0


def extract_marketplace_info(driver) -> Dict:
    """
    Extract all marketplace info with validation tracking.
    
    Returns:
        Dictionary with extracted fields and _extraction_report
    """
    report = ExtractionReport()
    result = {}
    
    # Define critical vs optional fields
    critical_fields = ['fb_join_date', 'fb_picture_url']
    optional_fields = ['fb_active_listings_count', 'fb_response_rate', 
                       'fb_response_time', 'fb_seller_badges', 'fb_cover_url']
    
    # Extract join date (CRITICAL)
    join_date = extract_join_date(driver)
    result['fb_join_date'] = join_date
    if join_date:
        report.fields_extracted += 1
        report.critical_fields_present.append('fb_join_date')
    else:
        report.missing_fields.append('fb_join_date')
    
    # Extract active listings count (OPTIONAL)
    listings = extract_active_listings_count(driver)
    result['fb_active_listings_count'] = listings
    if listings is not None:
        report.fields_extracted += 1
        report.optional_fields_present.append('fb_active_listings_count')
    else:
        report.missing_fields.append('fb_active_listings_count')
    
    # Extract response info (OPTIONAL)
    response_rate, response_time = extract_response_info(driver)
    result['fb_response_rate'] = response_rate
    result['fb_response_time'] = response_time
    if response_rate:
        report.fields_extracted += 1
        report.optional_fields_present.append('fb_response_rate')
    else:
        report.missing_fields.append('fb_response_rate')
    if response_time:
        report.fields_extracted += 1
        report.optional_fields_present.append('fb_response_time')
    else:
        report.missing_fields.append('fb_response_time')
    
    # Extract seller badges (OPTIONAL)
    badges = extract_seller_badges(driver)
    result['fb_seller_badges'] = badges
    if badges:
        report.fields_extracted += 1
        report.optional_fields_present.append('fb_seller_badges')
    else:
        report.missing_fields.append('fb_seller_badges')
    
    # Extract profile picture (CRITICAL)
    picture_url = extract_profile_picture(driver)
    result['fb_picture_url'] = picture_url
    if picture_url:
        report.fields_extracted += 1
        report.critical_fields_present.append('fb_picture_url')
    else:
        report.missing_fields.append('fb_picture_url')
    
    # Extract cover photo (OPTIONAL)
    cover_url = extract_cover_photo(driver)
    result['fb_cover_url'] = cover_url
    if cover_url:
        report.fields_extracted += 1
        report.optional_fields_present.append('fb_cover_url')
    else:
        report.missing_fields.append('fb_cover_url')
    
    report.calculate_success_rate()
    result['_extraction_report'] = report
    
    return result


def validate_extraction_data(data: Dict) -> bool:
    """
    Validate that extracted data meets minimum requirements.
    
    Critical fields (MUST have at least one):
    - fb_join_date
    - fb_picture_url
    
    Returns:
        True if validation passes, False otherwise
    """
    critical_present = 0
    
    if data.get('fb_join_date'):
        critical_present += 1
    if data.get('fb_picture_url'):
        critical_present += 1
    
    # Must have at least one critical field
    if critical_present == 0:
        print("❌ VALIDATION FAILED: No critical fields extracted")
        return False
    
    # Check for obviously bad data
    join_date = data.get('fb_join_date', '')
    if join_date and len(str(join_date)) > 50:
        print(f"⚠️ WARNING: Join date suspiciously long: {join_date[:50]}...")
    
    return True

