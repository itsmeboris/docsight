---
description: Show blast radius of changing a code element or file
argument-hint: '<element-or-file> [--max-hops N]'
allowed-tools: Bash(docsight:*), Read, Grep
---

Show what would be affected by changing a code element or file.

The user's argument is the target: `$ARGUMENTS`

## Step 1: Run impact analysis

```bash
docsight impact --json $ARGUMENTS
```

Parse using the `output-schemas` skill.

## Step 2: Present the blast radius

Summarize: "Changing X affects Y elements across Z files, and W docs would need updating."

Group affected elements by hop distance:
- **Direct dependents** (1 hop): these call/inherit the target
- **Transitive** (2+ hops): indirectly affected through the chain

## Step 3: Show affected docs

For each affected doc, explain which elements in that doc are affected and why.

If no dependents found: "This change is isolated — no other code depends on it and no docs reference it."

## Step 4: Offer guidance

- If many docs affected: "Consider updating docs before making this change"
- If few/no docs affected: "Safe to change — minimal documentation impact"
- Offer to read the source element: "Want me to show the current code?"
