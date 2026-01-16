#!/usr/bin/env python3
"""
validate_logging.py — Logging and error compliance per v5.8

This validator:
1. Checks all .py files for logging compliance
2. Ensures functions have logging calls
3. Detects bare except: patterns
4. Fails CI if critical violations found

Usage:
    python validate_logging.py [files...]
    python validate_logging.py  # validates all .py files
"""

import ast
import sys
from pathlib import Path

# Files to skip (tests, migrations, etc.)
SKIP_PATTERNS = ['test_', 'conftest', '__pycache__', 'migrations']

# Logging function patterns to detect
LOGGING_ATTRS = {'debug', 'info', 'warning', 'error', 'critical', 'exception', 'log'}


class LoggingValidator(ast.NodeVisitor):
    """AST visitor to check logging compliance in functions."""

    def __init__(self, filename: str):
        self.filename = filename
        self.issues = []
        self.warnings = []

    def visit_FunctionDef(self, node):
        """Check each function for logging calls."""
        has_log = self._has_logging_call(node)

        # Only warn for substantial functions (more than 5 lines)
        if not has_log and len(node.body) > 5:
            self.warnings.append(
                f"  ⚠️  {self.filename}:{node.lineno} - function '{node.name}' has no logging"
            )

        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        """Check except handlers for bare excepts."""
        if node.type is None:
            # Bare except:
            has_log = self._has_logging_call(node)
            if not has_log:
                self.issues.append(
                    f"  ❌ {self.filename}:{node.lineno} - bare 'except:' without logging"
                )
        self.generic_visit(node)

    def _has_logging_call(self, node) -> bool:
        """Check if node contains any logging calls."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    if child.func.attr in LOGGING_ATTRS:
                        return True
                    # Check for logger.x() pattern
                    if isinstance(child.func.value, ast.Name):
                        if child.func.value.id in ('logger', 'logging', 'log'):
                            return True
        return False


def find_python_files(root: Path, specific_files: list = None) -> list:
    """Find Python files to validate."""
    if specific_files:
        return [Path(f) for f in specific_files if f.endswith('.py')]

    files = []
    for p in root.rglob("*.py"):
        # Skip patterns
        if any(skip in str(p) for skip in SKIP_PATTERNS):
            continue
        files.append(p)
    return files


def validate_file(file_path: Path) -> tuple:
    """Validate a single file. Returns (issues, warnings)."""
    try:
        code = file_path.read_text()
        tree = ast.parse(code, filename=str(file_path))
    except SyntaxError as e:
        return ([f"  ❌ {file_path}: Syntax error - {e}"], [])
    except Exception as e:
        return ([f"  ❌ {file_path}: Parse error - {e}"], [])

    validator = LoggingValidator(str(file_path))
    validator.visit(tree)

    return (validator.issues, validator.warnings)


def main():
    """Main validation entry point."""
    print("=" * 60)
    print("v5.8 Logging Compliance Validator")
    print("=" * 60)

    # Get files to validate
    root = Path.cwd()
    specific_files = sys.argv[1:] if len(sys.argv) > 1 else None
    files = find_python_files(root, specific_files)

    print(f"Scanning {len(files)} Python files...")

    all_issues = []
    all_warnings = []

    for file in files:
        issues, warnings = validate_file(file)
        all_issues.extend(issues)
        all_warnings.extend(warnings)

    # Report
    print("")
    if all_warnings:
        print(f"⚠️  {len(all_warnings)} Warning(s):")
        for w in all_warnings[:10]:  # Limit output
            print(w)
        if len(all_warnings) > 10:
            print(f"  ... and {len(all_warnings) - 10} more")

    if all_issues:
        print(f"\n❌ {len(all_issues)} Critical Issue(s):")
        for issue in all_issues:
            print(issue)
        print("\n🚨 Logging Compliance FAILED")
        sys.exit(1)

    print("\n✅ Logging Compliance Passed")
    sys.exit(0)


if __name__ == "__main__":
    main()

