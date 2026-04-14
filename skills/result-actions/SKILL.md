---
name: result-actions
description: How to interpret docsight data and translate it into semantic, actionable insight
user-invocable: false
---

# Translating Docsight Data to Semantic Insight

Docsight is a data layer. You are the intelligence layer. Always read
the actual files before presenting results.

## Translating change types

**signature changed** → Read the old doc and new code. Show: "The doc says X but the code now does Y."

**body changed** → Read the doc. Does it describe behavior details? If it only shows a usage example, the example might still work. Only flag if the doc describes the behavior that changed.

**transitive** → This is the trickiest. Read the doc section about the affected element. Ask: "Does this doc describe HOW the element works internally (in which case a dependency change matters) or just HOW TO USE it (in which case it probably doesn't)?"

**deleted/reference_lost** → Always flag. The doc references something that doesn't exist. Read the doc and identify every mention.

## Assessing whether a gap matters

Not all undocumented code needs docs. Ask:

1. **Is it user-facing?** Entry points, CLI commands, API endpoints → needs docs
2. **Is it a system boundary?** Connects major components → architecture doc should mention it
3. **Do other devs need to understand it?** Complex logic, non-obvious design → needs explanation
4. **Is it a simple utility?** Single-purpose, well-named → code is the doc

## Presenting findings

Bad: "src/docsight/cli.py::check has change_type=signature, confidence=0.90, hops=0"

Good: "The auth guide shows `validate_token(token, strict=True)` but the `strict` parameter was renamed to `mode` and now takes a string instead of a boolean. Line 42 of the guide needs updating."

## After fixes

Always offer to re-baseline: `docsight check --baseline`
Explain: "This marks all current docs as verified against the code."
