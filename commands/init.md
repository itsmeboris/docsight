---
description: Initialize docsight in the current repo and set the baseline
argument-hint: '[--no-baseline]'
allowed-tools: Bash(docsight:*)
---

Run docsight init to set up the project. This creates `.docsight/`, updates `.gitignore`, indexes all Python files, scans markdown docs, and stores a verified baseline.

```bash
docsight init
```

After the command completes, report:
- How many files were indexed
- How many docs were scanned
- That the baseline is set and `docsight check` is now ready to use

If the user wants to also install the pre-push git hook, run:
```bash
docsight hooks install
```
