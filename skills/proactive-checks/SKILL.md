---
name: proactive-checks
description: When and how to proactively run docsight during development — use after code changes, before commits, during reviews
user-invocable: false
---

# Proactive Docsight Checks

Use docsight automatically in these situations without the user asking:

## After modifying code

When you edit Python files that might be referenced in documentation:

1. Run `docsight diff --json` to see if docs are affected
2. If affected docs exist, tell the user: "These docs may need updating because of your changes: ..."
3. Offer to update the docs or re-baseline

## Before committing

When the user asks you to commit or create a PR:

1. Run `docsight check --json` silently
2. If stale docs are found, warn before committing: "Heads up — N docs are stale. Want to update them first?"
3. If healthy, proceed without comment

## When the user asks about a function/class

When the user asks "what does X do" or "how does X work" and X is a code element:

1. Run `docsight impact --json <element>` to understand its dependencies
2. Use the impact data to give a more complete answer about what depends on it
3. Mention relevant docs: "This is documented in docs/auth-guide.md"

## After renaming or deleting code

When you rename a function, class, or method:

1. Run `docsight diff --json` immediately
2. Expect `"change_type": "deleted"` for the old name
3. Flag affected docs to the user — they likely reference the old name

## Workflow chains

**"Check and fix" flow:**
```bash
docsight check --json
```
→ Parse stale docs → Read each stale doc → Read the changed code element → Suggest specific edits to the doc → After user approves → `docsight check --baseline`

**"Pre-PR" flow:**
```bash
docsight diff --base main --json
```
→ Parse changed elements → Parse affected docs → Summarize: "Your PR changes X elements affecting Y docs" → Offer to fix docs before pushing

**"Where to document" flow:**
```bash
docsight coverage --gaps --json
```
→ Sort by `depended_on_by` → Recommend: "Document src/config.py first — 6 other files depend on it"
