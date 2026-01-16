# Bug Report: launch-process and read-terminal Output Capture Failure

**Date:** 2025-01-15
**Severity:** High (causes widespread incorrect behavior)
**Component:** launch-process tool, read-terminal tool

## Summary

The `launch-process` and `read-terminal` tools fail to capture terminal output that is visible to the user in the same terminal session. Commands execute successfully but the assistant receives empty or truncated output.

## Environment

- Workspace: `/home/owner/Documents/69612439-14cc-8326-ae46-455c0df3b9be/claude`
- OS: Linux (Fedora-based)
- Shell: bash

## Reproduction Steps

1. Assistant runs via launch-process:
   ```bash
   $ ls .augment/rules/*.md
   ```

2. launch-process returns empty output to assistant

3. read-terminal also returns empty output

4. User inspects same terminal and sees full output:
   ```
   .augment/rules/mandatory-rules_5_3.md  .augment/rules/mandatory-rules-v5.4.md
   .augment/rules/mandatory-rules_5_5.md  .augment/rules/mandatory-rules-v5.7.md
   .augment/rules/mandatory-rules.md
   ```

## Evidence from Session

### Assistant's view (launch-process output):
```
Terminal ID 6
<output>
</output>
```

### Assistant's view (read-terminal):
```
[owner@192.168.1.135-20260115-084255 claude]$ ls .augment/rules/*.md
[owner@192.168.1.135-20260115-084256 claude]$ 
```

### User's actual terminal (same session):
```
[owner@192.168.1.135-20260115-084255 claude]$ ls .augment/rules/*.md
.augment/rules/mandatory-rules_5_3.md  .augment/rules/mandatory-rules-v5.4.md
.augment/rules/mandatory-rules_5_5.md  .augment/rules/mandatory-rules-v5.7.md
.augment/rules/mandatory-rules.md
```

## Additional Observations

1. `find` command also affected - returns partial or no results
2. "Cancelled by user" errors occur that are NOT user-initiated
3. `wc -l` command shows empty output when user sees full output
4. `view` tool works correctly for same file/directory operations

## Impact

This bug causes the assistant to:
- Make false claims about missing files
- Assume commands failed when they succeeded
- Launch redundant commands
- Provide incorrect information to users
- Waste significant user time debugging "problems" that don't exist

## Suggested Investigation Areas

1. Output buffering between terminal and tool capture
2. Race condition between command completion and output read
3. stdout vs tty capture differences
4. Terminal session state management

## Workaround

Use `view` tool instead of `launch-process` for file/directory operations.

## Related

This may explain many reported issues where the assistant incorrectly claims files don't exist or commands failed.

