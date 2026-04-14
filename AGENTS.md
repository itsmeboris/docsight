# docsight Agent Instructions

## Project Overview
- Python CLI tool that detects stale documentation by analyzing code-to-doc relationships
- Uses AST-based code analysis, dependency graphs, and automatic doc-to-code mapping
- CLI entry point: `docsight` (click-based), source in `src/docsight/`

## Build & Test
- Install: `pip install -e ".[dev]"`
- Test: `pytest -v` (316 tests, target 95%+ coverage)
- Lint: `pylint src/docsight/` and `pylint tests/` (target 10.00/10)
- All pylint config is in `pyproject.toml` under `[tool.pylint.*]`
- All test classes and methods must have docstrings (pylint enforces this)
- Stop hooks run pylint on tests too — fix before committing

## Architecture Rules
- `CodeElement.raw_calls` stores unresolved AST call strings; the graph is the sole source of resolved dependencies
- `body_hash` must hash only body statements (not signature/decorators), so signature changes don't alter body_hash
- `signature_hash` must include default values and parameter kinds (changing `strict=True` to `strict=False` must change it)
- MODULE elements per file use `ast.dump(tree)` for body_hash so comments/formatting don't trigger staleness
- File-path doc references resolve to the MODULE element, not to every element in the file
- Mappings use `"mapped"` and `"unmapped"` keys per doc (not `"references"`)
- State format_version=2 uses relative paths; version <2 is treated as UNVERIFIED to prevent false-green results
- `check` command auto-runs index (skip_errors=True) + scan before detection
- Reference-lost detection compares previous baseline refs against current scan results
- All commands that walk files (`index`, `scan`, `check`, `graph`, `report`, `coverage`) must respect exclude patterns from `[tool.docsight]` in pyproject.toml
- Default coverage metric counts only public API elements (classes + module-level functions); methods are covered by their parent class — use `--all-elements` for full count
- `config.py` must never crash on malformed pyproject.toml values — every intermediate value (`tool`, `docsight`, `exclude`) must be type-checked before use

## Conventions
- `visit_Assign`/`visit_Call` method names follow ast.NodeVisitor convention (pylint disabled per-method)
- HTML graph export must html.escape all user-controlled content in tooltips; JSON embedded in `<script>` tags must have `</` escaped to `<\/` to prevent script-tag breakout
- When embedding JSON via template replacement, inject the data blob LAST so placeholder strings inside user data are never re-processed
- max_hops flag must be enforced in both baseline closure and detection
- `analyze_file()` accepts optional `repo_root` param for relative path generation
- `clean` command: gitignore cleanup runs BEFORE rmtree to avoid stale state on partial failure
- CLI commands that add `docsight init` must also consider `docsight clean` for symmetry
- `init` adds only `.docsight/` to `.gitignore` — all generated files live inside it
- Prefer lightweight hierarchical HTML (`report` command) over heavy vis.js graph for visualization
- vis.js graph with 400+ nodes is unusable — semantic zoom (file → class → method) is the default; `--flat` for old behavior
- Semantic zoom graph must distinguish `stale` (red) from `possibly_stale` (amber) — never lump both as stale
- MODULE element IDs must be mapped to their file node in the JS graph so IMPORTS edges resolve correctly
- Generated files (graph.html, report.html, graph.json) default to `.docsight/` so cleanup is just `docsight clean`
- Internal helpers `_run_index` and `_run_scan` accept an `exclude` kwarg; all callers must pass it
- Config reading from pyproject.toml is in `config.py` (`load_config`, `get_exclude_patterns`, `should_exclude`)
- `diff` deleted-element detection must use exclude patterns (not file existence) to suppress false positives — files that fail to parse must still flag their missing elements
- `impact` command uses reverse BFS (`impact_radius`) and cross-references mappings to find affected docs
- `coverage --gaps` finds files with zero documented public API, sorted by dependency weight
- `init` auto-runs index + scan + baseline by default; use `--no-baseline` to skip
- Pre-push hook must drain stdin (`cat > /dev/null`) and guard with `command -v docsight` for portability
- `diff --base REF` must use three-dot merge-base syntax (`REF...HEAD`) for correct PR semantics
- Claude Code plugin lives in `.claude-plugin/` + `commands/` following the codex-plugin-cc pattern
