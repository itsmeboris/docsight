---
description: Semantic audit — what do your docs cover, what's missing, what matters
argument-hint: '[path/to/specific/doc.md]'
allowed-tools: Bash(docsight:*), Read, Grep, Glob
---

Analyze documentation quality semantically. This is NOT a line count — it reads
your docs and code to understand what's covered and what's missing.

Raw arguments: `$ARGUMENTS`

## If a specific doc is given

1. Read the doc file
2. Run `docsight check --json` to get staleness data for it
3. Run `docsight impact --json` on the key elements it references
4. Analyze:
   - **What this doc covers** — summarize its topics in 2-3 bullets
   - **Is it accurate?** — check if referenced code matches what the doc says
   - **Is it complete?** — does it cover the important parts of the module/feature it describes, or does it skip critical details?
   - **What's missing?** — based on the dependency graph, are there related modules the doc should mention but doesn't?

## If no specific doc is given — full repo audit

1. Find all docs:
   ```bash
   docsight coverage --json
   docsight coverage --gaps --json
   ```

2. Read the main docs (README, ARCHITECTURE, guides) using the Read tool

3. Get the code structure:
   ```bash
   docsight impact --json <each major module>
   ```

4. Build a **documentation map**:

   For each major doc, summarize:
   - What it covers (topics, modules, features)
   - Is it current? (staleness status)
   - What's its scope? (overview vs deep-dive vs tutorial)

5. Identify **semantic gaps**:
   - "ARCHITECTURE.md explains the trigger and worker systems but doesn't mention the queue pipeline, which connects them"
   - "There's no guide for the Gerrit flow, which is one of the three main flows"
   - "The setup guide references config.yaml but doesn't explain the Teams webhook configuration, which is required for the Teams flow"

6. Prioritize by importance:
   - Critical: gaps in core systems that many things depend on
   - Important: undocumented flows or features users interact with
   - Nice to have: internal utilities, test helpers

7. Present as a structured report:
   ```
   Documentation Health Report
   
   ✓ Well covered: auth system, trigger polling, deployment
   ✗ Gaps: queue pipeline, Gerrit flow prompts, error handling
   ⚠ Stale: auth-guide.md (signature change in validate_token)
   
   Recommended actions (by priority):
   1. Add queue pipeline section to ARCHITECTURE.md — connects triggers to workers
   2. Create docs/gerrit-flow.md — one of three main flows, undocumented
   3. Update auth-guide.md line 42 — parameter renamed
   ```

## Rules
- Read actual files. Never just report numbers.
- Explain gaps in terms of features and systems, not function names.
- Prioritize by what matters to someone trying to understand or use the project.
- If a module has 50 functions but only 3 are entry points, focus on the 3.
