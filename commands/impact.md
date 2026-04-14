---
description: Understand the blast radius before changing code
argument-hint: '<element-or-file>'
allowed-tools: Bash(docsight:*), Read, Grep
---

Show what would break if you change a code element or file. Explains
the impact semantically, not just as a list of IDs.

The user's target: `$ARGUMENTS`

## Step 1: Get the data

```bash
docsight impact --json $ARGUMENTS
```

## Step 2: Explain the blast radius

1. **Read the target code** to understand what it does
2. **Group affected elements by relationship:**
   - Direct callers: "These functions call yours directly — their behavior depends on your API"
   - Transitive: "These are further up the call chain — likely unaffected unless you change return types or semantics"
3. **For each affected doc**, read it and identify which section discusses the affected element. Quote the relevant passage.
4. **Assess the risk level:**
   - High: changing the API signature → docs definitely break
   - Medium: changing behavior → docs might break depending on what they describe
   - Low: internal refactor → docs probably fine

## Step 3: Give actionable advice

- "Safe to change — only 1 test depends on it, no docs reference it"
- "Medium risk — 3 files depend on it and the auth guide shows usage examples that would break"
- "High risk — this is referenced in ARCHITECTURE.md and 2 user-facing guides. Update docs first."

## Rules
- Read the actual code and docs, don't just list IDs
- Assess whether transitive impacts actually matter
- Frame it as risk assessment, not a dump of graph data
