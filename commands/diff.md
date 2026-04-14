---
description: Show which docs need updating for your code changes and suggest fixes
argument-hint: '[--base REF]'
allowed-tools: Bash(docsight:*), Bash(git:*), Read, Grep, Glob
---

Analyze code changes and show which docs need updating.

Raw arguments: `$ARGUMENTS`

## Step 1: Run the diff

```bash
docsight diff --json $ARGUMENTS
```

Parse using the `output-schemas` skill.

## Step 2: Present the change summary

Group by change type:
- **Signature changes**: API contract broke — list elements with old → new signatures
- **Body changes**: behavior shifted — list elements
- **Deleted elements**: renamed or removed — list elements

Then show affected docs:
- **Direct**: doc references a changed element
- **Transitive**: doc references something that depends on a changed element (show the chain)

## Step 3: For each affected doc

1. Read the doc file
2. Read the changed code
3. Identify the specific section that needs updating
4. Suggest a concrete fix: "Line 42 says `validate_token(token, strict=True)` but the parameter is now `mode: str`"

## Step 4: Offer next steps

- "Want me to fix these docs?"
- If no changes detected: "Your code changes don't affect any documented elements."
- After fixes: offer to re-baseline with `docsight check --baseline`
