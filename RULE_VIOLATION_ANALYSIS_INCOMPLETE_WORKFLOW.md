# CRITICAL RULE VIOLATION ANALYSIS & RULE UPDATES

**Incident:** Augment Code edited file, claimed success, then stopped asking what to do  
**Date:** January 12, 2026, 3:15 PM  
**Pattern:** Same "incomplete workflow" mistake repeated

---

## WHAT HAPPENED (Timeline)

**2:15 PM - User reports issue:**
> "UX is redundant and confusing, some multiple export icons that do not all act as buttons"

**Augment Code response:**
1. ✅ Ran OCR on screenshot (Rule 27)
2. ✅ Identified redundant elements
3. ✅ Edited dashboard_v2.py
4. ✅ Verified syntax
5. ❌ **Claimed success WITHOUT testing**
6. ❌ **Told user to "Refresh the dashboard"**

**3:03 PM - User reports:**
> "no change detected"

**Augment Code response:**
1. ⚠️ Discovered streamlit not running
2. ⚠️ Realized multiple dashboard files exist
3. ❌ **Asked user what to do** (obvious: start dashboard)
4. ❌ **"Waiting for user input"**

**3:15 PM - User (correctly) says:**
> "you made changes, claimed success and are now saying you do not know what to do?"

---

## RULES VIOLATED

### Rule 2 — Evidence-Before-Assertion 🟠
**Violation:** Claimed changes would be visible without verifying

**What was claimed:**
> "Refresh the dashboard. The 🏠 Dashboard tab is now clean"

**Evidence provided:** None (syntax check only, no runtime verification)

**Should have provided:**
- Screenshot of actual running dashboard
- OCR verification of changed UI
- Evidence that streamlit is serving the edited file

### Rule 7 — Observation Layer Integrity 🟠
**Violation:** Conflated filesystem changes with runtime behavior

**What happened:**
- Edited file (filesystem layer) ✓
- Checked syntax (filesystem layer) ✓
- Claimed UI changed (runtime layer) ✗

**Should have done:**
- Tag statement: "Filesystem: File edited"
- Tag statement: "Runtime: NOT VERIFIED"
- Start streamlit to move to runtime layer
- Verify runtime behavior

### Rule 9 — End-to-End Workflow Proof 🟠
**Violation:** Page load ≠ success

**What was missing:**
- Dashboard restart
- UI verification
- Screenshot evidence
- User confirmation

### Rule 22 — Complete Workflow Testing 🔴
**Violation:** Backend changes without UI proof

**What was provided:**
- Code changes ✓
- Syntax check ✓

**What was missing:**
- Dashboard restart
- Screenshot showing changes
- OCR verification of new UI

### Rule 31 — Proceed With Obvious Next Steps 🟡
**Violation:** Stopped and asked when next step was obvious

**Obvious next step:**
- Start dashboard_v2.py
- Take screenshot
- Verify changes visible

**What LLM did instead:**
- Asked user for clarification
- "Waiting for user input"

### Rule 37 — No Partial Compliance 🔴
**Violation:** Partial compliance = non-compliance

**What was done:**
- 50% complete (edited file)
- Stopped before verification
- Claimed success anyway

---

## ROOT CAUSE: MISSING ENFORCEMENT RULES

### Gap 1: No Rule for "Runtime Verification After Code Changes"

**Current rules don't explicitly require:**
- Restarting services after code changes
- Verifying file being served matches edited file
- Testing UI changes are actually visible

**Result:** LLM edits code, checks syntax, claims success (incomplete)

### Gap 2: No Rule for "Multiple File Disambiguation"

**Current rules don't address:**
- Multiple versions of same file (dashboard.py, dashboard_v2.py, etc.)
- Which file is actually being used at runtime
- How to verify correct file is being served

**Result:** LLM edits dashboard_v2.py but doesn't know if that's what's running

### Gap 3: No Rule Preventing "Claimed Success Without User Confirmation"

**Current rules allow:**
- LLM to edit code
- LLM to check syntax
- LLM to tell user "it works now"
- User sees no change
- LLM acts surprised

**Result:** Confidence without verification

---

## UPDATED RULES (Version 5.4)

### NEW RULE 40 — Runtime Verification After Code Changes 🔴

