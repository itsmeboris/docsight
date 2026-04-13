---
name: doc-check
description: Check if documentation is stale due to code changes and suggest updates
---

# Doc Staleness Check

## When to Use
- User asks "are my docs up to date?"
- User modifies code and wants to know which docs need updating
- During PR review to check doc impact
- User says "check docs", "stale docs", "doc health"

## Workflow

1. Ensure initialized and run check:
   ```bash
   doc-updater init 2>/dev/null || true
   doc-updater check --json
   ```

2. Parse JSON output and present findings:
   - Summary: X healthy, Y stale, Z need review
   - For each stale doc: what changed, suggested fix
   - Offer to update docs or set new baseline

3. For visual overview:
   ```bash
   doc-updater graph
   ```
