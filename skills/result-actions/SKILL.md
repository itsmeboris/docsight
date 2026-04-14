---
name: result-actions
description: How to interpret docsight results and take action — fix stale docs, suggest updates, prioritize gaps
user-invocable: false
---

# Acting on Docsight Results

## Interpreting staleness

**change_type = "signature"** (high confidence)
The function/class API changed — parameters added/removed/renamed, return type changed.
→ The doc almost certainly needs updating. Read the element's current signature and update the doc to match.

**change_type = "body"** (medium confidence)
The function behavior changed but the API is the same.
→ Check if the doc describes behavior details. If it only shows usage examples, it may still be correct.

**change_type = "transitive"** (lower confidence, hops > 0)
A dependency of the documented element changed.
→ Only flag if the doc mentions the dependency's behavior. Many transitive changes don't affect the doc.

**change_type = "reference_lost" or "deleted"**
The documented element was renamed or removed.
→ This always needs a doc update. Find what replaced it and update the reference.

## Fixing a stale doc

When you need to update a doc for a stale element:

1. Read the current doc file
2. Read the changed code element: `docsight show <doc>` or read the source file directly
3. Find the specific section in the doc that references the changed element
4. Update that section to match the current code
5. Do NOT rewrite unrelated sections
6. After fixing, offer to re-baseline: `docsight check --baseline`

## Prioritizing coverage gaps

When `coverage --gaps` returns multiple files:

1. Files with highest `depended_on_by` are most critical — they're used by many other files
2. Files with high `public_api` count have more surface area to document
3. Recommend documenting the highest-impact file first
4. Suggest creating a new doc file in `docs/` with the file's public API documented

## Confidence thresholds

- >= 0.70: STALE — doc definitely needs review
- 0.40–0.69: POSSIBLY_STALE — doc might need review, mention it but don't alarm
- < 0.40: Low confidence — don't mention unless the user asks for details

## Exit codes

- `docsight check` exits 0 = all healthy, exits 1 = stale docs found
- Use exit code for CI gating, not for conversational output
