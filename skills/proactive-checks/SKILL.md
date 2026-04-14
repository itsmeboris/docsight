---
name: proactive-checks
description: When and how to proactively run docsight during development — provides semantic analysis, not just data dumps
user-invocable: false
---

# Proactive Docsight Checks

Use docsight as a data layer, then provide semantic analysis on top.

## Core principle

Docsight gives you structured data (which elements changed, which docs reference
them, dependency graph). Your job is to READ the actual files and EXPLAIN what
the data means. Never dump JSON or element IDs at the user.

## After modifying code

When you edit Python files:

1. Run `docsight diff --json` silently
2. If docs are affected, READ the affected doc and the changed code
3. Explain: "The auth guide shows the old function signature at line 23 — here's what it should say now"
4. Offer to fix

## Before committing

When the user asks to commit or create a PR:

1. Run `docsight check --json` silently
2. If stale, read the stale doc and changed code
3. Warn with specifics: "The cache guide's usage example on line 8 uses the old API — want me to update it before committing?"

## After renaming or deleting code

1. Run `docsight diff --json`
2. For `"change_type": "deleted"` — read each affected doc
3. Flag: "You renamed `authenticate()` to `login()` but the auth guide still references it in 3 places. Want me to update them?"

## When asked about documentation quality

1. Use `/docsight:audit` — it reads all docs and code to build a semantic map
2. Don't just report coverage percentages. Explain what's covered, what's missing, and what matters.

## What NOT to do

- Never dump raw JSON output to the user
- Never list element IDs without explaining what they mean
- Never say "55 files are undocumented" — say "the queue pipeline has no docs and it connects your two main systems"
- Never report confidence scores — translate them to "definitely stale" or "might need a look"
