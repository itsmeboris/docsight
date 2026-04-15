---
description: Explain what docs need updating for your code changes
argument-hint: '[--base REF] [--json] [--max-hops N]'
allowed-tools: Bash(docsight:*), Bash(git:*), Read, Grep, Glob, Edit
---

Analyze code changes and explain which docs need updating and why.

Raw arguments: `$ARGUMENTS`

## Step 1: Get the data

```bash
docsight diff --json $ARGUMENTS
```

If no changes detected, say so and stop.

## Step 2: Semantic analysis of each affected doc

For each affected doc, DO NOT just list element names. Instead:

1. **Read the affected doc**
2. **Read the changed code** (both old intent and new state)
3. **Explain the impact in plain language:**
   - "You renamed `authenticate()` to `login()` — the auth guide at line 23 still says 'call `authenticate()` directly' which will confuse readers"
   - "You added a `ttl` parameter to `cache_lookup()` — the cache guide's example at line 8 should show this parameter since it changes the caching behavior"
4. **For transitive changes**, explain the chain:
   - "You changed `cache_lookup` → `validate_token` calls it → the auth guide documents `validate_token` — check if the caching behavior description is still accurate"
5. **For deleted elements**, flag clearly:
   - "The function `authenticate()` no longer exists. The auth guide references it in 3 places."

## Step 3: Offer to fix

For each issue, draft the corrected doc text. Ask before applying.

## Rules
- Read the actual files. Quote specific lines.
- Explain WHY the doc is affected, not just THAT it is.
- For transitive impacts, assess whether the doc actually needs updating (not all transitive changes matter).
