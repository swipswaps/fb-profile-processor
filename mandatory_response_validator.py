#!/usr/bin/env python3
"""
Mandatory Response Validator - Prevents LLM from Making Repeated Mistakes

This validator MUST run before LLM sends ANY response.
If validation fails, response is BLOCKED and corrected.

Critical Rules Enforced:
- Rule 27: Screenshot claims require OCR
- Rule 31: Proceed with obvious steps
- Rule 22: Complete workflow testing

Usage:
    Before LLM sends response:
    validator = ResponseValidator(user_message, llm_response, context)
    is_valid, corrections = validator.validate()
    if not is_valid:
        # Block response
        # Apply corrections
        # Re-generate with correct approach
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of response validation"""
    is_valid: bool
    violations: List[str]
    required_corrections: List[str]
    blocking_severity: str  # "critical", "warning", "info"


class ResponseValidator:
    """Validates LLM responses before they're sent to user"""
    
    # Critical phrases that indicate violations
    FORBIDDEN_PHRASES = {
        "Rule 27 (Screenshot Claims)": [
            r"you should see",
            r"the dashboard (will|should) (show|display)",
            r"you (will|can) see",
            r"this (will|should) display",
        ],
        "Rule 31 (Asking Instead of Doing)": [
            r"would you like me to",
            r"should i (integrate|add|update|fix|implement)",
            r"do you want me to",
            r"shall i proceed",
        ],
        "Explain Instead of Show": [
            r"to see (it|this|that), (click|select|navigate)",
            r"you can find (it|this) (in|at|by)",
            r"it'?s located (in|at)",
        ],
    }
    
    # Required elements for different question types
    REQUIRED_ELEMENTS = {
        "where_is": ["navigate", "screenshot", "ocr"],
        "show_me": ["navigate", "screenshot", "ocr"],
        "dont_see": ["navigate", "screenshot", "ocr"],
        "update": ["implement", "test", "verify"],
        "fix": ["implement", "test", "verify"],
        "add": ["implement", "test", "verify"],
    }
    
    def __init__(self, user_message: str, llm_response: str, context: Dict = None):
        """
        Initialize validator.
        
        Args:
            user_message: The user's question/request
            llm_response: The LLM's proposed response
            context: Additional context (tools available, etc.)
        """
        self.user_message = user_message.lower()
        self.llm_response = llm_response.lower()
        self.context = context or {}
        
    def validate(self) -> ValidationResult:
        """
        Validate response against all rules.
        
        Returns:
            ValidationResult with violations and corrections
        """
        violations = []
        corrections = []
        severity = "info"
        
        # Check for forbidden phrases
        phrase_violations = self._check_forbidden_phrases()
        if phrase_violations:
            violations.extend(phrase_violations)
            severity = "critical"
        
        # Check for missing required elements
        element_violations = self._check_required_elements()
        if element_violations:
            violations.extend(element_violations)
            corrections.extend(self._generate_corrections(element_violations))
            severity = "critical"
        
        # Check for screenshot claims without OCR
        screenshot_violations = self._check_screenshot_claims()
        if screenshot_violations:
            violations.extend(screenshot_violations)
            corrections.append("MUST: Take screenshot, run OCR, show output, THEN make claims")
            severity = "critical"
        
        is_valid = len(violations) == 0
        
        return ValidationResult(
            is_valid=is_valid,
            violations=violations,
            required_corrections=corrections,
            blocking_severity=severity
        )
    
    def _check_forbidden_phrases(self) -> List[str]:
        """Check if response contains forbidden phrases"""
        violations = []
        
        for rule, patterns in self.FORBIDDEN_PHRASES.items():
            for pattern in patterns:
                if re.search(pattern, self.llm_response):
                    violations.append(
                        f"{rule} violation: Found '{pattern}' in response"
                    )
        
        return violations
    
    def _check_required_elements(self) -> List[str]:
        """Check if response has required elements for question type"""
        violations = []
        
        # Determine question type
        question_type = None
        if re.search(r"where\s+is", self.user_message):
            question_type = "where_is"
        elif re.search(r"show\s+me", self.user_message):
            question_type = "show_me"
        elif re.search(r"don'?t\s+see", self.user_message):
            question_type = "dont_see"
        elif re.search(r"update|add|fix|implement", self.user_message):
            question_type = "update"
        
        if not question_type:
            return []
        
        # Check for required elements
        required = self.REQUIRED_ELEMENTS.get(question_type, [])
        missing = []
        
        for element in required:
            if element not in self.llm_response:
                missing.append(element)
        
        if missing:
            violations.append(
                f"Missing required elements for '{question_type}' question: {', '.join(missing)}"
            )
        
        return violations
    
    def _check_screenshot_claims(self) -> List[str]:
        """Check for screenshot/UI claims without OCR proof"""
        violations = []
        
        # Phrases that make claims about UI
        ui_claim_patterns = [
            r"you (will|should|can) see",
            r"(will|should) display",
            r"shows? (the|a|an)",
        ]
        
        has_ui_claim = any(
            re.search(pattern, self.llm_response)
            for pattern in ui_claim_patterns
        )
        
        if has_ui_claim:
            # Check if OCR is mentioned
            has_ocr = "ocr" in self.llm_response or "pytesseract" in self.llm_response
            has_screenshot = "screenshot" in self.llm_response
            
            if not (has_ocr and has_screenshot):
                violations.append(
                    "Rule 27 violation: Making UI claims without screenshot + OCR proof"
                )
        
        return violations
    
    def _generate_corrections(self, violations: List[str]) -> List[str]:
        """Generate specific corrections for violations"""
        corrections = []
        
        for violation in violations:
            if "where_is" in violation or "show_me" in violation:
                corrections.append(
                    "REQUIRED: Navigate to location → Screenshot → OCR → Show user"
                )
            elif "update" in violation or "add" in violation:
                corrections.append(
                    "REQUIRED: Implement change → Test → Screenshot → Verify → Report"
                )
        
        return corrections


