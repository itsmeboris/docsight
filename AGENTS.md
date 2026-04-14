# doc-updater Agent Instructions

## Project Overview
- Python CLI tool that detects stale documentation by analyzing code-to-doc relationships
- Uses AST-based code analysis, dependency graphs, and automatic doc-to-code mapping
- CLI entry point: `doc-updater` (click-based), source in `src/doc_updater/`

## Build & Test
- Install: `pip install -e ".[dev]"`
- Test: `pytest -v` (241 tests, target 96%+ coverage)
- Lint: `pylint src/doc_updater/` and `pylint tests/` (target 10.00/10)
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

## Conventions
- `visit_Assign`/`visit_Call` method names follow ast.NodeVisitor convention (pylint disabled per-method)
- HTML graph export must html.escape all user-controlled content in tooltips
- max_hops flag must be enforced in both baseline closure and detection
- `analyze_file()` accepts optional `repo_root` param for relative path generation
- `clean` command: gitignore cleanup runs BEFORE rmtree to avoid stale state on partial failure
- CLI commands that add `doc-updater init` must also consider `doc-updater clean` for symmetry