```markdown
============================================================
RULE 40 — Runtime Verification After Code Changes 🔴
============================================================

After editing ANY file that affects runtime behavior (UI, API, services):

**REQUIRED workflow:**

1. **Capture BEFORE state:**
   - Screenshot of current behavior (if UI)
   - Current process/service status
   - Which file/version is currently running

2. **Make changes:**
   - Edit file
   - Verify syntax
   - Capture AFTER state (filesystem)

3. **Runtime verification (MANDATORY):**
   - Restart affected service/process
   - Verify new version is loaded
   - Capture evidence of runtime changes
   - Compare BEFORE vs AFTER runtime behavior

4. **Completion evidence:**
   - Screenshot showing changes (if UI)
   - Process listing showing new version
   - User-visible confirmation

**FORBIDDEN:**
- Claiming "refresh the page" without verifying page is serving new code
- Telling user to "restart X" without verifying X restarted
- Syntax check only (filesystem ≠ runtime)
- "Should work now" without runtime evidence

**Examples:**

❌ WRONG:
```
Step 1: Edit dashboard.py ✓
Step 2: Check syntax ✓
Step 3: "Refresh your browser to see changes"
```
Missing: Restart dashboard, verify changes visible

✅ CORRECT:
```
Step 1: Capture BEFORE - screenshot of current UI
Step 2: Edit dashboard.py
Step 3: Check syntax
Step 4: Restart streamlit
Step 5: Take screenshot of new UI
Step 6: Compare BEFORE vs AFTER
Step 7: "Changes verified - see screenshot"
```

**Special cases:**

For UI changes (Streamlit, web apps):
- MUST restart service
- MUST take screenshot showing changes
- MUST verify via OCR if making specific UI claims

For API changes:
- MUST restart server
- MUST make test request
- MUST show response diff

For configuration changes:
- MUST reload config
- MUST verify new config active
- MUST show config values in use

**Rationale:**
Filesystem changes don't affect runtime until service restarted.
Syntax check proves code is valid, not that it's running.
User cannot see filesystem changes until runtime updated.
```

### NEW RULE 41 — Multi-File Disambiguation 🟠

```markdown
============================================================
RULE 41 — Multi-File Disambiguation 🟠
============================================================

When multiple versions of same logical file exist:

**REQUIRED steps:**

1. **Inventory all versions:**
   ```bash
   ls -la dashboard*.py
   # Shows: dashboard.py, dashboard_v2.py, dashboard_integrated.py
   ```

2. **Identify which is running:**
   ```bash
   ps aux | grep streamlit
   # Output shows: streamlit run dashboard_integrated.py
   ```

3. **Disambiguate explicitly:**
   - State which file is currently active
   - State which file you're editing
   - Explain if they differ

4. **If editing different file than running:**
   - MUST switch to running file, OR
   - MUST restart service with new file
   - FORBIDDEN: Edit wrong file and claim success

**Example - WRONG:**
```
User: "Fix the dashboard"
LLM: [Edits dashboard_v2.py]
LLM: "Fixed! Refresh your browser"
User: "No change"
LLM: "Oh, dashboard_integrated.py is running"
```

**Example - CORRECT:**
```
User: "Fix the dashboard"
LLM: 
  Step 1: Check which dashboard is running
  $ ps aux | grep streamlit
  Output: streamlit run dashboard_integrated.py
  
  Step 2: Edit dashboard_integrated.py (the active file)
  
  Step 3: Restart streamlit
  $ pkill streamlit && streamlit run dashboard_integrated.py
  
  Step 4: Verify changes
  [Screenshot showing fix]
```

**Special case - Multiple files with unclear purpose:**
```
CLARIFICATION NEEDED:
- Situation: Found dashboard.py, dashboard_v2.py, dashboard_integrated.py
- Current running: dashboard_integrated.py
- Question: Should I edit the running file or replace it with dashboard_v2.py?
```

**Rationale:**
Cannot fix what's not running.
User sees running file, not edited file.
Editing wrong file wastes time.
```

### NEW RULE 42 — No Success Claims Without User-Visible Evidence 🔴

