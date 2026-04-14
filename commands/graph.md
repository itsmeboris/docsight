---
description: Generate the interactive dependency graph and open it
argument-hint: '[--flat] [--export json]'
allowed-tools: Bash(docsight:*), Bash(open:*), Bash(xdg-open:*)
---

Generate the semantic-zoom dependency graph.

```bash
docsight graph
```

After generation, tell the user the output path (`.docsight/graph.html`) and offer to open it:
```bash
open .docsight/graph.html 2>/dev/null || xdg-open .docsight/graph.html 2>/dev/null || true
```

Explain the graph interaction:
- **Double-click** a file node to expand it into classes and functions
- **Double-click** a class to show its methods
- **Double-click** the folder header to collapse back
- **Red** nodes are stale, **amber** are possibly stale
- **Search** box filters nodes by name
