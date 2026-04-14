---
description: Show documentation coverage and find gaps
argument-hint: '[--gaps] [--all-elements]'
allowed-tools: Bash(docsight:*)
---

Run docsight coverage to analyze documentation coverage.

Raw arguments: `$ARGUMENTS`

If the user asks about gaps or "where should I write docs next", add `--gaps`:
```bash
docsight coverage --gaps --json
```

Otherwise run standard coverage:
```bash
docsight coverage --json $ARGUMENTS
```

For standard coverage, report:
- Coverage percentage and element counts
- List of undocumented public API elements

For gaps mode, report:
- Files with zero documented public API, sorted by importance (most depended-on first)
- Recommend which files to document first based on dependency weight
- "Documenting X would cover the most critical gap — Y other files depend on it"
