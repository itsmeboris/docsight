---
description: Understand what your docs cover and where the real gaps are
argument-hint: '[--gaps] [--all-elements] [--include-private] [--json]'
allowed-tools: Bash(docsight:*), Read, Grep, Glob
---

Analyze documentation coverage semantically — not just function counts.

Raw arguments: `$ARGUMENTS`

## Step 1: Get the data

```bash
docsight coverage --gaps --json
```

## Step 2: Semantic gap analysis

DO NOT just list undocumented files. Instead:

1. **Read the main docs** (README, ARCHITECTURE, guides) to understand what's covered
2. **Read the top gap files** (highest dependency weight) to understand what they do
3. **Identify meaningful gaps:**
   - "Your architecture doc covers the trigger and worker systems but doesn't explain how the queue connects them — `core/queue/` is the pipeline between them and has no documentation"
   - "All three flow handlers (Jenkins, Gerrit, Teams) follow the same pattern but only the Jenkins flow has a guide"
   - "The config system is well-documented but the credential/secret management isn't mentioned anywhere"

4. **Ignore noise:**
   - Test files don't need docs
   - Internal utilities with 0 dependents are low priority
   - Files already covered by a file-path reference in an architecture doc

## Step 3: Prioritized recommendations

Present 3-5 actionable recommendations:
1. Most critical gap (highest impact on understanding)
2. Easiest win (small doc addition that covers a lot)
3. User-facing gap (something an end user would need)

For each, explain WHAT to write and WHERE to put it.

## Rules
- Frame gaps in terms of features and systems, not function names
- Only flag gaps that matter to someone reading the docs
- Read the code before claiming something is undocumented — it might be covered inline
