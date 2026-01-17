#!/usr/bin/env python3
"""
CI Compliance Validator for Run Instructions
Fails build if forbidden patterns or incomplete commands are detected.

Part of the Canonical Run Matrix enforcement (v5.9 compliance).
"""

import sys
import re
from pathlib import Path

# Forbidden patterns that indicate incorrect/incomplete instructions
FORBIDDEN_PATTERNS = [
    # Wrong dashboard file
    (r"streamlit run dashboard\.py(?!\S)", "Wrong entrypoint: must use dashboard_integrated.py"),
]

# Patterns that are allowed ONLY if labeled as "alternative" or "simple" in nearby context
ALTERNATIVE_PATTERNS = [
    (r"streamlit run dashboard_integrated\.py\s*$", "Bare command without flags"),
    (r"streamlit run dashboard_integrated\.py\s*['\"`]", "Bare command without flags"),
]

# Keywords that indicate a pattern is an explicitly labeled alternative
ALTERNATIVE_LABELS = ["alternative", "simple", "shortcut", "quick start", "minimal"]

# Pattern that requires venv BEFORE pip install (checks line does NOT have venv before pip)
# This is a separate check - we look for pip install without venv in same command sequence
def check_pip_without_venv(content: str, path: str) -> list:
    """Check for pip install commands that don't have venv setup first."""
    issues = []
    # Match command sequences with pip install
    pip_pattern = r"(?:^|&&\s*|;\s*)pip install -r requirements\.txt"
    for match in re.finditer(pip_pattern, content, re.MULTILINE):
        # Get the context before this match (same line or command sequence)
        start = max(0, match.start() - 200)
        context = content[start:match.start()]
        # Check if venv activation is present before pip install
        if "venv" not in context and ".venv" not in context and "virtualenv" not in context:
            line_num = content[:match.start()].count('\n') + 1
            issues.append({
                'path': str(path),
                'line': line_num,
                'pattern': 'PIP_WITHOUT_VENV',
                'reason': 'pip install without venv/virtualenv activation',
                'matched': match.group(0)[:50]
            })
    return issues

# Required elements when streamlit run is mentioned (at least one must be present)
STREAMLIT_REQUIRED_ELEMENTS = [
    "--server.port",
    "8501",
]

# Files to scan
TARGET_EXTENSIONS = (".md", ".html", ".txt", ".rst")
EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".augment", "ci"}
# Files that are allowed to have examples/counterexamples
EXCLUDE_FILES = {"RULE_VIOLATION_ANALYSIS_INCOMPLETE_WORKFLOW.md"}


def fail(msg: str, path: str = None) -> None:
    """Print failure message and exit."""
    location = f" in {path}" if path else ""
    print(f"[COMPLIANCE FAILURE]{location}: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str, path: str = None) -> None:
    """Print warning message."""
    location = f" in {path}" if path else ""
    print(f"[WARNING]{location}: {msg}", file=sys.stderr)


def scan_file(path: Path) -> list:
    """Scan a file for compliance violations. Returns list of issues."""
    issues = []
    try:
        content = path.read_text(errors="ignore")
    except Exception as e:
        warn(f"Could not read file: {e}", str(path))
        return issues

    # Check for forbidden patterns (always fail)
    for pattern, reason in FORBIDDEN_PATTERNS:
        matches = list(re.finditer(pattern, content, re.MULTILINE))
        for match in matches:
            line_num = content[:match.start()].count('\n') + 1
            issues.append({
                'path': str(path),
                'line': line_num,
                'pattern': pattern,
                'reason': reason,
                'matched': match.group(0)[:50]
            })

    # Check for alternative patterns (fail only if NOT labeled as alternative)
    for pattern, reason in ALTERNATIVE_PATTERNS:
        matches = list(re.finditer(pattern, content, re.MULTILINE))
        for match in matches:
            line_num = content[:match.start()].count('\n') + 1
            # Check context around match for alternative labels
            start = max(0, match.start() - 200)
            end = min(len(content), match.end() + 50)
            context = content[start:end].lower()
            is_labeled = any(label in context for label in ALTERNATIVE_LABELS)
            if not is_labeled:
                issues.append({
                    'path': str(path),
                    'line': line_num,
                    'pattern': pattern,
                    'reason': f"{reason} - not labeled as alternative",
                    'matched': match.group(0)[:50]
                })

    # Check for pip install without venv
    issues.extend(check_pip_without_venv(content, path))

    # If file mentions "streamlit run dashboard_integrated", verify it has required elements
    if "streamlit run dashboard_integrated" in content:
        has_required = any(elem in content for elem in STREAMLIT_REQUIRED_ELEMENTS)
        if not has_required:
            issues.append({
                'path': str(path),
                'line': 0,
                'pattern': 'MISSING_REQUIRED',
                'reason': f"streamlit command missing required elements: {STREAMLIT_REQUIRED_ELEMENTS}",
                'matched': 'N/A'
            })

    return issues


def should_scan(path: Path) -> bool:
    """Check if file should be scanned."""
    # Skip excluded directories
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return False
    # Skip excluded files
    if path.name in EXCLUDE_FILES:
        return False
    # Only scan target extensions
    return path.suffix.lower() in TARGET_EXTENSIONS


def main():
    """Main entry point."""
    root = Path(".")
    all_issues = []
    scanned_count = 0

    print("[INFO] Scanning for run instruction compliance...")

    for file_path in root.rglob("*"):
        if file_path.is_file() and should_scan(file_path):
            scanned_count += 1
            issues = scan_file(file_path)
            all_issues.extend(issues)

    if scanned_count == 0:
        fail("No files scanned — compliance validator misconfigured")

    print(f"[INFO] Scanned {scanned_count} files")

    if all_issues:
        print(f"\n[COMPLIANCE FAILURES] Found {len(all_issues)} issues:\n", file=sys.stderr)
        for issue in all_issues:
            print(f"  ❌ {issue['path']}:{issue['line']}", file=sys.stderr)
            print(f"     Reason: {issue['reason']}", file=sys.stderr)
            print(f"     Matched: {issue['matched']}", file=sys.stderr)
            print(file=sys.stderr)
        sys.exit(1)

    print("[OK] Run instruction compliance validated ✅")
    sys.exit(0)


if __name__ == "__main__":
    main()

