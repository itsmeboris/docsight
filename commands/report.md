---
description: Generate the HTML report with file-level drill-down
allowed-tools: Bash(doc-updater:*), Bash(open:*), Bash(xdg-open:*)
---

Generate the interactive HTML report.

```bash
doc-updater report
```

After generation, tell the user the output path (`.doc-updater/report.html`) and offer to open it:
```bash
open .doc-updater/report.html 2>/dev/null || xdg-open .doc-updater/report.html 2>/dev/null || true
```

The report shows:
- Documentation staleness status per doc file
- Code elements grouped by file, with collapsible sections
- Stale elements highlighted in red, undocumented in yellow
- Coverage statistics (public API only)