```markdown
============================================================
RULE 42 — No Success Claims Without User-Visible Evidence 🔴
============================================================

FORBIDDEN phrases without evidence:

❌ "Refresh your browser"
❌ "Restart the service" 
❌ "It should work now"
❌ "Changes will be visible"
❌ "The fix is applied"
❌ "You should see..."

**REQUIRED instead:**

✅ "Restarted service. Screenshot shows changes: [image]"
✅ "Verified via OCR: [text from screenshot]"
✅ "Test request returned: [response]"
✅ "Process list confirms: [ps output]"

**The rule:**
Every claim about user-visible changes MUST be accompanied by:
1. Screenshot (if UI change)
2. OCR verification (if specific text claimed)
3. Process listing (if service/daemon change)
4. API response (if backend change)

**No speculation allowed:**
- "Should" → FORBIDDEN (implies untested)
- "Will" → FORBIDDEN (implies future, not verified)
- "Is" → REQUIRED (must have evidence)

**Examples:**

❌ WRONG:
```
Step 3: Edit dashboard.py
Step 4: "Refresh your browser to see the simplified UI"
```
Problem: No evidence UI actually changed

✅ CORRECT:
```
Step 3: Edit dashboard.py
Step 4: Restart streamlit
Step 5: Take screenshot
[Screenshot shows simplified UI]
Step 6: "UI simplified - see screenshot above showing 4 buttons instead of 8"
```

❌ WRONG:
```
"The API should now return correct data"
```
Problem: "should" = untested speculation

✅ CORRECT:
```
$ curl localhost:3000/api/test
Response: {"status": "ok", "data": [...]}
"API returns correct data (verified above)"
```

**Rationale:**
"Should work" is not evidence it works.
User cannot see filesystem changes.
Claims must be verifiable by user.
```

### ENHANCED RULE 31 — Proceed With Obvious Next Steps (v5.4 Update)

**Add to existing Rule 31:**

```markdown
**UPDATED forbidden stops (v5.4):**

❌ After editing code file:
   - MUST restart service
   - MUST verify changes
   - MUST provide evidence
   - FORBIDDEN: Stop after syntax check

❌ After discovering service not running:
   - MUST start service
   - MUST verify it started
   - MUST test functionality
   - FORBIDDEN: Ask "should I start it?"

❌ After making UI changes:
   - MUST restart UI service
   - MUST take screenshot
   - MUST verify changes visible
   - FORBIDDEN: Tell user to "refresh browser" without verification

**New examples:**

✅ CORRECT auto-proceed:
```
User: "Fix the redundant buttons"
LLM:
  Step 1: Edit dashboard.py (remove buttons)
  Step 2: Restart streamlit
  Step 3: Screenshot shows 4 buttons instead of 8
  Step 4: "Fixed - see screenshot"
```

❌ WRONG stop:
```
User: "Fix the redundant buttons"
LLM:
  Step 1: Edit dashboard.py (remove buttons)
  Step 2: Check syntax ✓
  Step 3: "Refresh your browser"
  [User reports no change]
  Step 4: "Oh, streamlit wasn't running"
  Step 5: "Should I start it?" ← VIOLATION
```
```

---

## ENFORCEMENT PATTERN FOR THIS VIOLATION

### Detection Pattern:

```python
def detect_incomplete_ui_change():
    """Detect when UI change claimed without verification"""
    
    patterns = {
        'file_edited': r'(Edit|Modified|Changed).*\.(py|js|jsx|html)',
        'syntax_check': r'(syntax|py_compile|eslint).*OK',
        'refresh_claim': r'(Refresh|Reload).*browser',
        'no_restart': not r'(streamlit run|npm start|restart)',
        'no_screenshot': not r'(screenshot|image|verify)',
    }
    
    if (patterns['file_edited'] and 
        patterns['syntax_check'] and
        patterns['refresh_claim'] and
        patterns['no_restart']):
        
        return "VIOLATION: Rule 40 - UI change without runtime verification"
    
    return None
```

### Auto-Correction:

```python
def correct_incomplete_ui_change(llm_response):
    """Auto-correct to complete workflow"""
    
    # Extract what was edited
    file_edited = extract_filename(llm_response)
    
    # Generate correct workflow
    correction = f"""
    ❌ INCOMPLETE WORKFLOW DETECTED
    
    You edited {file_edited} but didn't verify runtime changes.
    
    COMPLETING WORKFLOW:
    
    Step {n+1}: Restart service
    $ pkill streamlit && streamlit run {file_edited} &
    
    Step {n+2}: Verify service running
    $ ps aux | grep streamlit
    
    Step {n+3}: Take screenshot
    [Screenshot of new UI]
    
    Step {n+4}: Verify changes visible
    OCR shows: [expected changes]
    
    ✅ COMPLETE - Changes verified at runtime
    """
    
    return correction
```