class AutoCorrector:
    """Automatically corrects responses that fail validation"""
    
    @staticmethod
    def correct_where_is_response(user_message: str) -> str:
        """
        Generate correct response for 'where is' questions.
        
        Args:
            user_message: The user's question
            
        Returns:
            Corrected response template
        """
        return f'''
CORRECTED RESPONSE for: "{user_message}"

Step 1: Navigate to location
```python
driver.get("http://localhost:8501")
time.sleep(3)
```

Step 2: Locate element
```python
# Find the item user asked about
element = driver.find_element(By.CSS_SELECTOR, "SELECTOR")
driver.execute_script("arguments[0].scrollIntoView()", element)
```

Step 3: Screenshot
```python
driver.save_screenshot("/tmp/proof.png")
```

Step 4: OCR
```python
import pytesseract
from PIL import Image
text = pytesseract.image_to_string(Image.open("/tmp/proof.png"))
print("=== OCR OUTPUT ===")
print(text)
```

Step 5: Verify and show user
```python
if "EXPECTED_TEXT" in text:
    print("✅ VERIFIED: User can see [ITEM]")
    # Display: code /tmp/proof.png
```

CRITICAL: Do NOT explain where it is. SHOW where it is.
'''
    
    @staticmethod
    def correct_update_response(user_message: str) -> str:
        """
        Generate correct response for 'update/add/fix' requests.
        
        Args:
            user_message: The user's request
            
        Returns:
            Corrected response template
        """
        return f'''
CORRECTED RESPONSE for: "{user_message}"

Step 1: Implement the change
```python
# Make the requested change
# ... implementation code ...
```

Step 2: Test
```python
# Verify it works
# ... test code ...
```

Step 3: Screenshot proof
```python
driver.save_screenshot("/tmp/proof.png")
```

Step 4: Verify with OCR
```python
text = pytesseract.image_to_string(Image.open("/tmp/proof.png"))
assert "EXPECTED_RESULT" in text
```

Step 5: Report completion
```
✅ COMPLETED: [Change description]
Evidence: /tmp/proof.png
Verification: [OCR confirmation]
```

CRITICAL: Do NOT ask "Would you like me to...". JUST DO IT.
'''


def validate_and_correct_response(user_message: str, llm_response: str) -> Tuple[bool, str]:
    """
    Main validation function - call before sending ANY response.
    
    Args:
        user_message: User's question/request
        llm_response: LLM's proposed response
        
    Returns:
        (is_valid, corrected_response_or_original)
    """
    validator = ResponseValidator(user_message, llm_response)
    result = validator.validate()
    
    if result.is_valid:
        return True, llm_response
    
    # Response is invalid - generate correction
    print("=" * 80)
    print("❌ RESPONSE VALIDATION FAILED")
    print("=" * 80)
    print(f"Violations ({len(result.violations)}):")
    for violation in result.violations:
        print(f"  • {violation}")
    print(f"\nRequired corrections ({len(result.required_corrections)}):")
    for correction in result.required_corrections:
        print(f"  • {correction}")
    print("=" * 80)
    
    # Generate corrected response
    if "where is" in user_message.lower() or "show me" in user_message.lower():
        corrected = AutoCorrector.correct_where_is_response(user_message)
    elif any(word in user_message.lower() for word in ["update", "add", "fix", "implement"]):
        corrected = AutoCorrector.correct_update_response(user_message)
    else:
        corrected = llm_response + "\n\n⚠️ VALIDATION WARNING: " + "; ".join(result.violations)
    
    return False, corrected


# Integration example
def example_usage():
    """Example of how to use the validator"""
    
    print("EXAMPLE 1: 'Where is' question")
    print("-" * 80)
    
    user_msg = "Where is enriched data?"
    
    # Bad response (will fail validation)
    bad_response = "Your data is in test_profiles.db. To see it, select from dropdown."
    
    is_valid, response = validate_and_correct_response(user_msg, bad_response)
    print(f"Valid: {is_valid}")
    if not is_valid:
        print("Corrected response:")
        print(response)
    
    print("\n" + "=" * 80)
    print("EXAMPLE 2: 'Update' request")
    print("-" * 80)
    
    user_msg2 = "Update the app to export as SQL"
    
    # Bad response (will fail validation)
    bad_response2 = "Would you like me to integrate SQL export?"
    
    is_valid2, response2 = validate_and_correct_response(user_msg2, bad_response2)
    print(f"Valid: {is_valid2}")
    if not is_valid2:
        print("Corrected response:")
        print(response2)


if __name__ == "__main__":
    print(__doc__)
    print("\n")
    example_usage()
