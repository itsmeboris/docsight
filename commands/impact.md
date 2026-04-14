---
description: Show blast radius of changing a code element or file
argument-hint: '<element-or-file> [--max-hops N]'
allowed-tools: Bash(doc-updater:*)
---

Run doc-updater impact to show what would be affected by a change.

The user's argument is the target: `$ARGUMENTS`

```bash
doc-updater impact --json $ARGUMENTS
```

Parse the JSON output and present:
- The seed element(s) that were targeted
- Affected elements grouped by hop distance (direct dependents vs transitive)
- Which docs reference any affected element and would need updating
- If no dependents found, confirm the change is isolated

Help the user understand the risk: "Changing X affects Y elements across Z files, and W docs would need updating."
