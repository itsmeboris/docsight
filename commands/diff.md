---
description: Show which docs need updating based on code changes (vs baseline or git ref)
argument-hint: '[--base REF]'
allowed-tools: Bash(doc-updater:*)
---

Run doc-updater diff to see what docs need updating based on code changes.

Raw arguments: `$ARGUMENTS`

```bash
doc-updater diff --json $ARGUMENTS
```

Parse the JSON output and present:
- Changed elements: what changed (signature, body, deleted) and in which files
- Affected docs: which docs need updating, whether the impact is direct or transitive
- For each affected doc, suggest what the user should review or update

If no changes detected, confirm the codebase matches the baseline.

This is the go-to command for PR review: "before I push, what docs need updating?"
