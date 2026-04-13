"""Tests for doc_updater.analyzer.base data models."""

import pytest
from doc_updater.analyzer.base import (
    CodeElement,
    EdgeKind,
    ElementKind,
    FileAnalysis,
    GraphEdge,
    ImportInfo,
    Parameter,
)


class TestElementKind:
    @pytest.mark.parametrize(
        "member",
        ["FUNCTION", "CLASS", "METHOD", "MODULE"],
    )
    def test_has_member(self, member):
        assert hasattr(ElementKind, member)

    def test_values_are_strings(self):
        for kind in ElementKind:
            assert isinstance(kind.value, str)


class TestParameter:
    def test_basic_creation(self):
        p = Parameter(name="x", annotation="int", default=None)
        assert p.name == "x"
        assert p.annotation == "int"
        assert p.default is None

    def test_default_kind(self):
        p = Parameter(name="y", annotation="str", default="hello")
        assert p.kind == "POSITIONAL_OR_KEYWORD"

    def test_custom_kind(self):
        p = Parameter(name="z", annotation="int", default=None, kind="KEYWORD_ONLY")
        assert p.kind == "KEYWORD_ONLY"

    def test_frozen_immutable(self):
        p = Parameter(name="a", annotation="int", default=0)
        with pytest.raises((AttributeError, TypeError)):
            p.name = "b"  # type: ignore[misc]

    def test_hashable(self):
        p1 = Parameter(name="a", annotation="int", default=0)
        p2 = Parameter(name="a", annotation="int", default=0)
        assert hash(p1) == hash(p2)
        s = {p1, p2}
        assert len(s) == 1

    def test_unequal_parameters_have_different_hash(self):
        p1 = Parameter(name="a", annotation="int", default=0)
        p2 = Parameter(name="b", annotation="int", default=0)
        assert p1 != p2


class TestCodeElement:
    def _make(self, **kwargs):
        defaults = dict(
            element_id="mod.func",
            kind=ElementKind.FUNCTION,
            file="mod.py",
            name="func",
            qualified_name="mod.func",
            lineno=1,
            end_lineno=5,
            signature_hash="abc",
            body_hash="def",
            source_hash="ghi",
            parameters=[],
            return_annotation=None,
            parent=None,
            bases=[],
            methods=[],
            raw_calls=[],
            docstring_summary=None,
        )
        defaults.update(kwargs)
        return CodeElement(**defaults)

    def test_basic_creation(self):
        el = self._make()
        assert el.element_id == "mod.func"
        assert el.kind == ElementKind.FUNCTION

    def test_has_raw_calls_not_calls(self):
        el = self._make(raw_calls=["mod.helper"])
        assert el.raw_calls == ["mod.helper"]
        assert not hasattr(el, "calls")

    def test_parameters_stored(self):
        p = Parameter(name="x", annotation="int", default=None)
        el = self._make(parameters=[p])
        assert el.parameters == [p]

    def test_return_annotation_none_default(self):
        el = self._make()
        assert el.return_annotation is None

    def test_docstring_summary_none_default(self):
        el = self._make()
        assert el.docstring_summary is None

    @pytest.mark.parametrize("kind", list(ElementKind))
    def test_all_kinds_accepted(self, kind):
        el = self._make(kind=kind)
        assert el.kind == kind


class TestImportInfo:
    def test_basic_creation(self):
        from doc_updater.analyzer.base import ImportInfo

        imp = ImportInfo(
            module="os.path",
            names=["join", "exists"],
            alias=None,
            lineno=1,
        )
        assert imp.module == "os.path"
        assert imp.names == ["join", "exists"]
        assert imp.alias is None
        assert imp.lineno == 1


class TestFileAnalysis:
    def test_basic_creation(self):
        fa = FileAnalysis(
            file="mod.py",
            elements=[],
            imports=[],
            parse_errors=[],
        )
        assert fa.file == "mod.py"
        assert fa.elements == []
        assert fa.imports == []
        assert fa.parse_errors == []

    def test_parse_errors_field_exists(self):
        fa = FileAnalysis(
            file="bad.py",
            elements=[],
            imports=[],
            parse_errors=["SyntaxError at line 3"],
        )
        assert fa.parse_errors == ["SyntaxError at line 3"]


class TestEdgeKind:
    @pytest.mark.parametrize(
        "member",
        ["CALLS", "INHERITS", "IMPORTS", "DOCUMENTS"],
    )
    def test_has_member(self, member):
        assert hasattr(EdgeKind, member)


class TestGraphEdge:
    def test_basic_creation(self):
        edge = GraphEdge(
            source="mod.func",
            target="mod.helper",
            kind=EdgeKind.CALLS,
        )
        assert edge.source == "mod.func"
        assert edge.target == "mod.helper"
        assert edge.kind == EdgeKind.CALLS

    def test_frozen(self):
        edge = GraphEdge(
            source="a",
            target="b",
            kind=EdgeKind.CALLS,
        )
        with pytest.raises((AttributeError, TypeError)):
            edge.source = "c"  # type: ignore[misc]

    def test_hashable_and_usable_in_set(self):
        e1 = GraphEdge(source="a", target="b", kind=EdgeKind.CALLS)
        e2 = GraphEdge(source="a", target="b", kind=EdgeKind.CALLS)
        e3 = GraphEdge(source="a", target="c", kind=EdgeKind.CALLS)
        s = {e1, e2, e3}
        assert len(s) == 2
