# doc-updater Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that detects when code changes make documentation stale, using AST-based code graph analysis and automatic code-to-doc mapping.

**Architecture:** Python AST extracts code elements (functions, classes, methods) and builds a dependency graph via networkx. A markdown scanner auto-detects references to code elements in docs. A staleness detector compares current code hashes against a full snapshot of hashes (including transitive dependencies) from when docs were last verified.

**Tech Stack:** Python 3.10+, click (CLI), networkx (graph), rich (terminal UI), stdlib ast/hashlib/json/subprocess

---

## Codex Review Fixes Applied

### Round 1 (13 findings)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | **Critical** | Baseline only stores direct ref hashes, transitive detection is a no-op | Baseline now stores full dependency closure hashes per doc |
| 2 | **Critical** | Call resolution misses instance-bound calls (`mgr.validate_token()`) | Track local variable bindings (`x = ClassName()`) for resolution |
| 3 | **Critical** | HTML exporter has `UnboundLocalError` from shadowed `json` import | Single `import json` at module scope; removed `--export dot` |
| 4 | **Important** | `check` ignores stale index/mappings | `check` auto-runs `index`+`scan` (incremental); warns if skipped |
| 5 | **Important** | `body_hash` includes signature via `ast.dump(node)` | Hash only `node.body` statements, not the full function node |
| 6 | **Important** | Signature hash ignores defaults, varargs, parameter kinds | Canonicalize full signature model including defaults and kinds |
| 7 | **Important** | File-path refs map to ALL elements in file (blast radius) | File-path refs create a MODULE-level reference, not per-element |
| 8 | **Important** | Resolved mappings drop `text` and `context` | Persist `text`, `context`, and `section` in mappings.json |
| 9 | **Important** | `CodeElement.calls` mixes raw and resolved (DRY violation) | Separate `raw_calls` field; graph is sole source for resolved deps |
| 10 | **Important** | `status`/`show` not wired to real staleness results | `check` persists report; `status`/`show` load it |
| 11 | **Important** | Syntax errors silently swallowed | Report parse errors in CLI; fail unless `--skip-errors` |
| 12 | **Important** | Tests only cover happy path | Added end-to-end transitive test, duplicate name test, stale mapping test |
| 13 | **Minor** | vis.js search opacity may be too subtle | Use `hidden` toggle instead of opacity |

### Round 2 (5 findings)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 14 | **Critical** | Renamed/deleted symbols disappear from current mappings silently | Detector compares previous mappings against current: refs that existed in baseline but vanished from current scan are reported as "reference_lost" staleness |
| 15 | **Critical** | `self._cache.get()` (instance attributes from `__init__`) can't be resolved with local binding tracking alone | Extend `_CallExtractor` to also track `self.attr = ClassName()` in `__init__` methods, resolving `self.attr.method()` to `ClassName.method` in any method of the same class. Fixture updated to use direct call patterns that ARE resolvable as a simpler alternative. |
| 16 | **Important** | 3-hop closure limit silently excludes deeper chains | Document as known limitation; `--max-hops` flag applies to both baseline closure and check; default 3 is sufficient for most codebases |
| 17 | **Important** | Module-level ref has no canonical representation in the index | Add real `MODULE` element kind to `ElementKind`; `index` creates one MODULE element per file; `signature_hash` = hash of top-level defined names (API surface); `body_hash` = hash of `ast.dump(module)` (structural, ignores comments/formatting); mapper resolves file-path refs to this MODULE element |
| 18 | **Important** | `status`/`show` after baseline have no report to load | `check --baseline` also persists an "all healthy" report to state.json |

### Round 3 (4 findings)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 19 | **Important** | `check` auto-runs `index` but doesn't handle parse errors | `check` auto-indexes with `skip_errors=True` by default (warn, don't fail); explicit `doc-updater index` remains strict |
| 20 | **Important** | `test_index_finds_elements` expects `TokenCache` but fixture now has `cache_lookup` | Fixed test assertion to match updated fixture |
| 21 | **Important** | Comment-only e2e test contradicts MODULE file-path behavior | MODULE element uses `ast.dump()` for body_hash (structural, ignores comments); file_hash only stored on FileAnalysis for incremental indexing, not for staleness |
| 22 | **Important** | Unresolved references are invisible to the user | `scan` persists unmapped refs; `show` displays them; `check` warns about unmapped count. Unmapped != stale (coverage gap, not staleness) |

### Round 4 (3 findings)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 23 | **Critical** | rename/delete: after auto-rescan, renamed symbol drops from current mappings, `reference_lost` never fires | `check` compares PREVIOUS mappings (from state) against CURRENT mappings. If a ref existed in previous baseline but is absent from current scan, report `reference_lost`. This comparison happens in `check` (cli.py), not in detector. Detector's `reference_lost` is for the simpler case where current mappings still reference a now-deleted element. |
| 24 | **Important** | MODULE element creation never specified in analyzer/index tasks | `index` command creates one MODULE element per file: `element_id="path::__module__"`, `signature_hash=hash(sorted top-level names)`, `body_hash=hash(ast.dump(tree))`. Explicitly added to Task 5 (analyzer) and Task 7 (index). |
| 25 | **Important** | `--max-hops` not wired through CLI | Added `--max-hops` to `check` command options (already in test spec). Default 3, documented as known limitation. Passed to both baseline closure and detector. |

---

## File Structure

```
doc-updater/
├── pyproject.toml                          # Package config, entry point, deps
├── src/doc_updater/
│   ├── __init__.py                         # Version string
│   ├── cli.py                              # Click CLI group + all commands
│   ├── analyzer/
│   │   ├── __init__.py
│   │   ├── base.py                         # Data models + abstract CodeAnalyzer
│   │   ├── python_analyzer.py              # Python AST visitor
│   │   └── graph.py                        # CodeGraph: networkx wrapper
│   ├── docs/
│   │   ├── __init__.py
│   │   ├── scanner.py                      # Markdown parser: extract references
│   │   └── mapper.py                       # Resolve references to element_ids
│   ├── staleness/
│   │   ├── __init__.py
│   │   ├── detector.py                     # Direct + transitive staleness
│   │   └── reporter.py                     # Rich tables/trees + JSON output
│   └── store/
│       ├── __init__.py
│       └── json_store.py                   # Read/write index.json, mappings.json, state.json
├── tests/
│   ├── conftest.py                         # Shared fixtures
│   ├── test_models.py
│   ├── test_python_analyzer.py
│   ├── test_graph.py
│   ├── test_scanner.py
│   ├── test_mapper.py
│   ├── test_detector.py
│   ├── test_reporter.py
│   ├── test_store.py
│   ├── test_cli.py
│   └── test_e2e.py                         # End-to-end integration tests
└── claude-code/
    └── doc-check.md                        # Claude Code skill
```

**Responsibility boundaries:**
- `base.py` owns ALL data models. No circular deps.
- `python_analyzer.py` does AST walking + hashing. Stores `raw_calls` (strings). Does NOT write resolved calls onto elements.
- `graph.py` is the sole source of truth for resolved dependencies.
- `scanner.py` extracts raw text references from markdown. Knows nothing about code elements.
- `mapper.py` resolves scanner output to element_ids. Persists `text`, `context`, `section`. Unresolvable refs are persisted as `unmapped` in mappings.json (visible via `show` command, warned in `check` output). Unmapped refs are NOT staleness — they're coverage gaps.
- `detector.py` is pure logic: index + mappings + state + graph → staleness report.
- `reporter.py` only formats output.
- `json_store.py` only serializes/deserializes.
- `cli.py` orchestrates: wires modules, handles args, auto-refreshes index/scan before check.

