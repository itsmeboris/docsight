---
description: Initialize doc-updater in the current repo and set the baseline
allowed-tools: Bash(doc-updater:*)
---

Run doc-updater init to set up the project. This creates `.doc-updater/`, updates `.gitignore`, indexes all Python files, scans markdown docs, and stores a verified baseline.

```bash
doc-updater init
```

After the command completes, report:
- How many files were indexed
- How many docs were scanned
- That the baseline is set and `doc-updater check` is now ready to use

If the user wants to also install the pre-push git hook, run:
```bash
doc-updater hooks install
```