---

## PATTERN RECOGNITION

### This is the FOURTH time this session this pattern occurred:

**Instance 1 (Export integration):**
- Added export code
- Claimed "exports work"
- Didn't test exports
- User found exports broken

**Instance 2 (Schema migration):**
- Ran migration
- Claimed "migration complete"
- Didn't verify in dashboard
- User found legacy schema message

**Instance 3 (Firefox spawn fix):**
- Fixed is_available()
- Claimed "Firefox won't spawn"
- Didn't restart dashboard
- (Actually worked this time by luck)

**Instance 4 (UX redundancy fix):**
- Edited dashboard_v2.py
- Claimed "refresh browser"
- Didn't verify streamlit running
- User found no changes

### Common thread:

1. LLM makes filesystem change ✓
2. LLM checks syntax ✓
3. LLM claims success ✗
4. LLM doesn't verify runtime ✗
5. User sees no change
6. LLM discovers service wasn't running / wrong file / etc.

---

## TESTING THE NEW RULES

### Scenario: User asks to fix UI

**With OLD rules (current behavior):**
```
Step 1: Edit file ✓
Step 2: Check syntax ✓
Step 3: "Refresh browser" ✗
[INCOMPLETE - User sees no change]
```

**With NEW rules (Rule 40, 41, 42):**
```
Step 1: Identify running file (Rule 41)
Step 2: Edit correct file
Step 3: Check syntax
Step 4: Restart service (Rule 40)
Step 5: Take screenshot (Rule 42)
Step 6: Verify changes visible (Rule 40)
Step 7: "Changes verified - see screenshot"
[COMPLETE - User sees changes]
```

**With enforcement system:**
```
[LLM tries to stop after syntax check]
[Enforcement detects Rule 40 violation]
[Auto-generates steps 4-7]
[Completes workflow automatically]
```

---

## RECOMMENDED RULE UPDATES

### Update Rules File to Version 5.4:

**Add:**
- Rule 40: Runtime Verification After Code Changes (🔴 HARD STOP)
- Rule 41: Multi-File Disambiguation (🟠 CRITICAL)
- Rule 42: No Success Claims Without Evidence (🔴 HARD STOP)

**Enhance:**
- Rule 31: Add forbidden stops after code edits
- Rule 37: Add examples of partial compliance

**Cross-reference:**
- Rule 40 reinforces Rule 9 (end-to-end workflow)
- Rule 40 reinforces Rule 22 (complete workflow testing)
- Rule 42 reinforces Rule 2 (evidence-before-assertion)

---

## IMMEDIATE ACTIONS NEEDED

### For Current Situation:

Augment Code should have done (per Rules 31, 40):
```
Step 1: Identify which dashboard file is running
$ ps aux | grep streamlit
[No streamlit process found]

Step 2: Start the edited file
$ streamlit run dashboard_v2.py --server.port 8501 &

Step 3: Wait for startup
$ sleep 5

Step 4: Verify it's running
$ ps aux | grep streamlit
$ curl http://localhost:8501

Step 5: Take screenshot
[Screenshot showing simplified UI]

Step 6: Compare to user's original screenshot
Before: 8 buttons (redundant)
After: 4 buttons (streamlined)

Step 7: "UI simplified - see screenshot comparison"
```

**NOT:** "Waiting for user input" ← Rule 31 violation

---

## SUMMARY

### Rules Violated:
- Rule 2: Evidence-Before-Assertion
- Rule 7: Observation Layer Integrity
- Rule 9: End-to-End Workflow Proof
- Rule 22: Complete Workflow Testing
- Rule 31: Auto-proceed with obvious steps
- Rule 37: No Partial Compliance

### New Rules Needed:
- Rule 40: Runtime Verification (prevents filesystem ≠ runtime confusion)
- Rule 41: Multi-File Disambiguation (prevents wrong file edits)
- Rule 42: No Speculation (prevents "should work" claims)

### Enforcement Pattern:
- Detect: Syntax check + no restart + "refresh browser"
- Correct: Auto-generate restart + screenshot + verification

### Bottom Line:

**The pattern:** Make change → Check syntax → Claim success → Stop  
**The problem:** Runtime not verified, user sees nothing  
**The fix:** Rules 40, 41, 42 enforce complete workflow  

This is the FOURTH occurrence of this exact pattern. Rules update is critical to prevent recurrence.
