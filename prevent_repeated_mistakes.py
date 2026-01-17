#!/usr/bin/env python3
"""
Mistake Prevention Framework for Augment Code LLM

This framework automatically detects patterns that lead to repeated mistakes
and enforces correct behavior.

Rules enforced:
- "Where is X?" → Navigate + Show + Prove (not explain)
- "I don't see X" → Navigate + Show + Prove (not instruct)
- UI questions → Screenshot + OCR (not claims)
- Obvious actions → Do them (not ask permission)
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    """Types of actions the LLM should take"""
    NAVIGATE = "navigate"
    SCREENSHOT = "screenshot"
    OCR = "ocr"
    EXECUTE = "execute"
    EXPLAIN = "explain"
    ASK = "ask"


class MistakePattern(Enum):
    """Common mistake patterns to detect"""
    EXPLAIN_INSTEAD_OF_SHOW = "explain_instead_of_show"
    ASK_INSTEAD_OF_DO = "ask_instead_of_do"
    CLAIM_WITHOUT_PROOF = "claim_without_proof"
    INCOMPLETE_WORKFLOW = "incomplete_workflow"
    TOOL_UNDERUTILIZATION = "tool_underutilization"


@dataclass
class UserIntent:
    """Parsed user intent with required actions"""
    question: str
    intent_type: str  # "show_me", "explain", "do_action", "verify"
    required_actions: List[ActionType]
    tools_needed: List[str]
    success_criteria: str


class IntentDetector:
    """Detects user intent and maps to required actions"""

    # Patterns that indicate "show me" intent (not "explain")
    SHOW_ME_PATTERNS = [
        r"where\s+is",
        r"show\s+me",
        r"i\s+don'?t\s+see",
        r"can'?t\s+find",
        r"display",
        r"view",
        r"see\s+the",
    ]

    # Patterns that indicate action intent (not explanation)
    ACTION_PATTERNS = [
        r"update",
        r"add",
        r"fix",
        r"implement",
        r"integrate",
        r"create",
        r"make",
        r"change",
    ]

    # Patterns that indicate verification intent
    VERIFY_PATTERNS = [
        r"verify",
        r"check\s+if",
        r"is\s+it",
        r"does\s+it",
        r"working",
    ]

    @classmethod
    def detect_intent(cls, user_message: str) -> UserIntent:
        """
        Detect user intent and determine required actions.
        
        Args:
            user_message: The user's question/request
            
        Returns:
            UserIntent with required actions
        """
        message_lower = user_message.lower()

        # Check for "show me" intent
        if any(re.search(pattern, message_lower) for pattern in cls.SHOW_ME_PATTERNS):
            return UserIntent(
                question=user_message,
                intent_type="show_me",
                required_actions=[
                    ActionType.NAVIGATE,
                    ActionType.SCREENSHOT,
                    ActionType.OCR,
                ],
                tools_needed=["selenium", "screenshot", "ocr"],
                success_criteria="User can SEE the thing they asked about"
            )

        # Check for action intent
        if any(re.search(pattern, message_lower) for pattern in cls.ACTION_PATTERNS):
            return UserIntent(
                question=user_message,
                intent_type="do_action",
                required_actions=[
                    ActionType.EXECUTE,
                    ActionType.SCREENSHOT,
                    ActionType.OCR,
                ],
                tools_needed=["code_execution", "screenshot", "ocr"],
                success_criteria="Action completed AND verified with proof"
            )

        # Check for verification intent
        if any(re.search(pattern, message_lower) for pattern in cls.VERIFY_PATTERNS):
            return UserIntent(
                question=user_message,
                intent_type="verify",
                required_actions=[
                    ActionType.NAVIGATE,
                    ActionType.SCREENSHOT,
                    ActionType.OCR,
                ],
                tools_needed=["selenium", "screenshot", "ocr"],
                success_criteria="Verification shown with evidence"
            )

        # Default to explanation (but still check if action is obvious)
        return UserIntent(
            question=user_message,
            intent_type="explain",
            required_actions=[ActionType.EXPLAIN],
            tools_needed=[],
            success_criteria="Question answered with examples/evidence"
        )


class MistakeDetector:
    """Detects when LLM is about to make a repeated mistake"""

    # Phrases that indicate LLM is about to explain instead of show
    EXPLAIN_INDICATORS = [
        "to see it",
        "you should see",
        "it's located",
        "you can find",
        "click on",
        "select from",
        "navigate to",
    ]

    # Phrases that indicate LLM is about to ask instead of do
    ASK_INDICATORS = [
        "would you like me to",
        "should i",
        "do you want me to",
        "shall i",
    ]

    # Phrases that indicate claims without proof
    CLAIM_INDICATORS = [
        "you should see",
        "this will show",
        "the dashboard displays",
        "you can see",
    ]

    @classmethod
    def detect_mistake(cls, llm_response: str, intent: UserIntent) -> Optional[MistakePattern]:
        """
        Detect if LLM response contains a mistake pattern.
        
        Args:
            llm_response: The LLM's proposed response
            intent: The detected user intent
            
        Returns:
            MistakePattern if detected, None otherwise
        """
        response_lower = llm_response.lower()

        # Check for explain instead of show
        if intent.intent_type == "show_me":
            if any(phrase in response_lower for phrase in cls.EXPLAIN_INDICATORS):
                return MistakePattern.EXPLAIN_INSTEAD_OF_SHOW

        # Check for ask instead of do
        if intent.intent_type == "do_action":
            if any(phrase in response_lower for phrase in cls.ASK_INDICATORS):
                return MistakePattern.ASK_INSTEAD_OF_DO

        # Check for claims without proof
        if any(phrase in response_lower for phrase in cls.CLAIM_INDICATORS):
            if "screenshot" not in response_lower and "ocr" not in response_lower:
                return MistakePattern.CLAIM_WITHOUT_PROOF

        return None


class ActionEnforcer:
    """Enforces that required actions are actually taken"""

    @staticmethod
    def create_action_plan(intent: UserIntent) -> Dict:
        """
        Create detailed action plan based on intent.
        
        Args:
            intent: Detected user intent
            
        Returns:
            Dictionary with step-by-step actions
        """
        plan = {
            "intent": intent.intent_type,
            "steps": [],
            "verification": [],
        }

        if intent.intent_type == "show_me":
            plan["steps"] = [
                {
                    "action": "navigate",
                    "description": "Navigate to the UI/page where item is located",
                    "code": "driver.get(url); time.sleep(3)",
                },
                {
                    "action": "locate",
                    "description": "Find the element user asked about",
                    "code": "element = driver.find_element(By...)",
                },
                {
                    "action": "scroll",
                    "description": "Scroll element into view",
                    "code": "driver.execute_script('arguments[0].scrollIntoView()', element)",
                },
                {
                    "action": "screenshot",
                    "description": "Take screenshot showing the element",
                    "code": "driver.save_screenshot('/tmp/proof.png')",
                },
                {
                    "action": "ocr",
                    "description": "Run OCR to verify element is visible",
                    "code": "text = pytesseract.image_to_string(Image.open('/tmp/proof.png'))",
                },
            ]
            plan["verification"] = [
                "Screenshot exists",
                "OCR output contains expected text",
                "Element is visible in screenshot",
            ]

        elif intent.intent_type == "do_action":
            plan["steps"] = [
                {
                    "action": "implement",
                    "description": "Make the requested change",
                    "code": "# Implementation code here",
                },
                {
                    "action": "test",
                    "description": "Test the implementation",
                    "code": "# Run tests",
                },
                {
                    "action": "screenshot",
                    "description": "Screenshot showing it works",
                    "code": "driver.save_screenshot('/tmp/proof.png')",
                },
                {
                    "action": "verify",
                    "description": "Verify with OCR/data check",
                    "code": "# Verification code",
                },
            ]
            plan["verification"] = [
                "Implementation complete",
                "Tests pass",
                "Screenshot shows feature working",
                "Verification confirms success",
            ]

        return plan

    @staticmethod
    def generate_code_template(intent: UserIntent) -> str:
        """
        Generate code template for required actions.
        
        Args:
            intent: Detected user intent
            
        Returns:
            Python code template
        """
        if intent.intent_type == "show_me":
            return '''
# REQUIRED: Show user what they asked about

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pytesseract
from PIL import Image
import time

# Step 1: Navigate to location
driver.get("URL_HERE")
time.sleep(3)

# Step 2: Find element
wait = WebDriverWait(driver, 10)
element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "SELECTOR_HERE")))

# Step 3: Scroll into view
driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
time.sleep(1)

# Step 4: Verify visible
assert element.is_displayed(), "Element not visible!"

# Step 5: Screenshot
driver.save_screenshot("/tmp/proof.png")

# Step 6: OCR
img = Image.open("/tmp/proof.png")
text = pytesseract.image_to_string(img)
print("=== OCR OUTPUT ===")
print(text)

# Step 7: Verify expected text
assert "EXPECTED_TEXT" in text, "Expected text not found in screenshot"

print("✅ VERIFIED: User can see [ITEM]")
# Display: code /tmp/proof.png
'''

        elif intent.intent_type == "do_action":
            return '''
# REQUIRED: Do the action (don't ask permission)

# Step 1: Implement the change
# ... implementation code ...

# Step 2: Test it works
# ... test code ...

# Step 3: Screenshot proof
driver.save_screenshot("/tmp/proof.png")

# Step 4: OCR verify
img = Image.open("/tmp/proof.png")
text = pytesseract.image_to_string(img)

# Step 5: Report completion with proof
print("✅ COMPLETED: [ACTION]")
print("Evidence: /tmp/proof.png")
print("OCR confirms: [VERIFICATION]")
'''


class WorkflowValidator:
    """Validates that complete workflows are executed"""

    @staticmethod
    def validate_completion(intent: UserIntent, actions_taken: List[str]) -> Tuple[bool, str]:
        """
        Validate that all required actions were taken.
        
        Args:
            intent: The detected intent
            actions_taken: List of actions LLM actually took
            
        Returns:
            (is_complete, missing_actions_message)
        """
        required = set(a.value for a in intent.required_actions)
        taken = set(actions_taken)

        missing = required - taken

        if missing:
            return False, f"Incomplete workflow. Missing: {', '.join(missing)}"

        return True, "Workflow complete"


# Example usage and tests
def test_framework():
    """Test the mistake prevention framework"""

    print("=" * 80)
    print("MISTAKE PREVENTION FRAMEWORK TESTS")
    print("=" * 80)

    # Test 1: "Where is" question
    print("\n1. Testing 'Where is' question...")
    user_message = "Where is enriched data?"
    intent = IntentDetector.detect_intent(user_message)
    print(f"   Intent: {intent.intent_type}")
    print(f"   Required actions: {[a.value for a in intent.required_actions]}")
    print(f"   Tools needed: {intent.tools_needed}")

    # Test 2: Detect explain-instead-of-show mistake
    print("\n2. Testing mistake detection...")
    bad_response = "Your data is in test_profiles.db. To see it, select from dropdown."
    mistake = MistakeDetector.detect_mistake(bad_response, intent)
    if mistake:
        print(f"   ❌ Mistake detected: {mistake.value}")
    else:
        print(f"   ✅ No mistake detected")

    # Test 3: Create action plan
    print("\n3. Testing action plan generation...")
    plan = ActionEnforcer.create_action_plan(intent)
    print(f"   Steps: {len(plan['steps'])}")
    for i, step in enumerate(plan['steps'], 1):
        print(f"      {i}. {step['action']}: {step['description']}")

    # Test 4: Validate workflow
    print("\n4. Testing workflow validation...")
    incomplete_actions = ["navigate", "screenshot"]  # Missing OCR
    is_complete, message = WorkflowValidator.validate_completion(intent, incomplete_actions)
    print(f"   Complete: {is_complete}")
    print(f"   Message: {message}")

    print("\n" + "=" * 80)
    print("✅ All tests complete")


if __name__ == "__main__":
    print(__doc__)
    test_framework()
