"""Tests for docsight.store.json_store."""

import pytest
from docsight.analyzer.base import (
    CodeElement,
    EdgeKind,
    ElementKind,
    FileAnalysis,
    GraphEdge,
    ImportInfo,
    Parameter,
)
from docsight.store.json_store import JsonStore


def make_element(**kwargs):
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


class TestJsonStoreIndex:
    def test_roundtrip_empty_index(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        store.save_index({})
        loaded = store.load_index()
        assert loaded == {}

    def test_roundtrip_single_element(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        el = make_element()
        store.save_index({"mod.func": el})
        loaded = store.load_index()
        assert "mod.func" in loaded
        restored = loaded["mod.func"]
        assert restored.element_id == el.element_id
        assert restored.kind == el.kind
        assert restored.file == el.file
        assert restored.name == el.name
        assert restored.qualified_name == el.qualified_name
        assert restored.lineno == el.lineno
        assert restored.end_lineno == el.end_lineno

    def test_roundtrip_with_parameters(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        p = Parameter(name="x", annotation="int", default=None, kind="POSITIONAL_OR_KEYWORD")
        el = make_element(parameters=[p], return_annotation="bool")
        store.save_index({"mod.func": el})
        loaded = store.load_index()
        restored = loaded["mod.func"]
        assert len(restored.parameters) == 1
        assert restored.parameters[0].name == "x"
        assert restored.parameters[0].annotation == "int"
        assert restored.parameters[0].kind == "POSITIONAL_OR_KEYWORD"
        assert restored.return_annotation == "bool"

    def test_roundtrip_with_raw_calls(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        el = make_element(raw_calls=["mod.helper", "mod.util"])
        store.save_index({"mod.func": el})
        loaded = store.load_index()
        assert loaded["mod.func"].raw_calls == ["mod.helper", "mod.util"]

    def test_roundtrip_all_element_kinds(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        index = {
            kind.value: make_element(
                element_id=kind.value,
                kind=kind,
                name=kind.value,
                qualified_name=kind.value,
            )
            for kind in ElementKind
        }
        store.save_index(index)
        loaded = store.load_index()
        for kind in ElementKind:
            assert loaded[kind.value].kind == kind

    def test_missing_index_returns_empty(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        loaded = store.load_index()
        assert loaded == {}

    def test_creates_directory_on_save(self, tmp_path):
        store_dir = tmp_path / "nested" / ".docsight"
        assert not store_dir.exists()
        store = JsonStore(store_dir)
        store.save_index({})
        assert store_dir.exists()


class TestJsonStoreMappings:
    def _make_mappings(self):
        return {
            "docs/auth-guide.md": [
                {
                    "element_id": "mod.AuthManager",
                    "text": "AuthManager",
                    "section": "Overview",
                    "context": "This guide covers the AuthManager class.",
                },
                {
                    "element_id": "mod.validate_token",
                    "text": "validate_token()",
                    "section": "Usage",
                    "context": "Call validate_token() to check a token.",
                },
            ],
            "docs/cache-guide.md": [
                {
                    "element_id": "cache.cache_lookup",
                    "text": "cache_lookup()",
                    "section": None,
                    "context": "Use cache_lookup() to retrieve cached values.",
                }
            ],
        }

    def test_roundtrip_mappings(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        mappings = self._make_mappings()
        store.save_mappings(mappings)
        loaded = store.load_mappings()
        assert loaded == mappings

    def test_mappings_have_text_section_context(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        mappings = self._make_mappings()
        store.save_mappings(mappings)
        loaded = store.load_mappings()
        first_ref = loaded["docs/auth-guide.md"][0]
        assert "text" in first_ref
        assert "section" in first_ref
        assert "context" in first_ref
        assert "element_id" in first_ref

    def test_missing_mappings_returns_empty(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        loaded = store.load_mappings()
        assert loaded == {}

    def test_section_can_be_none(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        mappings = {
            "docs/guide.md": [
                {"element_id": "mod.func", "text": "func()", "section": None, "context": ""}
            ]
        }
        store.save_mappings(mappings)
        loaded = store.load_mappings()
        assert loaded["docs/guide.md"][0]["section"] is None


class TestJsonStoreState:
    def _make_state(self):
        return {
            "docs/auth-guide.md": {
                "doc_hash": "abc123",
                "element_hashes": {
                    "mod.AuthManager": "hash1",
                    "mod.validate_token": "hash2",
                },
                "dependency_hashes": {
                    "mod.cache_lookup": "dephash1",
                },
                "last_checked": "2026-01-01T00:00:00",
            },
            "docs/cache-guide.md": {
                "doc_hash": "def456",
                "element_hashes": {
                    "cache.cache_lookup": "hash3",
                },
                "dependency_hashes": {},
                "last_checked": "2026-01-02T00:00:00",
            },
        }

    def test_roundtrip_state(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        state = self._make_state()
        store.save_state(state)
        loaded = store.load_state()
        assert loaded == state

    def test_state_has_dependency_hashes(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        state = self._make_state()
        store.save_state(state)
        loaded = store.load_state()
        assert "dependency_hashes" in loaded["docs/auth-guide.md"]
        assert loaded["docs/auth-guide.md"]["dependency_hashes"] == {
            "mod.cache_lookup": "dephash1"
        }

    def test_missing_state_returns_empty(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        loaded = store.load_state()
        assert loaded == {}

    def test_empty_dependency_hashes_roundtrip(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        state = {
            "docs/guide.md": {
                "doc_hash": "abc",
                "element_hashes": {},
                "dependency_hashes": {},
                "last_checked": "2026-01-01T00:00:00",
            }
        }
        store.save_state(state)
        loaded = store.load_state()
        assert loaded["docs/guide.md"]["dependency_hashes"] == {}


class TestJsonStoreFileAnalysis:
    def test_roundtrip_file_analyses(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        imp = ImportInfo(module="os.path", names=["join"], alias=None, lineno=1)
        el = make_element()
        fa = FileAnalysis(
            file="mod.py",
            elements=[el],
            imports=[imp],
            parse_errors=[],
        )
        store.save_file_analyses({"mod.py": fa})
        loaded = store.load_file_analyses()
        assert "mod.py" in loaded
        restored_fa = loaded["mod.py"]
        assert restored_fa.file == "mod.py"
        assert len(restored_fa.elements) == 1
        assert restored_fa.elements[0].element_id == "mod.func"
        assert len(restored_fa.imports) == 1
        assert restored_fa.imports[0].module == "os.path"
        assert restored_fa.parse_errors == []

    def test_roundtrip_with_parse_errors(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        fa = FileAnalysis(
            file="bad.py",
            elements=[],
            imports=[],
            parse_errors=["SyntaxError at line 3"],
        )
        store.save_file_analyses({"bad.py": fa})
        loaded = store.load_file_analyses()
        assert loaded["bad.py"].parse_errors == ["SyntaxError at line 3"]

    def test_missing_file_analyses_returns_empty(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        loaded = store.load_file_analyses()
        assert loaded == {}


class TestJsonStoreGraphEdges:
    def test_roundtrip_edges(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        edges = [
            GraphEdge(source="a.func", target="b.helper", kind=EdgeKind.CALLS),
            GraphEdge(source="c.Child", target="d.Parent", kind=EdgeKind.INHERITS),
        ]
        store.save_edges(edges)
        loaded = store.load_edges()
        assert len(loaded) == 2
        assert loaded[0].source == "a.func"
        assert loaded[0].kind == EdgeKind.CALLS
        assert loaded[1].kind == EdgeKind.INHERITS

    def test_missing_edges_returns_empty(self, tmp_path):
        store = JsonStore(tmp_path / ".docsight")
        loaded = store.load_edges()
        assert loaded == []

    @pytest.mark.parametrize("kind", list(EdgeKind))
    def test_all_edge_kinds_roundtrip(self, tmp_path, kind):
        store = JsonStore(tmp_path / ".docsight")
        edges = [GraphEdge(source="a", target="b", kind=kind)]
        store.save_edges(edges)
        loaded = store.load_edges()
        assert loaded[0].kind == kind
