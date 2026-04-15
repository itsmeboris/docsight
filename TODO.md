# docsight Roadmap

## Phase 1 — Ship it (make it installable)

- [ ] **Publish to PyPI** — `pip install docsight`, setup classifiers, license, long_description from README
- [ ] **Claude Code marketplace** — publish plugin so anyone can `/plugin install docsight`

## Phase 2 — Make it smarter

- [ ] **LLM-assisted doc scanning** — detect prose mentions ("the polling system handles...") not just backtick references. Optional pass that uses the configured AI provider to find semantic code references in docs
- [ ] **Auto-fix CLI command** — `docsight fix` that patches simple staleness: updated signatures in code examples, renamed references. Confirm before applying. Handles the common cases so you don't need to manually edit
- [ ] **Doc generation from gap analysis** — `docsight generate <file>` reads the code, understands dependencies via the graph, and drafts a doc. Uses the gap analysis to know what's important. The `/docsight:audit` command can trigger this for top-priority gaps

## Phase 3 — Expand reach

- [ ] **Multi-language support** — tree-sitter analyzers for TypeScript, Go, Rust. The abstract `CodeAnalyzer` interface is ready. Start with TypeScript (most common alongside Python in docs-heavy projects)
- [ ] **Watch mode** — `docsight watch` monitors file changes and alerts when docs become stale in real-time. Useful for long coding sessions. Could integrate with editor LSP for inline warnings
