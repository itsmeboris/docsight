---
description: Check if documentation is stale and show what needs updating
allowed-tools: Bash(doc-updater:*)
---

Run doc-updater check to detect stale documentation.

```bash
doc-updater check --json
```

Parse the JSON output and present findings to the user:
- Summary: X healthy, Y stale, Z possibly stale, W unverified
- For each stale doc: which elements changed (signature vs body vs transitive), confidence score
- Suggest specific updates the user should make to each stale doc
- If everything is healthy, confirm docs are up to date

If the user wants to accept current state as verified, offer to re-baseline:
```bash
doc-updater check --baseline
```
