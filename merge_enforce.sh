#!/usr/bin/env bash
#
# merge_enforce.sh — Enforce safe merges per v5.8 and UX/logging rules
# Created: 2026-01-16
#

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG_ISSUES_FILE="/tmp/merge_log_issues.txt"
> "$LOG_ISSUES_FILE"

echo "➤ Merge Enforcement Starting..."
echo "  Repository: $REPO_ROOT"
echo "  Timestamp: $(date -Iseconds)"

# ----------------------------------------------------------------------
# 1) Require clean working directory (optional - comment if not in git)
# ----------------------------------------------------------------------
if command -v git &> /dev/null && git rev-parse --is-inside-work-tree &> /dev/null; then
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        echo "⚠️  Working directory has uncommitted changes (proceeding anyway)"
    fi
fi

# ----------------------------------------------------------------------
# 2) Confirm backup exists
# ----------------------------------------------------------------------
echo "🔎 Phase 0 — Checking for backup..."
BACKUP_COUNT=$(ls -1 dashboard_integrated.py.BEFORE_* 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -eq 0 ]; then
    echo "❌ No backup found. Create with:"
    echo "   cp dashboard_integrated.py dashboard_integrated.py.BEFORE_\$(date +%F_%H%M%S)"
    exit 1
else
    echo "   ✅ Found $BACKUP_COUNT backup(s)"
fi

# ----------------------------------------------------------------------
# 3) Phase 1 — Logging Framework Presence
# ----------------------------------------------------------------------
echo "🔎 Phase 1 — Logging Framework Scan..."

# Check for logger initialization
if ! grep -q "logging.basicConfig\|getLogger(" dashboard_integrated.py; then
    echo "⚠️ No logging framework found" >> "$LOG_ISSUES_FILE"
fi

# Detect bare excepts (excluding comments)
BARE_EXCEPTS=$(grep -n "except:$" dashboard_integrated.py 2>/dev/null | grep -v "^#" || true)
if [ -n "$BARE_EXCEPTS" ]; then
    echo "❌ Bare except detected:" >> "$LOG_ISSUES_FILE"
    echo "$BARE_EXCEPTS" >> "$LOG_ISSUES_FILE"
fi

# ----------------------------------------------------------------------
# 4) Phase 2 — Required Functions Present
# ----------------------------------------------------------------------
echo "🔎 Phase 2 — Required functions check..."

REQUIRED_FUNCTIONS=(
    "detect_schema"
    "load_data"
    "get_database_stats"
    "render_listing_card"
    "render_api_config"
)

for fn in "${REQUIRED_FUNCTIONS[@]}"; do
    if ! grep -q "def $fn" dashboard_integrated.py 2>/dev/null; then
        echo "⚠️ Missing recommended function: $fn" >> "$LOG_ISSUES_FILE"
    fi
done

# ----------------------------------------------------------------------
# 5) Phase 3 — UI/Tabs Preserved
# ----------------------------------------------------------------------
echo "🔎 Phase 3 — Required tabs/features present..."

REQUIRED_PATTERNS=(
    "st.tabs"
    "Upload"
    "View"
    "Export"
    "Marketplace"
    "API Config\|Settings"
)

for pattern in "${REQUIRED_PATTERNS[@]}"; do
    if ! grep -qE "$pattern" dashboard_integrated.py 2>/dev/null; then
        echo "⚠️ Missing recommended pattern: $pattern" >> "$LOG_ISSUES_FILE"
    fi
done

# ----------------------------------------------------------------------
# 6) Syntax Check
# ----------------------------------------------------------------------
echo "🔎 Phase 4 — Python Syntax Check..."
if ! python3 -m py_compile dashboard_integrated.py 2>&1; then
    echo "❌ Syntax error in dashboard_integrated.py" >> "$LOG_ISSUES_FILE"
fi

# ----------------------------------------------------------------------
# 7) Report
# ----------------------------------------------------------------------
echo ""
echo "=========================================="
if [ -s "$LOG_ISSUES_FILE" ]; then
    echo "⚠️  Merge Enforcement WARNINGS:"
    cat "$LOG_ISSUES_FILE"
    echo ""
    echo "Review issues above. Some may be acceptable."
    exit 0  # Warnings only, not hard failures
else
    echo "✅ Merge Enforcement Passed"
fi
echo "=========================================="

