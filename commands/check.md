---
description: Check if documentation is stale and suggest fixes
allowed-tools: Bash(docsight:*), Read, Grep, Glob
---

Run docsight check and help the user fix any stale docs.

## Step 1: Run the check

```bash
docsight check --json
```

Parse using the `output-schemas` skill.

## Step 2: Present findings

- If all healthy: "All N docs are up to date." Stop here.
- If stale/possibly_stale: summarize by severity, then detail each.

For each stale doc, explain:
- **What changed**: element name, change type (signature/body/transitive/deleted)
- **Confidence**: high (>= 0.70) or medium (< 0.70)
- **Impact**: direct (hops=0) or transitive (hops > 0, name the chain)

## Step 3: Offer to fix (only if stale found)

For each stale doc:
1. Read the doc file
2. Read the changed source code element
3. Show the user the specific section that needs updating and the current code
4. Suggest a concrete edit

Ask: "Want me to apply these fixes?" — do NOT auto-edit without confirmation.

## Step 4: After fixes

If the user approved fixes:
```bash
docsight check --baseline
```
Confirm: "Baseline updated. Docs are now verified against current code."
