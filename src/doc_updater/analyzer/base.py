"""Base data models for the doc-updater code analyzer."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ElementKind(str, Enum):
    """Kinds of code elements that can be analyzed."""

    FUNCTION = "FUNCTION"
    CLASS = "CLASS"
    METHOD = "METHOD"
    MODULE = "MODULE"


@dataclass(frozen=True)
class Parameter:
    """A single parameter in a function or method signature."""

    name: str
    annotation: Optional[str]
    default: Optional[str]
    kind: str = "POSITIONAL_OR_KEYWORD"


@dataclass
class CodeElement:
    """A code element (function, class, method, or module) extracted from source."""

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
    parameters: list[Parameter]
    return_annotation: Optional[str]
    parent: Optional[str]
    bases: list[str]
    methods: list[str]
    raw_calls: list[str]
    docstring_summary: Optional[str]


@dataclass
class ImportInfo:
    """Information about a single import statement."""

    module: str
    names: list[str]
    alias: Optional[str]
    lineno: int


@dataclass
class FileAnalysis:
    """Analysis result for a single source file."""

    file: str
    elements: list[CodeElement]
    imports: list[ImportInfo]
    parse_errors: list[str]


class EdgeKind(str, Enum):
    """Kinds of edges in the code dependency graph."""

    CALLS = "CALLS"
    INHERITS = "INHERITS"
    IMPORTS = "IMPORTS"
    DOCUMENTS = "DOCUMENTS"


@dataclass(frozen=True)
class GraphEdge:
    """A directed edge in the code dependency graph."""

    source: str
    target: str
    kind: EdgeKind


class CodeAnalyzer(abc.ABC):
    """Abstract base class for language-specific code analyzers."""

    @abc.abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return the file extensions this analyzer handles (e.g. ['.py'])."""

    @abc.abstractmethod
    def analyze_file(self, path: Path) -> FileAnalysis:
        """Parse a source file and return its analysis."""

    @abc.abstractmethod
    def resolve_calls(
        self,
        elements: dict[str, CodeElement],
        analyses: dict[str, FileAnalysis],
    ) -> list[GraphEdge]:
        """Resolve raw_calls references into typed graph edges."""
