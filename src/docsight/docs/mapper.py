"""Doc-to-code mapper that resolves raw references to concrete element IDs."""

from __future__ import annotations

from dataclasses import dataclass

from docsight.analyzer.base import CodeElement, ElementKind
from docsight.docs.scanner import RawReference


@dataclass
class ResolvedMapping:
    """A resolved reference from a doc to a code element."""

    element_id: str
    ref_type: str
    lineno: int
    confidence: float
    text: str = ""
    context: str = ""
    section: str = ""


class DocMapper:
    """Resolve RawReferences to CodeElement IDs using index lookups."""

    def __init__(self, elements: dict[str, CodeElement]) -> None:
        self._elements = elements

        # qualified_name -> list[element_id]
        self._by_qualified: dict[str, list[str]] = {}
        # simple name -> list[element_id]
        self._by_name: dict[str, list[str]] = {}
        # file path -> module element_id
        self._by_file_module: dict[str, str] = {}

        for eid, el in elements.items():
            self._by_qualified.setdefault(el.qualified_name, []).append(eid)
            self._by_name.setdefault(el.name, []).append(eid)

            if el.kind == ElementKind.MODULE:
                self._by_file_module[el.file] = eid

    def resolve(self, ref: RawReference) -> list[ResolvedMapping]:
        """Resolve a RawReference to zero or more ResolvedMappings."""
        text = ref.text

        if ref.ref_type == "file_path_backtick":
            return self._resolve_file_path(ref)

        # Try qualified_name match first (exact)
        candidates = self._by_qualified.get(text)
        if candidates:
            return self._build_mappings(candidates, ref)

        # For dotted names (e.g. "ClassName.method"), try class+method split
        if "." in text:
            return self._resolve_dotted(ref)

        # Fall back to simple name match
        candidates = self._by_name.get(text)
        if candidates:
            return self._build_mappings(candidates, ref)

        return []

    def _resolve_file_path(self, ref: RawReference) -> list[ResolvedMapping]:
        """Resolve a file path reference to its MODULE element."""
        module_eid = self._by_file_module.get(ref.text)
        if module_eid is None:
            return []
        return [
            ResolvedMapping(
                element_id=module_eid,
                ref_type=ref.ref_type,
                lineno=ref.lineno,
                confidence=ref.confidence,
                text=ref.text,
                context=ref.context,
                section=ref.section,
            )
        ]

    def _resolve_dotted(self, ref: RawReference) -> list[ResolvedMapping]:
        """Resolve a dotted name by looking up method name within a class context."""
        class_name, method_name = ref.text.split(".", 1)
        # Find method elements whose qualified_name ends with the dotted suffix
        dotted_suffix = f"{class_name}.{method_name}"
        candidates = [
            eid
            for eid, el in self._elements.items()
            if el.qualified_name.endswith(dotted_suffix)
            and el.name == method_name
        ]
        if candidates:
            return self._build_mappings(candidates, ref)
        return []

    def _build_mappings(
        self, candidates: list[str], ref: RawReference
    ) -> list[ResolvedMapping]:
        """Build ResolvedMappings from a list of candidate element IDs."""
        count = len(candidates)
        adjusted_confidence = ref.confidence / count

        if adjusted_confidence < 0.10:
            return []

        return [
            ResolvedMapping(
                element_id=eid,
                ref_type=ref.ref_type,
                lineno=ref.lineno,
                confidence=adjusted_confidence,
                text=ref.text,
                context=ref.context,
                section=ref.section,
            )
            for eid in candidates
        ]
