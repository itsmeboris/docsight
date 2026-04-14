"""JSON-based persistence store for docsight index and state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docsight.analyzer.base import (
    CodeElement,
    EdgeKind,
    ElementKind,
    FileAnalysis,
    GraphEdge,
    ImportInfo,
    Parameter,
)


def _serialize_parameter(p: Parameter) -> dict[str, Any]:
    return {
        "name": p.name,
        "annotation": p.annotation,
        "default": p.default,
        "kind": p.kind,
    }


def _deserialize_parameter(d: dict[str, Any]) -> Parameter:
    return Parameter(
        name=d["name"],
        annotation=d.get("annotation"),
        default=d.get("default"),
        kind=d.get("kind", "POSITIONAL_OR_KEYWORD"),
    )


def _serialize_element(el: CodeElement) -> dict[str, Any]:
    return {
        "element_id": el.element_id,
        "kind": el.kind.value,
        "file": el.file,
        "name": el.name,
        "qualified_name": el.qualified_name,
        "lineno": el.lineno,
        "end_lineno": el.end_lineno,
        "signature_hash": el.signature_hash,
        "body_hash": el.body_hash,
        "source_hash": el.source_hash,
        "parameters": [_serialize_parameter(p) for p in el.parameters],
        "return_annotation": el.return_annotation,
        "parent": el.parent,
        "bases": el.bases,
        "methods": el.methods,
        "raw_calls": el.raw_calls,
        "docstring_summary": el.docstring_summary,
    }


def _deserialize_element(d: dict[str, Any]) -> CodeElement:
    return CodeElement(
        element_id=d["element_id"],
        kind=ElementKind(d["kind"]),
        file=d["file"],
        name=d["name"],
        qualified_name=d["qualified_name"],
        lineno=d["lineno"],
        end_lineno=d["end_lineno"],
        signature_hash=d["signature_hash"],
        body_hash=d["body_hash"],
        source_hash=d["source_hash"],
        parameters=[_deserialize_parameter(p) for p in d.get("parameters", [])],
        return_annotation=d.get("return_annotation"),
        parent=d.get("parent"),
        bases=d.get("bases", []),
        methods=d.get("methods", []),
        raw_calls=d.get("raw_calls", []),
        docstring_summary=d.get("docstring_summary"),
    )


def _serialize_import(imp: ImportInfo) -> dict[str, Any]:
    return {
        "module": imp.module,
        "names": imp.names,
        "alias": imp.alias,
        "lineno": imp.lineno,
    }


def _deserialize_import(d: dict[str, Any]) -> ImportInfo:
    return ImportInfo(
        module=d["module"],
        names=d.get("names", []),
        alias=d.get("alias"),
        lineno=d["lineno"],
    )


def _serialize_file_analysis(fa: FileAnalysis) -> dict[str, Any]:
    return {
        "file": fa.file,
        "elements": [_serialize_element(el) for el in fa.elements],
        "imports": [_serialize_import(imp) for imp in fa.imports],
        "parse_errors": fa.parse_errors,
    }


def _deserialize_file_analysis(d: dict[str, Any]) -> FileAnalysis:
    return FileAnalysis(
        file=d["file"],
        elements=[_deserialize_element(el) for el in d.get("elements", [])],
        imports=[_deserialize_import(imp) for imp in d.get("imports", [])],
        parse_errors=d.get("parse_errors", []),
    )


def _serialize_edge(edge: GraphEdge) -> dict[str, Any]:
    return {
        "source": edge.source,
        "target": edge.target,
        "kind": edge.kind.value,
    }


def _deserialize_edge(d: dict[str, Any]) -> GraphEdge:
    return GraphEdge(
        source=d["source"],
        target=d["target"],
        kind=EdgeKind(d["kind"]),
    )


class JsonStore:
    """Persist and load docsight data as JSON files."""

    INDEX_FILE = "index.json"
    MAPPINGS_FILE = "mappings.json"
    STATE_FILE = "state.json"
    FILE_ANALYSES_FILE = "file_analyses.json"
    EDGES_FILE = "edges.json"

    def __init__(self, store_dir: Path) -> None:
        self._dir = Path(store_dir)

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _write(self, filename: str, data: Any) -> None:
        self._ensure_dir()
        (self._dir / filename).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _read(self, filename: str) -> Any:
        path = self._dir / filename
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- index (element_id -> CodeElement) ---------------------------------

    def save_index(self, index: dict[str, CodeElement]) -> None:
        """Persist element index to index.json."""
        self._write(
            self.INDEX_FILE,
            {eid: _serialize_element(el) for eid, el in index.items()},
        )

    def load_index(self) -> dict[str, CodeElement]:
        """Load element index; returns empty dict if file is missing."""
        data = self._read(self.INDEX_FILE)
        if data is None:
            return {}
        return {eid: _deserialize_element(d) for eid, d in data.items()}

    # ---- mappings (doc_path -> list[reference dict]) -----------------------

    def save_mappings(self, mappings: dict[str, list[dict]]) -> None:
        """Persist doc-to-element mappings to mappings.json."""
        self._write(self.MAPPINGS_FILE, mappings)

    def load_mappings(self) -> dict[str, list[dict]]:
        """Load doc-to-element mappings; returns empty dict if file is missing."""
        data = self._read(self.MAPPINGS_FILE)
        if data is None:
            return {}
        return data

    # ---- state (doc_path -> staleness state) --------------------------------

    def save_state(self, state: dict[str, dict]) -> None:
        """Persist staleness state to state.json."""
        self._write(self.STATE_FILE, state)

    def load_state(self) -> dict[str, dict]:
        """Load staleness state; returns empty dict if file is missing."""
        data = self._read(self.STATE_FILE)
        if data is None:
            return {}
        return data

    # ---- file analyses (file_path -> FileAnalysis) -------------------------

    def save_file_analyses(self, analyses: dict[str, FileAnalysis]) -> None:
        """Persist per-file analysis results."""
        self._write(
            self.FILE_ANALYSES_FILE,
            {fp: _serialize_file_analysis(fa) for fp, fa in analyses.items()},
        )

    def load_file_analyses(self) -> dict[str, FileAnalysis]:
        """Load per-file analysis results; returns empty dict if file is missing."""
        data = self._read(self.FILE_ANALYSES_FILE)
        if data is None:
            return {}
        return {fp: _deserialize_file_analysis(d) for fp, d in data.items()}

    # ---- graph edges --------------------------------------------------------

    def save_edges(self, edges: list[GraphEdge]) -> None:
        """Persist graph edges."""
        self._write(self.EDGES_FILE, [_serialize_edge(e) for e in edges])

    def load_edges(self) -> list[GraphEdge]:
        """Load graph edges; returns empty list if file is missing."""
        data = self._read(self.EDGES_FILE)
        if data is None:
            return []
        return [_deserialize_edge(d) for d in data]
