---
description: Check if documentation is stale and explain what drifted
argument-hint: '[--baseline] [--json] [--direct-only] [--max-hops N]'
allowed-tools: Bash(docsight:*), Read, Grep, Glob, Edit
---

Detect stale documentation, explain what drifted, and offer to fix it.

## Step 1: Get the data

```bash
docsight check --json
```

If all healthy, say so briefly and stop.

## Step 2: For each stale doc — do semantic analysis

For each stale doc, DO NOT just list element IDs. Instead:

1. **Read the stale doc** using the Read tool
2. **Read the changed source code** — the element that triggered staleness
3. **Explain the drift in plain language:**
   - "The authentication guide shows `validate_token(token, strict=True)` but the `strict` parameter was renamed to `mode` and now accepts a string"
   - "The cache guide describes `cache_lookup(key)` but the function now takes an optional `ttl` parameter"
4. **Quote the specific lines** in the doc that are wrong
5. **Show what the code looks like now**

## Step 3: Offer to fix

For each stale section, draft the corrected text and ask:
"Want me to update this section?"

Do NOT auto-edit. Wait for confirmation.

## Step 4: After fixes

```bash
docsight check --baseline
```

## Rules
- Never just dump JSON or element IDs at the user
- Always read the actual files and explain semantically
- Focus on WHAT changed and WHY the doc is wrong, not on confidence scores
