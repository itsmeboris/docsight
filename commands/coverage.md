---
description: Show documentation coverage and find where to write docs next
argument-hint: '[--gaps] [--all-elements]'
allowed-tools: Bash(docsight:*), Read, Glob
---

Analyze documentation coverage.

Raw arguments: `$ARGUMENTS`

## If the user asks about gaps or "where should I write docs":

```bash
docsight coverage --gaps --json
```

Present gap files sorted by impact:
- "**src/config.py** (3 public elements, depended on by 6 files) — highest priority"
- For the top gap file, read its source and offer to draft a doc for it

## Otherwise, run standard coverage:

```bash
docsight coverage --json $ARGUMENTS
```

Present:
- Coverage percentage and counts
- Top undocumented elements grouped by file
- If coverage is low, suggest: "Run `/docsight:coverage --gaps` to see where to start"