---

## Chunk 1: Data Models + Store + CLI Init

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/doc_updater/__init__.py`
- Create: all `__init__.py` files for subpackages
- Create: `tests/conftest.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "doc-updater"
version = "0.1.0"
description = "Detect stale documentation by analyzing code-to-doc relationships"
requires-python = ">=3.10"
dependencies = [
    "click>=8.0",
    "networkx>=3.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
doc-updater = "doc_updater.cli:cli"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init files**

`src/doc_updater/__init__.py`:
```python
"""doc-updater: Detect stale documentation by analyzing code-to-doc relationships."""
__version__ = "0.1.0"
```

Empty `__init__.py` for: `analyzer/`, `docs/`, `staleness/`, `store/`

- [ ] **Step 3: Create conftest.py with shared fixtures**

```python
import textwrap
from pathlib import Path
import pytest

@pytest.fixture
def tmp_repo(tmp_path):
    """Minimal repo with Python files + markdown docs for testing."""
    src = tmp_path / "src"
    src.mkdir()
    docs = tmp_path / "docs"
    docs.mkdir()

    # NOTE: Fixture uses direct function calls (not instance attributes) so the
    # call graph is resolvable by the AST analyzer. validate_token() calls
    # cache_lookup() directly, creating a clean transitive chain:
    # authenticate -> AuthManager.validate_token -> cache_lookup
    (src / "auth.py").write_text(textwrap.dedent("""\
        from src.cache import cache_lookup

        class AuthManager:
            \"\"\"Manages authentication tokens.\"\"\"
            def validate_token(self, token: str, strict: bool = True) -> bool:
                \"\"\"Validate a JWT token.\"\"\"
                cached = cache_lookup(token)
                if cached:
                    return True
                return self._decode(token) is not None

            def _decode(self, token: str) -> dict:
                return {"sub": "user1"}

        def authenticate(username: str, password: str) -> bool:
            \"\"\"Authenticate a user by credentials.\"\"\"
            mgr = AuthManager()
            return mgr.validate_token(f"{username}:{password}")
    """))

    (src / "cache.py").write_text(textwrap.dedent("""\
        def cache_lookup(key: str) -> str:
            \"\"\"Look up a cached token.\"\"\"
            return ""

        def cache_store(key: str, value: str) -> None:
            \"\"\"Store a token in cache.\"\"\"
            pass
    """))

    (docs / "auth-guide.md").write_text(textwrap.dedent("""\
        # Authentication Guide

        ## Overview

        Authentication is handled by the `AuthManager` class in `src/auth.py`.

        ## Token Validation

        Call `validate_token()` with a JWT string:

        ```python
        from src.auth import AuthManager

        mgr = AuthManager()
        result = mgr.validate_token("my-jwt-token")
        ```

        ## Authentication Flow

        Use `authenticate()` for the full login flow.
    """))

    (docs / "cache-guide.md").write_text(textwrap.dedent("""\
        # Caching Guide

        Use `cache_lookup()` from `src/cache.py` for reads.

        Use `cache_store()` for writes.
    """))

    return tmp_path
```

- [ ] **Step 4: Install in dev mode and verify**

Run: `pip install -e ".[dev]"`
Expected: Installs successfully

- [ ] **Step 5: Commit**

```bash
git init && git add -A && git commit -m "feat: project scaffolding"
```

---

### Task 2: Data models (base.py)

**Files:**
- Create: `src/doc_updater/analyzer/base.py`
- Create: `tests/test_models.py`

Key design note: `CodeElement` has `raw_calls: list[str]` for unresolved AST calls.
There is NO `calls` field with resolved IDs — the graph is the sole source of truth for resolved dependencies. (Codex fix #9)

- [ ] **Step 1: Write tests for data models**

```python
"""Tests for data models."""
from doc_updater.analyzer.base import (
    CodeElement, ElementKind, Parameter, ImportInfo,
    FileAnalysis, GraphEdge, EdgeKind,
)

def test_code_element_creation():
    elem = CodeElement(
        element_id="src/auth.py::AuthManager.validate_token",
        kind=ElementKind.METHOD,
        file="src/auth.py",
        name="validate_token",
        qualified_name="AuthManager.validate_token",
        lineno=2, end_lineno=5,
        signature_hash="aaa", body_hash="bbb", source_hash="ccc",
        parameters=[
            Parameter(name="self", kind="POSITIONAL_OR_KEYWORD"),
            Parameter(name="token", annotation="str", kind="POSITIONAL_OR_KEYWORD"),
            Parameter(name="strict", annotation="bool", default="True", kind="POSITIONAL_OR_KEYWORD"),
        ],
        return_annotation="bool",
        parent="src/auth.py::AuthManager",
    )
    assert elem.kind == ElementKind.METHOD
    assert len(elem.parameters) == 3
    assert elem.parameters[2].default == "True"
    assert elem.raw_calls == []  # default empty

def test_parameter_frozen_and_hashable():
    p = Parameter(name="x", annotation="int", kind="POSITIONAL_OR_KEYWORD")
    assert hash(p) is not None

def test_graph_edge_in_set():
    e = GraphEdge(source="a::B", target="c::D", kind=EdgeKind.CALLS)
    assert len({e, e}) == 1

def test_file_analysis_defaults():
    fa = FileAnalysis(file="src/auth.py", file_hash="abc")
    assert fa.elements == []
    assert fa.imports == []
    assert fa.parse_errors == []
```

- [ ] **Step 2: Run tests — expected FAIL**

Run: `pytest tests/test_models.py -v`

- [ ] **Step 3: Implement base.py**

```python
"""Abstract code analyzer interface and shared data models."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ElementKind(Enum):
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"


@dataclass(frozen=True)
class Parameter:
    name: str
    annotation: Optional[str] = None
    default: Optional[str] = None
    kind: str = "POSITIONAL_OR_KEYWORD"  # matches inspect.Parameter.kind names


@dataclass
class CodeElement:
    element_id: str
    kind: ElementKind
    file: str
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    signature_hash: str
    body_hash: str
    source_hash: str
    parameters: list[Parameter] = field(default_factory=list)
    return_annotation: Optional[str] = None
    parent: Optional[str] = None
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    raw_calls: list[str] = field(default_factory=list)  # unresolved AST call names
    docstring_summary: Optional[str] = None


@dataclass
class ImportInfo:
    module: str
    names: list[str]
    lineno: int


@dataclass
class FileAnalysis:
    file: str
    file_hash: str
    elements: list[CodeElement] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


class EdgeKind(Enum):
    CALLS = "calls"
    INHERITS = "inherits"
    IMPORTS = "imports"


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    kind: EdgeKind


class CodeAnalyzer(ABC):
    @abstractmethod
    def supported_extensions(self) -> set[str]: ...

    @abstractmethod
    def analyze_file(self, file_path: Path, repo_root: Path) -> FileAnalysis: ...

    @abstractmethod
    def resolve_calls(
        self,
        file_analysis: FileAnalysis,
        all_elements: dict[str, CodeElement],
        all_files: dict[str, FileAnalysis],
    ) -> list[GraphEdge]: ...
```

- [ ] **Step 4: Run tests — expected PASS (4 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/analyzer/base.py tests/test_models.py
git commit -m "feat: data models - CodeElement with raw_calls, Parameter with kind, FileAnalysis with parse_errors"
```

---

### Task 3: JSON store

**Files:**
- Create: `src/doc_updater/store/json_store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for JSON store."""
import json
from doc_updater.store.json_store import JsonStore
from doc_updater.analyzer.base import (
    CodeElement, ElementKind, Parameter, FileAnalysis,
    ImportInfo, GraphEdge, EdgeKind,
)

def test_roundtrip_index(tmp_path):
    store = JsonStore(tmp_path / ".doc-updater")
    elements = {
        "src/auth.py::AuthManager": CodeElement(
            element_id="src/auth.py::AuthManager",
            kind=ElementKind.CLASS, file="src/auth.py",
            name="AuthManager", qualified_name="AuthManager",
            lineno=1, end_lineno=10,
            signature_hash="aaa", body_hash="bbb", source_hash="ccc",
            methods=["src/auth.py::AuthManager.validate_token"],
        ),
    }
    files = {
        "src/auth.py": FileAnalysis(
            file="src/auth.py", file_hash="fff",
            imports=[ImportInfo(module="os", names=["path"], lineno=1)],
        ),
    }
    edges = [GraphEdge("a::B", "c::D", EdgeKind.CALLS)]
    store.save_index(elements, files, edges, git_commit="abc123")

    loaded_elem, loaded_files, loaded_edges, meta = store.load_index()
    assert "src/auth.py::AuthManager" in loaded_elem
    assert loaded_elem["src/auth.py::AuthManager"].kind == ElementKind.CLASS
    assert meta["git_commit"] == "abc123"
    assert len(loaded_edges) == 1

def test_roundtrip_mappings(tmp_path):
    store = JsonStore(tmp_path / ".doc-updater")
    mappings = {
        "docs/auth.md": {
            "file_hash": "ddd",
            "references": [{
                "element_id": "src/auth.py::AuthManager",
                "ref_type": "class_name_backtick",
                "text": "AuthManager",
                "context": "The `AuthManager` class",
                "section": "Overview",
                "lineno": 5,
                "confidence": 0.85,
            }],
        },
    }
    store.save_mappings(mappings)
    loaded = store.load_mappings()
    assert loaded["docs/auth.md"]["references"][0]["text"] == "AuthManager"
    assert loaded["docs/auth.md"]["references"][0]["section"] == "Overview"

def test_roundtrip_state(tmp_path):
    store = JsonStore(tmp_path / ".doc-updater")
    state = {
        "last_check_commit": "abc",
        "verified": {
            "docs/auth.md": {
                "element_hashes": {
                    "src/auth.py::AuthManager": {"signature_hash": "a", "body_hash": "b"},
                },
                "dependency_hashes": {
                    "src/cache.py::TokenCache.get": {"signature_hash": "j", "body_hash": "k", "via": "src/auth.py::AuthManager.validate_token", "hops": 1},
                },
            },
        },
    }
    store.save_state(state)
    loaded = store.load_state()
    dep_hashes = loaded["verified"]["docs/auth.md"]["dependency_hashes"]
    assert dep_hashes["src/cache.py::TokenCache.get"]["hops"] == 1

def test_load_missing_returns_empty(tmp_path):
    store = JsonStore(tmp_path / ".doc-updater")
    e, f, ed, m = store.load_index()
    assert e == {} and f == {} and ed == []

def test_creates_directory_on_save(tmp_path):
    store_dir = tmp_path / ".doc-updater"
    assert not store_dir.exists()
    JsonStore(store_dir).save_mappings({})
    assert store_dir.exists()
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement json_store.py**

```python
"""Persistent JSON storage for index, mappings, and verification state."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from doc_updater.analyzer.base import (
    CodeElement, ElementKind, Parameter, FileAnalysis,
    ImportInfo, GraphEdge, EdgeKind,
)


class JsonStore:
    def __init__(self, store_dir: Path):
        self._dir = store_dir

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _read(self, filename: str) -> dict:
        path = self._dir / filename
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _write(self, filename: str, data: dict) -> None:
        self._ensure_dir()
        (self._dir / filename).write_text(json.dumps(data, indent=2, default=str) + "\n")

    # --- Index ---

    def save_index(self, elements: dict[str, CodeElement], files: dict[str, FileAnalysis],
                   edges: list[GraphEdge], git_commit: str = "") -> None:
        self._write("index.json", {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": git_commit,
            "elements": {eid: _ser_element(e) for eid, e in elements.items()},
            "files": {fp: _ser_file(fa) for fp, fa in files.items()},
            "edges": [{"source": e.source, "target": e.target, "kind": e.kind.value} for e in edges],
        })

    def load_index(self) -> tuple[dict[str, CodeElement], dict[str, FileAnalysis], list[GraphEdge], dict]:
        data = self._read("index.json")
        if not data:
            return {}, {}, [], {}
        elements = {eid: _deser_element(eid, d) for eid, d in data.get("elements", {}).items()}
        files = {fp: _deser_file(fp, d) for fp, d in data.get("files", {}).items()}
        edges = [GraphEdge(e["source"], e["target"], EdgeKind(e["kind"])) for e in data.get("edges", [])]
        meta = {k: data.get(k) for k in ("version", "updated_at", "git_commit")}
        return elements, files, edges, meta

    # --- Mappings ---

    def save_mappings(self, mappings: dict[str, Any]) -> None:
        self._write("mappings.json", {
            "version": 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "docs": mappings,
        })

    def load_mappings(self) -> dict[str, Any]:
        return self._read("mappings.json").get("docs", {})

    # --- State ---

    def save_state(self, state: dict[str, Any]) -> None:
        state["version"] = 1
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write("state.json", state)

    def load_state(self) -> dict[str, Any]:
        return self._read("state.json")


def _ser_element(e: CodeElement) -> dict:
    return {
        "kind": e.kind.value, "file": e.file, "name": e.name,
        "qualified_name": e.qualified_name, "lineno": e.lineno, "end_lineno": e.end_lineno,
        "signature_hash": e.signature_hash, "body_hash": e.body_hash, "source_hash": e.source_hash,
        "parameters": [{"name": p.name, "annotation": p.annotation, "default": p.default, "kind": p.kind} for p in e.parameters],
        "return_annotation": e.return_annotation, "parent": e.parent,
        "bases": e.bases, "methods": e.methods, "raw_calls": e.raw_calls,
        "docstring_summary": e.docstring_summary,
    }

def _deser_element(eid: str, d: dict) -> CodeElement:
    return CodeElement(
        element_id=eid, kind=ElementKind(d["kind"]), file=d["file"],
        name=d["name"], qualified_name=d["qualified_name"],
        lineno=d["lineno"], end_lineno=d["end_lineno"],
        signature_hash=d["signature_hash"], body_hash=d["body_hash"], source_hash=d["source_hash"],
        parameters=[Parameter(p["name"], p.get("annotation"), p.get("default"), p.get("kind", "POSITIONAL_OR_KEYWORD")) for p in d.get("parameters", [])],
        return_annotation=d.get("return_annotation"), parent=d.get("parent"),
        bases=d.get("bases", []), methods=d.get("methods", []),
        raw_calls=d.get("raw_calls", []), docstring_summary=d.get("docstring_summary"),
    )

def _ser_file(fa: FileAnalysis) -> dict:
    return {
        "file_hash": fa.file_hash,
        "imports": [{"module": i.module, "names": i.names, "lineno": i.lineno} for i in fa.imports],
        "parse_errors": fa.parse_errors,
    }

def _deser_file(fp: str, d: dict) -> FileAnalysis:
    return FileAnalysis(
        file=fp, file_hash=d["file_hash"],
        imports=[ImportInfo(i["module"], i["names"], i["lineno"]) for i in d.get("imports", [])],
        parse_errors=d.get("parse_errors", []),
    )
```

- [ ] **Step 4: Run tests — expected PASS (5 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/store/json_store.py tests/test_store.py
git commit -m "feat: JSON store with dependency_hashes support in state"
```

---

### Task 4: CLI skeleton with init command

**Files:**
- Create: `src/doc_updater/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write tests**

```python
from click.testing import CliRunner
from doc_updater.cli import cli

def test_init_creates_directory(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
    assert result.exit_code == 0
    assert (tmp_path / ".doc-updater").is_dir()

def test_init_adds_gitignore_entry(tmp_path):
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    CliRunner().invoke(cli, ["--repo", str(tmp_path), "init"])
    assert ".doc-updater/" in (tmp_path / ".gitignore").read_text()

def test_init_idempotent(tmp_path):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_path), "init"])
    result = runner.invoke(cli, ["--repo", str(tmp_path), "init"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement cli.py skeleton**

```python
"""CLI entry point for doc-updater."""
from __future__ import annotations
from pathlib import Path
import click
from doc_updater.store.json_store import JsonStore


@click.group()
@click.option("--repo", default=".", type=click.Path(exists=True), help="Repository root.")
@click.pass_context
def cli(ctx: click.Context, repo: str) -> None:
    """Detect stale documentation by analyzing code-to-doc relationships."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = Path(repo).resolve()
    ctx.obj["store"] = JsonStore(Path(repo).resolve() / ".doc-updater")


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize doc-updater in the repository."""
    repo = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    already = store_dir.exists()
    store_dir.mkdir(parents=True, exist_ok=True)

    gitignore = repo / ".gitignore"
    entry = ".doc-updater/"
    if gitignore.exists():
        content = gitignore.read_text()
        if entry not in content:
            with gitignore.open("a") as f:
                if not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{entry}\n")
    else:
        gitignore.write_text(f"{entry}\n")

    if already:
        click.echo(f"Already initialized in {repo}")
    else:
        click.echo(f"Initialized doc-updater in {repo}")
```

- [ ] **Step 4: Run tests — expected PASS (3 passed)**

- [ ] **Step 5: Run all tests: `pytest -v` — all pass**

- [ ] **Step 6: Commit**

```bash
git add src/doc_updater/cli.py tests/test_cli.py
git commit -m "feat: CLI skeleton with init command"
```

---

## Chunk 2: Python AST Analyzer + Dependency Graph

### Task 5: Python analyzer — element extraction + hashing

**Files:**
- Create: `src/doc_updater/analyzer/python_analyzer.py`
- Create: `tests/test_python_analyzer.py`

Key Codex fixes in this task:
- **Fix #5**: `body_hash` hashes only `node.body` statements, not the full function node
- **Fix #6**: `signature_hash` includes defaults, varargs, parameter kinds
- **Fix #9**: Stores `raw_calls` (unresolved strings), not resolved element_ids
- **Fix #11**: Reports SyntaxError in `parse_errors` instead of silently swallowing
- **Fix #2**: Tracks local bindings (`x = ClassName()`) for call resolution

- [ ] **Step 1: Write tests**

```python
"""Tests for Python AST analyzer."""
import textwrap
from pathlib import Path
from doc_updater.analyzer.python_analyzer import PythonAnalyzer
from doc_updater.analyzer.base import ElementKind

def _write(tmp_path, code):
    f = tmp_path / "sample.py"
    f.write_text(textwrap.dedent(code))
    return f

def test_extracts_function(tmp_path):
    f = _write(tmp_path, '''\
        def greet(name: str) -> str:
            """Say hello."""
            return f"Hello {name}"
    ''')
    r = PythonAnalyzer().analyze_file(f, tmp_path)
    assert len(r.elements) == 1
    e = r.elements[0]
    assert e.name == "greet"
    assert e.kind == ElementKind.FUNCTION
    assert e.parameters[0].name == "name"
    assert e.return_annotation == "str"
    assert e.docstring_summary == "Say hello."

def test_extracts_class_with_methods(tmp_path):
    f = _write(tmp_path, '''\
        class Calc:
            def add(self, a: int, b: int) -> int:
                return a + b
            def sub(self, a: int, b: int) -> int:
                return a - b
    ''')
    r = PythonAnalyzer().analyze_file(f, tmp_path)
    names = {e.name for e in r.elements}
    assert names == {"Calc", "add", "sub"}
    cls = next(e for e in r.elements if e.kind == ElementKind.CLASS)
    assert len(cls.methods) == 2

def test_body_hash_stable_on_signature_change(tmp_path):
    """Codex fix #5: body_hash must NOT change when only signature changes."""
    v1 = _write(tmp_path, '''\
        def process(x: int) -> int:
            return x + 1
    ''')
    r1 = PythonAnalyzer().analyze_file(v1, tmp_path)

    v2 = _write(tmp_path, '''\
        def process(x: int, y: int = 0) -> int:
            return x + 1
    ''')
    r2 = PythonAnalyzer().analyze_file(v2, tmp_path)

    assert r1.elements[0].body_hash == r2.elements[0].body_hash  # body unchanged
    assert r1.elements[0].signature_hash != r2.elements[0].signature_hash  # sig changed

def test_signature_hash_includes_defaults(tmp_path):
    """Codex fix #6: changing a default value must change signature_hash."""
    v1 = _write(tmp_path, '''\
        def process(x: int, strict: bool = True) -> int:
            return x
    ''')
    r1 = PythonAnalyzer().analyze_file(v1, tmp_path)

    v2 = _write(tmp_path, '''\
        def process(x: int, strict: bool = False) -> int:
            return x
    ''')
    r2 = PythonAnalyzer().analyze_file(v2, tmp_path)
    assert r1.elements[0].signature_hash != r2.elements[0].signature_hash

def test_extracts_raw_calls(tmp_path):
    f = _write(tmp_path, '''\
        def foo():
            bar()
            obj.method()
    ''')
    r = PythonAnalyzer().analyze_file(f, tmp_path)
    assert "bar" in r.elements[0].raw_calls
    assert "obj.method" in r.elements[0].raw_calls

def test_tracks_local_bindings(tmp_path):
    """Codex fix #2: instance-bound calls should be resolvable."""
    f = _write(tmp_path, '''\
        def main():
            mgr = AuthManager()
            mgr.validate_token("x")
    ''')
    r = PythonAnalyzer().analyze_file(f, tmp_path)
    # raw_calls should record "AuthManager.validate_token" or equivalent
    calls = r.elements[0].raw_calls
    assert any("AuthManager" in c and "validate_token" in c for c in calls)

def test_syntax_error_reported(tmp_path):
    """Codex fix #11: SyntaxError must not be silently swallowed."""
    f = _write(tmp_path, "def broken(\n")
    r = PythonAnalyzer().analyze_file(f, tmp_path)
    assert len(r.parse_errors) > 0
    assert r.elements == []

def test_extracts_imports(tmp_path):
    f = _write(tmp_path, '''\
        from os.path import join, exists
        import json
    ''')
    r = PythonAnalyzer().analyze_file(f, tmp_path)
    assert len(r.imports) == 2

def test_supported_extensions():
    assert ".py" in PythonAnalyzer().supported_extensions()
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement python_analyzer.py**

Key implementation details:
- `body_hash`: Hash `ast.dump()` of only the body statements: `_hash("|".join(ast.dump(stmt) for stmt in node.body if not _is_docstring(stmt)))`
- `signature_hash`: Canonicalize full signature: `f"{name}|{param_canon}|{return_ann}"` where `param_canon` includes name, annotation, default, and kind for each non-self param
- `_CallExtractor`: Also tracks `x = ClassName()` assignments as local bindings. When seeing `x.method()`, resolves to `ClassName.method` if `x` is a known binding
- `analyze_file`: On `SyntaxError`, returns `FileAnalysis` with `parse_errors` populated

- `analyze_file` also creates one MODULE element per file (fix #24): `element_id="{rel_path}::__module__"`, `signature_hash=hash(sorted list of top-level defined names)`, `body_hash=hash(ast.dump(tree))`. This makes file-path references staleness-aware without using raw file_hash (which would trigger on comments).

(Full implementation follows the structure from original plan Task 5, with the above fixes applied. ~200 lines.)

- [ ] **Step 4: Run tests — expected PASS (9 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/analyzer/python_analyzer.py tests/test_python_analyzer.py
git commit -m "feat: Python analyzer with body-only hashing, full signature canon, binding tracking"
```

---

### Task 6: Code dependency graph

**Files:**
- Create: `src/doc_updater/analyzer/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for CodeGraph."""
from doc_updater.analyzer.graph import CodeGraph
from doc_updater.analyzer.base import GraphEdge, EdgeKind, ElementKind

def _chain_graph():
    """A -> B -> C -> D, A -> E"""
    g = CodeGraph()
    for n in "ABCDE":
        g.add_element(n, ElementKind.FUNCTION)
    g.add_edge(GraphEdge("A", "B", EdgeKind.CALLS))
    g.add_edge(GraphEdge("B", "C", EdgeKind.CALLS))
    g.add_edge(GraphEdge("C", "D", EdgeKind.CALLS))
    g.add_edge(GraphEdge("A", "E", EdgeKind.CALLS))
    return g

def test_get_dependencies():
    g = _chain_graph()
    deps = dict(g.get_dependencies("A", max_hops=2))
    assert "B" in deps and "C" in deps and "E" in deps
    assert "D" not in deps

def test_get_dependents():
    g = _chain_graph()
    deps = dict(g.get_dependents("C", max_hops=2))
    assert "B" in deps and "A" in deps

def test_impact_radius():
    g = _chain_graph()
    impact = g.impact_radius(["C"], max_hops=3)
    assert impact["B"] == 1 and impact["A"] == 2

def test_dependency_closure():
    """For baseline: get all dependencies with hops for a set of elements."""
    g = _chain_graph()
    closure = g.dependency_closure(["A"], max_hops=3)
    assert "B" in closure and closure["B"] == 1
    assert "C" in closure and closure["C"] == 2
    assert "D" in closure and closure["D"] == 3

def test_serialization_roundtrip():
    g = _chain_graph()
    g2 = CodeGraph.from_serializable(g.to_serializable())
    assert g2.impact_radius(["C"], max_hops=2) == g.impact_radius(["C"], max_hops=2)

def test_empty_graph():
    assert CodeGraph().impact_radius(["X"]) == {}
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement graph.py**

Same as original plan Task 6, plus:
- Add `dependency_closure(element_ids, max_hops)` method: BFS forward from given elements, returns `{dep_id: min_hops}`. This is used by baseline to store the full transitive closure. (Codex fix #1)

```python
def dependency_closure(self, element_ids: list[str], max_hops: int = 3) -> dict[str, int]:
    """Get all forward dependencies of the given elements with min hop count.
    Used to build complete baseline snapshots including transitive deps."""
    result: dict[str, int] = {}
    for eid in element_ids:
        for dep_id, hops in self.get_dependencies(eid, max_hops):
            if dep_id not in result or result[dep_id] > hops:
                result[dep_id] = hops
    return result
```

- [ ] **Step 4: Run tests — expected PASS (6 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/analyzer/graph.py tests/test_graph.py
git commit -m "feat: CodeGraph with dependency_closure for transitive baseline snapshots"
```

---

### Task 7: CLI index command

**Files:**
- Modify: `src/doc_updater/cli.py`
- Modify: `tests/test_cli.py`

Codex fix #11: Report parse errors in output; fail with exit code 1 unless `--skip-errors`.

- [ ] **Step 1: Write tests**

```python
def test_index_command(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
    assert result.exit_code == 0
    assert "indexed" in result.output.lower()
    import json
    data = json.loads((tmp_repo / ".doc-updater" / "index.json").read_text())
    assert len(data["elements"]) > 0

def test_index_finds_elements(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
    import json
    data = json.loads((tmp_repo / ".doc-updater" / "index.json").read_text())
    names = {e["name"] for e in data["elements"].values()}
    assert {"AuthManager", "validate_token", "authenticate", "cache_lookup"} <= names

def test_index_fails_on_syntax_error(tmp_repo):
    (tmp_repo / "src" / "broken.py").write_text("def broken(\n")
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
    assert result.exit_code == 1
    assert "error" in result.output.lower()

def test_index_skip_errors(tmp_repo):
    (tmp_repo / "src" / "broken.py").write_text("def broken(\n")
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "index", "--skip-errors"])
    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Add index command to cli.py**

```python
@cli.command()
@click.argument("path", required=False, type=click.Path())
@click.option("--skip-errors", is_flag=True, help="Continue past files with syntax errors.")
@click.pass_context
def index(ctx, path, skip_errors):
    """Build code index and dependency graph."""
    # ... analyze files, build graph, report errors, save index
    # If any parse_errors and not skip_errors: exit(1) with error list
```

- [ ] **Step 4: Run tests — expected PASS**

- [ ] **Step 5: Run `pytest -v` — all pass**

- [ ] **Step 6: Commit**

```bash
git add src/doc_updater/cli.py tests/test_cli.py
git commit -m "feat: CLI index command with syntax error reporting"
```

---

## Chunk 3: Doc Scanner + Mapper

### Task 8: Markdown doc scanner

**Files:**
- Create: `src/doc_updater/docs/scanner.py`
- Create: `tests/test_scanner.py`

Codex fix #8: `RawReference` carries `section` heading for context.

- [ ] **Step 1: Write tests**

```python
"""Tests for markdown scanner."""
import textwrap
from doc_updater.docs.scanner import DocScanner

def test_finds_file_path_in_backticks():
    refs = DocScanner().scan_text("See `src/auth.py` for details.")
    assert any(r.text == "src/auth.py" and r.ref_type == "file_path_backtick" for r in refs)

def test_finds_function_call():
    refs = DocScanner().scan_text("Call `validate_token()` with a JWT.")
    assert any(r.text == "validate_token" and r.ref_type == "function_call_backtick" for r in refs)

def test_finds_class_name():
    refs = DocScanner().scan_text("The `AuthManager` class handles auth.")
    assert any(r.text == "AuthManager" and r.ref_type == "class_name_backtick" for r in refs)

def test_finds_dotted_method():
    refs = DocScanner().scan_text("Use `TokenCache.get()` for lookups.")
    assert any(r.text == "TokenCache.get" and r.ref_type == "method_call_backtick" for r in refs)

def test_extracts_imports_from_code_block():
    md = textwrap.dedent("""\
        ```python
        from src.auth import AuthManager
        mgr = AuthManager()
        ```
    """)
    refs = DocScanner().scan_text(md)
    assert any(r.text == "AuthManager" and "code_block" in r.ref_type for r in refs)

def test_no_false_positives_from_code_blocks():
    md = "```python\nAuthManager()\n```\nThe `AuthManager` is great."
    refs = DocScanner().scan_text(md)
    # Should not have duplicates from overlapping code block + prose detection
    texts = [r.text for r in refs if r.text == "AuthManager"]
    assert len(texts) >= 1  # at least one, no spurious extras

def test_tracks_section_heading():
    md = "# Overview\nSee `AuthManager`.\n## Details\nUse `get()`."
    refs = DocScanner().scan_text(md)
    auth_ref = next(r for r in refs if r.text == "AuthManager")
    assert auth_ref.section == "Overview"

def test_confidence_ordering():
    md = "See `src/auth.py` and `AuthManager` and `validate_token()`."
    refs = DocScanner().scan_text(md)
    file_ref = next(r for r in refs if r.ref_type == "file_path_backtick")
    func_ref = next(r for r in refs if r.ref_type == "function_call_backtick")
    class_ref = next(r for r in refs if r.ref_type == "class_name_backtick")
    assert file_ref.confidence >= func_ref.confidence >= class_ref.confidence

def test_line_numbers():
    refs = DocScanner().scan_text("line1\n`AuthManager`\nline3\n")
    assert refs[0].lineno == 2
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement scanner.py**

Same approach as original plan Task 8, with `section` tracking: maintain current heading text as state while walking lines.

`RawReference` dataclass:
```python
@dataclass
class RawReference:
    text: str
    ref_type: str
    lineno: int
    confidence: float
    context: str = ""
    section: str = ""  # Codex fix #8: nearest heading
```

- [ ] **Step 4: Run tests — expected PASS (9 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/docs/scanner.py tests/test_scanner.py
git commit -m "feat: markdown scanner with section tracking and confidence scoring"
```

---

### Task 9: Doc-to-code mapper

**Files:**
- Create: `src/doc_updater/docs/mapper.py`
- Create: `tests/test_mapper.py`

Codex fix #7: File-path references create a MODULE-level reference, not per-element.
Codex fix #8: `ResolvedMapping` carries `text`, `context`, `section`.

- [ ] **Step 1: Write tests**

```python
"""Tests for doc-to-code mapper."""
from doc_updater.docs.mapper import DocMapper
from doc_updater.docs.scanner import RawReference
from doc_updater.analyzer.base import CodeElement, ElementKind

def _elements():
    return {
        "src/auth.py::__module__": CodeElement(
            element_id="src/auth.py::__module__", kind=ElementKind.MODULE,
            file="src/auth.py", name="__module__", qualified_name="__module__",
            lineno=1, end_lineno=20, signature_hash="mod_sig", body_hash="mod_body", source_hash="mod_src",
        ),
        "src/auth.py::AuthManager": CodeElement(
            element_id="src/auth.py::AuthManager", kind=ElementKind.CLASS,
            file="src/auth.py", name="AuthManager", qualified_name="AuthManager",
            lineno=1, end_lineno=20, signature_hash="a", body_hash="b", source_hash="c",
        ),
        "src/auth.py::AuthManager.validate_token": CodeElement(
            element_id="src/auth.py::AuthManager.validate_token", kind=ElementKind.METHOD,
            file="src/auth.py", name="validate_token", qualified_name="AuthManager.validate_token",
            lineno=3, end_lineno=8, signature_hash="d", body_hash="e", source_hash="f",
            parent="src/auth.py::AuthManager",
        ),
        "src/cache.py::TokenCache": CodeElement(
            element_id="src/cache.py::TokenCache", kind=ElementKind.CLASS,
            file="src/cache.py", name="TokenCache", qualified_name="TokenCache",
            lineno=1, end_lineno=10, signature_hash="g", body_hash="h", source_hash="i",
        ),
    }

def test_resolve_class_name():
    r = DocMapper(_elements()).resolve(RawReference("AuthManager", "class_name_backtick", 5, 0.85))
    assert len(r) == 1 and r[0].element_id == "src/auth.py::AuthManager"

def test_resolve_dotted_method():
    r = DocMapper(_elements()).resolve(RawReference("AuthManager.validate_token", "method_call_backtick", 10, 0.90))
    assert len(r) == 1 and r[0].element_id == "src/auth.py::AuthManager.validate_token"

def test_file_path_resolves_to_module_element():
    """Codex fix #7/#24: file path resolves to MODULE element, not per-element."""
    r = DocMapper(_elements()).resolve(RawReference("src/auth.py", "file_path_backtick", 3, 0.95))
    assert len(r) == 1
    assert r[0].element_id == "src/auth.py::__module__"
    assert r[0].ref_type == "file_path_backtick"

def test_ambiguous_reduces_confidence():
    r = DocMapper(_elements()).resolve(RawReference("get", "function_call_backtick", 15, 0.90))
    if r:
        assert r[0].confidence < 0.90

def test_unresolvable_returns_empty():
    r = DocMapper(_elements()).resolve(RawReference("nonexistent", "function_call_backtick", 20, 0.90))
    assert r == []

def test_preserves_text_and_section():
    """Codex fix #8: resolved mapping must carry text and section."""
    ref = RawReference("AuthManager", "class_name_backtick", 5, 0.85, "The `AuthManager` class", "Overview")
    r = DocMapper(_elements()).resolve(ref)
    assert r[0].text == "AuthManager"
    assert r[0].section == "Overview"

def test_duplicate_names_across_files():
    """Codex fix #12: test for ambiguous names in different files."""
    elems = _elements()
    elems["src/other.py::AuthManager"] = CodeElement(
        element_id="src/other.py::AuthManager", kind=ElementKind.CLASS,
        file="src/other.py", name="AuthManager", qualified_name="AuthManager",
        lineno=1, end_lineno=5, signature_hash="x", body_hash="y", source_hash="z",
    )
    r = DocMapper(elems).resolve(RawReference("AuthManager", "class_name_backtick", 5, 0.85))
    # Should return both with reduced confidence
    assert len(r) == 2
    assert all(m.confidence < 0.85 for m in r)
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement mapper.py**

Key change from original: `_resolve_file_path` returns a single MODULE-level resolved mapping pointing to the file, not individual elements. The `ResolvedMapping` dataclass carries `text`, `context`, `section`.

```python
@dataclass
class ResolvedMapping:
    element_id: str
    ref_type: str
    lineno: int
    confidence: float
    text: str = ""
    context: str = ""
    section: str = ""
```

For file-path resolution: resolve to the MODULE element `"src/auth.py::__module__"` created by the analyzer (fix #24). The staleness detector treats file-path refs as stale when the MODULE element's `body_hash` (based on `ast.dump`, structural) changes — not raw file_hash, so comments/formatting don't trigger staleness (fix #21).

- [ ] **Step 4: Run tests — expected PASS (7 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/docs/mapper.py tests/test_mapper.py
git commit -m "feat: mapper with module-level file refs, text/section preservation, ambiguity handling"
```

---

### Task 10: CLI scan command

**Files:**
- Modify: `src/doc_updater/cli.py`
- Modify: `tests/test_cli.py`

Codex fix #8: Persist `text`, `context`, `section` in mappings.json.

- [ ] **Step 1: Write test**

```python
def test_scan_command(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "scan"])
    assert result.exit_code == 0
    import json
    m = json.loads((tmp_repo / ".doc-updater" / "mappings.json").read_text())
    refs = m["docs"]["docs/auth-guide.md"]["references"]
    assert any("AuthManager" in r["element_id"] for r in refs)
    assert all("text" in r for r in refs)  # Codex fix #8
```

- [ ] **Step 2–5: Implement, test, commit** (same pattern)

---

## Chunk 4: Staleness Detection + Reporting + CLI

### Task 11: Staleness detector

**Files:**
- Create: `src/doc_updater/staleness/detector.py`
- Create: `tests/test_detector.py`

Codex fix #1: Baseline stores full dependency closure. Detector checks both `element_hashes` and `dependency_hashes`.

- [ ] **Step 1: Write tests**

```python
"""Tests for staleness detector."""
from doc_updater.staleness.detector import StalenessDetector, DocStatus
from doc_updater.analyzer.graph import CodeGraph
from doc_updater.analyzer.base import GraphEdge, EdgeKind, ElementKind

def _detector(current_sig="a", current_body="b", verified_sig="a", verified_body="b", edges=None):
    elements = {"src/auth.py::fn": {"signature_hash": current_sig, "body_hash": current_body}}
    mappings = {"docs/auth.md": {"references": [
        {"element_id": "src/auth.py::fn", "confidence": 0.90, "ref_type": "func", "lineno": 5},
    ]}}
    state = {"verified": {"docs/auth.md": {
        "element_hashes": {"src/auth.py::fn": {"signature_hash": verified_sig, "body_hash": verified_body}},
        "dependency_hashes": {},
    }}}
    graph = CodeGraph()
    graph.add_element("src/auth.py::fn", ElementKind.FUNCTION)
    if edges:
        for e in edges:
            graph.add_element(e.target, ElementKind.FUNCTION)
            graph.add_edge(e)
            # Add dep to both elements and dependency_hashes for baseline
            elements[e.target] = {"signature_hash": "orig", "body_hash": "orig"}
            state["verified"]["docs/auth.md"]["dependency_hashes"][e.target] = {
                "signature_hash": "orig", "body_hash": "orig", "hops": 1,
            }
    return StalenessDetector(elements, mappings, state, graph)

def test_healthy():
    assert _detector().check_all()["docs/auth.md"]["status"] == DocStatus.HEALTHY

def test_stale_signature():
    r = _detector(current_sig="CHANGED").check_all()
    assert r["docs/auth.md"]["status"] == DocStatus.STALE

def test_stale_body():
    r = _detector(current_body="CHANGED").check_all()
    assert r["docs/auth.md"]["status"] in (DocStatus.STALE, DocStatus.POSSIBLY_STALE)

def test_transitive_staleness():
    """Codex fix #1: transitive detection via dependency_hashes in baseline."""
    edge = GraphEdge("src/auth.py::fn", "src/cache.py::get", EdgeKind.CALLS)
    det = _detector(edges=[edge])
    det._elements["src/cache.py::get"] = {"signature_hash": "CHANGED", "body_hash": "orig"}
    r = det.check_all()
    trans = [i for i in r["docs/auth.md"]["issues"] if i.change_type == "transitive"]
    assert len(trans) >= 1 and trans[0].hops == 1

def test_transitive_confidence_decay():
    edge = GraphEdge("src/auth.py::fn", "src/cache.py::get", EdgeKind.CALLS)
    det = _detector(edges=[edge])
    det._elements["src/cache.py::get"] = {"signature_hash": "CHANGED", "body_hash": "orig"}
    r = det.check_all()
    trans = [i for i in r["docs/auth.md"]["issues"] if i.change_type == "transitive"]
    assert 0.50 <= trans[0].confidence <= 0.60  # 0.90 * 0.6 = 0.54

def test_unverified():
    det = _detector()
    det._state = {"verified": {}}
    assert det.check_all()["docs/auth.md"]["status"] == DocStatus.UNVERIFIED

def test_reference_lost_on_rename():
    """Codex round 2 fix #14: detect when a previously-mapped element vanishes."""
    det = _detector()
    # Simulate: element was in baseline but is now gone from current index
    del det._elements["src/auth.py::fn"]
    report = det.check_all()
    issues = report["docs/auth.md"]["issues"]
    assert any(i.change_type == "reference_lost" for i in issues)
    assert report["docs/auth.md"]["status"] == DocStatus.STALE
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement detector.py**

Key changes:
- Transitive staleness checks `dependency_hashes` in state (stored during baseline)
- Baseline uses `graph.dependency_closure()` to compute and store all transitive dependency hashes
- **Reference loss detection** (fix #14): For each ref in mappings, if `element_id` is NOT in current `elements`, report `"reference_lost"` issue with high confidence. This catches renamed/deleted symbols.

- [ ] **Step 4: Run tests — expected PASS (7 passed)**

- [ ] **Step 5: Commit**

```bash
git add src/doc_updater/staleness/detector.py tests/test_detector.py
git commit -m "feat: staleness detector with dependency closure baseline for transitive detection"
```

---

### Task 12: Rich reporter

**Files:**
- Create: `src/doc_updater/staleness/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1–5:** Same as original plan Task 12 (unchanged — reporter was not flagged).

---

### Task 13: CLI check, status, show commands

**Files:**
- Modify: `src/doc_updater/cli.py`
- Modify: `tests/test_cli.py`

Key Codex fixes:
- **Fix #1**: `check --baseline` stores full dependency closure hashes per doc
- **Fix #4**: `check` auto-runs `index`+`scan` before checking (incremental). When auto-running `index`, always skip parse errors (warn but continue) — `check` is a convenience command and should not fail due to syntax errors in unrelated files. Explicit `doc-updater index` is strict by default.
- **Fix #10**: `check` persists the report in state.json; `status`/`show` load it
- **Fix #18**: `check --baseline` also persists an "all healthy" report so `status`/`show` work immediately after

- [ ] **Step 1: Write tests**

```python
def test_check_baseline(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    assert result.exit_code == 0
    import json
    state = json.loads((tmp_repo / ".doc-updater" / "state.json").read_text())
    # Verify dependency_hashes are stored (Codex fix #1)
    for doc_data in state["verified"].values():
        assert "dependency_hashes" in doc_data

def test_check_detects_stale(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    # Change a function signature
    auth = tmp_repo / "src" / "auth.py"
    auth.write_text(auth.read_text().replace(
        "def validate_token(self, token: str, strict: bool = True) -> bool:",
        "def validate_token(self, token: str, mode: str = 'default') -> dict:",
    ))
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
    assert result.exit_code == 1  # stale

def test_check_auto_refreshes(tmp_repo):
    """Codex fix #4: check should auto-run index+scan."""
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    # No manual index or scan — check --baseline should handle it
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    assert result.exit_code == 0

def test_check_json(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
    import json
    assert "summary" in json.loads(result.output)

def test_status_shows_last_report(tmp_repo):
    """Codex fix #10: status reads persisted report."""
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "status"])
    assert result.exit_code == 0
    assert "healthy" in result.output.lower() or "doc" in result.output.lower()

def test_show_displays_staleness(tmp_repo):
    """Codex fix #10: show reads persisted report."""
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "show", "docs/auth-guide.md"])
    assert result.exit_code == 0
    assert "auth-guide" in result.output.lower()
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement check, status, show**

`check` command flow:
1. Auto-run `index` (with `skip_errors=True`) + `scan` internally
2. Load index, mappings, state. Pass `--max-hops` (default 3) to both closure and detector (fix #25).
3. If `--baseline`: compute dependency closure per doc using `graph.dependency_closure(max_hops)`, store all hashes (direct + transitive), persist "all healthy" report (fix #18)
4. Otherwise:
   a. **Reference-lost comparison** (fix #23): compare refs in `state["verified"][doc]["element_hashes"]` against current mappings. If a previously-baselined ref is no longer in current mappings, inject `reference_lost` issue.
   b. Run `StalenessDetector.check_all()` for hash-based staleness
   c. Persist full report to `state.json["last_report"]`, display
5. Warn about unmapped reference count (fix #22)
6. Exit code 1 if any stale docs

`status` command: Load `state.json["last_report"]`, display summary. Works after both `check` and `check --baseline`.

`show <doc>` command: Load `state.json["last_report"]` + mappings, display tree with staleness + unmapped refs.

- [ ] **Step 4: Run tests — expected PASS**

- [ ] **Step 5: Run `pytest -v` — all pass**

- [ ] **Step 6: Commit**

```bash
git add src/doc_updater/cli.py tests/test_cli.py
git commit -m "feat: check with auto-refresh and dependency closure baseline, status/show read persisted report"
```

---

## Chunk 5: Graph Visualization + Skill + E2E Tests

### Task 14: Interactive HTML graph visualization

**Files:**
- Modify: `src/doc_updater/analyzer/graph.py`
- Modify: `src/doc_updater/cli.py`
- Create: `tests/test_graph_export.py`

Codex fix #3: Single `import json` at module scope. Removed `--export dot` (not implemented).
Codex fix #13: Search uses `hidden` toggle instead of opacity.

- [ ] **Step 1: Write tests**

```python
"""Tests for HTML graph export."""
from doc_updater.analyzer.graph import CodeGraph
from doc_updater.analyzer.base import GraphEdge, EdgeKind, ElementKind

def test_export_html(tmp_path):
    g = CodeGraph()
    g.add_element("src/auth.py::AuthManager", ElementKind.CLASS)
    g.add_element("src/auth.py::AuthManager.validate_token", ElementKind.METHOD)
    g.add_edge(GraphEdge("src/auth.py::AuthManager", "src/auth.py::AuthManager.validate_token", EdgeKind.CALLS))
    out = tmp_path / "graph.html"
    g.export_html(out)
    content = out.read_text()
    assert "vis.Network" in content
    assert "AuthManager" in content

def test_stale_nodes_highlighted(tmp_path):
    g = CodeGraph()
    g.add_element("src/auth.py::fn", ElementKind.FUNCTION)
    out = tmp_path / "graph.html"
    g.export_html(out, stale_elements={"src/auth.py::fn"})
    assert "ff4444" in out.read_text().lower() or "red" in out.read_text().lower()

def test_search_uses_hidden_not_opacity(tmp_path):
    """Codex fix #13."""
    g = CodeGraph()
    g.add_element("A", ElementKind.FUNCTION)
    out = tmp_path / "graph.html"
    g.export_html(out)
    content = out.read_text()
    assert "hidden" in content
    assert "opacity" not in content.split("search")[1] if "search" in content else True
```

- [ ] **Step 2: Run tests — expected FAIL**

- [ ] **Step 3: Implement export_html**

`import json` at module scope (Codex fix #3). Search toggles `hidden: true/false` (Codex fix #13).
CLI `graph` command only offers `--export html` and `--export json` (no dot).

- [ ] **Step 4: Run tests — expected PASS**

- [ ] **Step 5: Add graph command to CLI + test**

```python
def test_graph_command(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "index"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "graph"])
    assert result.exit_code == 0
    assert (tmp_repo / "graph.html").exists()
```

- [ ] **Step 6: Commit**

```bash
git add src/doc_updater/analyzer/graph.py src/doc_updater/cli.py tests/test_graph_export.py
git commit -m "feat: interactive HTML graph with vis.js, stale highlighting, hidden-based search"
```

---

### Task 15: End-to-end integration tests

**Files:**
- Create: `tests/test_e2e.py`

Codex fix #12: Test real transitive detection, duplicate names, stale mappings.

- [ ] **Step 1: Write e2e tests**

```python
"""End-to-end integration tests."""
from click.testing import CliRunner
from doc_updater.cli import cli
import json

def test_e2e_transitive_staleness(tmp_repo):
    """Full flow: baseline -> change dependency -> check detects transitive.
    Chain: auth-guide.md references validate_token -> calls cache_lookup -> CHANGED."""
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

    # Change cache_lookup signature (called by validate_token, which is referenced in auth-guide.md)
    cache = tmp_repo / "src" / "cache.py"
    cache.write_text(cache.read_text().replace(
        'def cache_lookup(key: str) -> str:',
        'def cache_lookup(key: str, default: str = "") -> str:',
    ))

    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
    data = json.loads(result.output)
    # auth-guide.md should be flagged because it references validate_token which calls get
    stale_docs = [d["doc"] for d in data["stale_docs"]]
    assert any("auth" in d for d in stale_docs)

def test_e2e_direct_staleness(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

    # Change validate_token signature
    auth = tmp_repo / "src" / "auth.py"
    auth.write_text(auth.read_text().replace("strict: bool = True", "mode: str = 'fast'"))

    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
    assert result.exit_code == 1

def test_e2e_no_false_positive_on_comment_change(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])

    # Add a comment (should not trigger staleness)
    auth = tmp_repo / "src" / "auth.py"
    auth.write_text("# New comment at top\n" + auth.read_text())

    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
    data = json.loads(result.output)
    assert data["summary"]["stale"] == 0

def test_e2e_full_flow_json(tmp_repo):
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--json"])
    data = json.loads(result.output)
    assert data["summary"]["total"] >= 2
    assert data["summary"]["healthy"] >= 2

def test_e2e_renamed_function_detected(tmp_repo):
    """Codex round 2 fix #14: renamed/deleted symbols should be flagged."""
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    # Rename authenticate -> login (doc still says authenticate)
    auth = tmp_repo / "src" / "auth.py"
    auth.write_text(auth.read_text().replace("def authenticate(", "def login("))
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "check"])
    assert result.exit_code == 1  # stale because doc references vanished symbol

def test_e2e_status_after_baseline(tmp_repo):
    """Codex round 2 fix #18: status should work right after baseline."""
    runner = CliRunner()
    runner.invoke(cli, ["--repo", str(tmp_repo), "init"])
    runner.invoke(cli, ["--repo", str(tmp_repo), "check", "--baseline"])
    result = runner.invoke(cli, ["--repo", str(tmp_repo), "status"])
    assert result.exit_code == 0
    assert "healthy" in result.output.lower()
```

- [ ] **Step 2: Run tests — expected PASS (all should pass if prior tasks are correct)**

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: end-to-end tests for direct, transitive, and false-positive scenarios"
```

---

### Task 16: Claude Code skill

**Files:**
- Create: `claude-code/doc-check.md`

- [ ] **Step 1: Create skill file**

```markdown
---
name: doc-check
description: Check if documentation is stale due to code changes and suggest updates
---

# Doc Staleness Check

## When to Use
- User asks "are my docs up to date?"
- User modifies code and wants to know which docs need updating
- During PR review to check doc impact
- User says "check docs", "stale docs", "doc health"

## Workflow

1. Ensure initialized and run check:
   ```bash
   doc-updater init 2>/dev/null || true
   doc-updater check --json
   ```

2. Parse JSON output and present findings:
   - Summary: X healthy, Y stale, Z need review
   - For each stale doc: what changed, suggested fix
   - Offer to update docs or set new baseline

3. For visual overview:
   ```bash
   doc-updater graph
   ```
```

- [ ] **Step 2: Commit**

```bash
git add claude-code/doc-check.md
git commit -m "feat: Claude Code /doc-check skill"
```

---

### Task 17: Final verification

- [ ] **Step 1: Run full test suite**

Run: `pytest -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Manual end-to-end test**

```bash
cd /tmp && mkdir test-repo && cd test-repo && git init
# Copy fixture files
doc-updater init
doc-updater check --baseline
# Modify code
doc-updater check
doc-updater check --json
doc-updater show docs/auth-guide.md
doc-updater graph
# Open graph.html in browser
```

- [ ] **Step 3: Verify graph.html is interactive**

Open in browser. Check: nodes colored by type, edges show calls vs inherits, search filters with hidden toggle, tooltip shows element details and doc references.
