# docsight

Detect stale documentation by analyzing code-to-doc relationships.

**docsight** builds a graph of your Python codebase, scans your markdown docs for references to code elements, and tells you exactly which docs are stale when code changes — including transitive dependencies.

---

## Table of Contents

- [Why](#why)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Commands](#commands)
- [Workflow](#workflow)
- [Configuration](#configuration)
- [Interactive Graph](#interactive-graph)
- [Claude Code Integration](#claude-code-integration)
- [Development](#development)
- [Built With](#built-with)

---

## Why

Code changes. Docs don't update themselves. You end up with:
- API docs describing parameters that no longer exist
- Guides referencing functions that were renamed
- Tutorials using patterns that changed three PRs ago

**docsight** catches this automatically. After a code change, one command tells you which docs need attention and why.

---

## Quick Start

### Prerequisites

- Python >= 3.12

### Install

```bash
pip install -e .
```

### First Run

```bash
cd your-python-project

# One command: creates .docsight/, indexes code, sets baseline, installs pre-push hook
docsight init

# ... make code changes ...

# Check which docs are now stale
docsight check

# See what changed and which docs need updating
docsight diff

# See blast radius before changing something
docsight impact src/auth.py
```

Example output:

```
╭─────────────────────────────╮
│     Staleness Summary       │
│                             │
│ Total docs:      4          │
│ Healthy:         2          │
│ Stale:           1          │
│ Possibly stale:  1          │
│ Unverified:      0          │
╰─────────────────────────────╯

docs/auth-guide.md — stale
  • [signature] src/auth.py::AuthManager.validate_token (confidence=0.90, hops=0)
    Signature of 'src/auth.py::AuthManager.validate_token' has changed

docs/cache-guide.md — possibly_stale
  • [transitive] src/cache.py::cache_lookup (confidence=0.54, hops=1)
    Dependency 'src/cache.py::cache_lookup' has changed (1 hop(s) away)
```

---

## How It Works

```mermaid
flowchart LR
    subgraph Analyze
        PY["Python files"] --> AST["AST Analyzer"]
        AST --> IDX["Code Index"]
        AST --> GRAPH["Dependency Graph"]
    end

    subgraph Scan
        MD["Markdown docs"] --> SCAN["Doc Scanner"]
        SCAN --> MAP["Mapper"]
        MAP --> MAPPINGS["Code-to-Doc Mappings"]
    end

    subgraph Detect
        IDX --> DET["Staleness Detector"]
        GRAPH --> DET
        MAPPINGS --> DET
        STATE["Verified Baseline"] --> DET
        DET --> REPORT["Staleness Report"]
    end
```

### Three-tier hashing

Each code element (function, class, method) gets three hashes:

| Hash | What it captures | Staleness signal |
|------|-----------------|------------------|
| `signature_hash` | Name, parameters (including defaults and kinds), return type | **High** — the API contract changed |
| `body_hash` | `ast.dump()` of body statements only | **Medium** — behavior changed |
| `source_hash` | Raw source text | Not used for staleness (comments/formatting aren't staleness) |

### Transitive detection

If your doc references `validate_token()` and `validate_token` calls `cache_lookup()`, a change to `cache_lookup` is flagged as **transitive staleness** with confidence that decays per hop (default: 0.6x per hop, max 3 hops).

### Reference-lost detection

If a documented function is renamed or deleted, it's flagged as `reference_lost` — the doc references something that no longer exists.

---

## Commands

| Command | Description |
|---------|-------------|
| `docsight init` | Initialize, index, scan, and baseline (one command to start) |
| `docsight hooks install` | Install pre-push git hook that runs `check` |
| `docsight hooks uninstall` | Remove the pre-push hook |
| `docsight index` | Parse Python files, build code index + dependency graph |
| `docsight scan` | Scan markdown docs, auto-detect code references |
| `docsight check --baseline` | Set current state as verified baseline |
| `docsight check` | Detect stale docs (exit code 1 if any stale) |
| `docsight check --json` | Machine-readable JSON output (for CI) |
| `docsight status` | Show last check summary |
| `docsight show <doc>` | Detailed tree view for one doc |
| `docsight impact <target>` | Show blast radius of changing an element or file |
| `docsight diff` | Show which docs need updating based on code changes |
| `docsight graph` | Export semantic-zoom dependency graph (file → class → method) |
| `docsight coverage` | Show doc coverage (public API only by default) |
| `docsight report` | Generate interactive HTML report |
| `docsight clean` | Remove all docsight data from the repo |

### Key flags

```bash
docsight check --json              # JSON output for CI
docsight check --direct-only       # Skip transitive checks
docsight check --max-hops 5        # Increase transitive depth (default: 3)
docsight impact src/auth.py        # Blast radius for all elements in a file
docsight impact cache_lookup --json # Impact analysis as JSON
docsight diff                      # Changes vs stored baseline
docsight diff --base main          # Changes vs a git ref
docsight coverage --gaps           # Files with zero documented public API
docsight coverage --all-elements   # Count every element (not just public API)
docsight graph --flat              # Old flat vis.js layout
docsight graph --export json       # Export graph as JSON
docsight clean --keep-gitignore    # Remove data but keep .gitignore entry
```

---

## Workflow

### Day-to-day use

```bash
# After code changes, check docs
docsight check

# See details for a specific doc
docsight show docs/auth-guide.md

# After updating the docs, re-baseline
docsight check --baseline
```

### CI integration

The baseline must be created **locally** and committed — CI only checks against it.

`init` adds `.docsight/` to `.gitignore` by default, so you need to
force-add `state.json` (the only file CI needs):

```bash
# One-time setup (run locally)
docsight init
git add .gitignore
git add -f .docsight/state.json
git commit -m "chore: add docsight baseline"
```

Then in CI, just check:

```yaml
# GitHub Actions example
- name: Check doc staleness
  run: |
    pip install docsight
    docsight check  # exits 1 if docs are stale vs. committed baseline
```

`check` auto-regenerates `index.json` and `mappings.json` — only `state.json`
needs to be in the repo. After updating stale docs, re-baseline and commit:

```bash
docsight check --baseline
git add -f .docsight/state.json
git commit -m "chore: update docsight baseline"
```

The `--json` flag produces machine-readable output:

```json
{
  "summary": {
    "total": 4,
    "healthy": 3,
    "stale": 1,
    "possibly_stale": 0,
    "unverified": 0
  },
  "stale_docs": [
    {
      "doc": "docs/auth-guide.md",
      "status": "stale",
      "issues": [
        {
          "element_id": "src/auth.py::AuthManager.validate_token",
          "change_type": "signature",
          "confidence": 0.90,
          "hops": 0,
          "detail": "Signature of 'src/auth.py::AuthManager.validate_token' has changed"
        }
      ]
    }
  ]
}
```

---

## Configuration

### Exclude patterns

Add a `[tool.docsight]` section to `pyproject.toml` to exclude paths from indexing and scanning:

```toml
[tool.docsight]
exclude = ["tests/", ".claude/", ".cursor/", "vendor/"]
```

Patterns support:
- **Directory prefixes**: `"tests/"` excludes everything under `tests/`
- **Glob/fnmatch**: `"*.generated.py"` excludes generated files
- **Bare names**: `"vendor"` matches `vendor/` as a directory prefix

### Data files

docsight stores all data in `.docsight/` (auto-added to `.gitignore`):

| File | Purpose |
|------|---------|
| `index.json` | Code elements with hashes |
| `edges.json` | Dependency graph edges |
| `file_analyses.json` | Per-file analysis results |
| `mappings.json` | Doc-to-code reference mappings |
| `state.json` | Verified baseline + last report |

### Coverage modes

By default, `coverage` counts only **public API elements** — classes and module-level functions. Methods are considered covered by their parent class's documentation status.

Use `--all-elements` to count every element (classes, functions, and methods).

### Staleness thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--max-hops` | 3 | Maximum graph traversal depth for transitive detection |
| Confidence decay | 0.6x per hop | How fast confidence drops with distance |
| Min confidence | 0.20 | Issues below this aren't reported |
| Stale threshold | >= 0.70 | Max issue confidence for STALE status |

---

## Interactive Graph

```bash
docsight graph
# Opens graph.html with interactive vis.js visualization
```

Features:
- **Dark theme** with color-coded nodes (classes=blue diamonds, methods=light blue, functions=green)
- **Stale nodes** highlighted in red
- **Search** to filter nodes by name
- **Hover tooltips** with element details
- **Edge types**: solid = calls, dashed = inherits

Export as JSON for programmatic use:

```bash
docsight graph --export json -o graph.json
```

---

## Claude Code Plugin

docsight ships as a Claude Code plugin. Install it to get slash commands in any conversation:

```bash
claude plugin add /path/to/docsight
```

### Available commands

| Command | What it does |
|---------|-------------|
| `/docsight:init` | Initialize and baseline the repo |
| `/docsight:check` | Check staleness, suggest fixes for stale docs |
| `/docsight:impact <target>` | Show blast radius of changing an element or file |
| `/docsight:diff [--base REF]` | Show which docs need updating for your changes |
| `/docsight:coverage [--gaps]` | Coverage stats or find where to write docs next |
| `/docsight:graph` | Generate and open the semantic-zoom dependency graph |
| `/docsight:report` | Generate and open the HTML report |

### Git hooks

```bash
docsight hooks install    # pre-push: fails if docs are stale
docsight hooks uninstall  # remove the hook
```

---

## Development

### Setup

```bash
git clone <repo-url>
cd docsight
pip install -e ".[dev]"
```

### Test

```bash
pytest -v           # 316 tests
pylint src/         # Target: 10.00/10
pylint tests/       # Target: clean
```

### Project layout

<details>
<summary>Click to expand</summary>

```
src/docsight/
├── cli.py                  # Click CLI (init, check, diff, impact, coverage, graph, report, hooks, ...)
├── config.py               # Load [tool.docsight] from pyproject.toml, exclude patterns
├── report.py               # Hierarchical HTML report generator
├── analyzer/
│   ├── base.py             # Data models (CodeElement, Parameter, GraphEdge, etc.)
│   ├── python_analyzer.py  # Python AST visitor with three-tier hashing
│   └── graph.py            # networkx dependency graph + semantic zoom HTML export
├── docs/
│   ├── scanner.py          # Markdown parser, extracts code references
│   └── mapper.py           # Resolves references to code element IDs
├── staleness/
│   ├── detector.py         # Direct + transitive staleness detection
│   └── reporter.py         # Rich CLI + JSON output formatting
└── store/
    └── json_store.py       # JSON persistence for index, mappings, state
```

</details>

### Architecture notes

- **`CodeElement.raw_calls`** stores unresolved AST call strings; the graph is the sole source of resolved dependencies
- **`body_hash`** hashes only body statements (not signature/decorators) so signature changes don't alter it
- **MODULE elements** per file use `ast.dump(tree)` for `body_hash` so comments/formatting don't trigger staleness
- **File-path references** in docs resolve to MODULE elements, not to every element in the file
- **`analyze_file()`** accepts an optional `repo_root` param to produce relative element IDs

---

## Built With

- [click](https://click.palletsprojects.com/) — CLI framework
- [networkx](https://networkx.org/) — Dependency graph operations
- [rich](https://rich.readthedocs.io/) — Terminal formatting
- [vis.js](https://visjs.org/) — Interactive graph visualization (CDN, no install)
- Python stdlib: `ast`, `hashlib`, `json`, `pathlib`, `subprocess`
