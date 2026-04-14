"""Tests for docsight.docs.mapper."""

import pytest

from docsight.analyzer.base import CodeElement, ElementKind
from docsight.docs.mapper import DocMapper, ResolvedMapping
from docsight.docs.scanner import RawReference


def _make_element(
    element_id: str,
    kind: ElementKind,
    file: str,
    name: str,
    qualified_name: str,
) -> CodeElement:
    return CodeElement(
        element_id=element_id,
        kind=kind,
        file=file,
        name=name,
        qualified_name=qualified_name,
        lineno=1,
        end_lineno=10,
        signature_hash="sig",
        body_hash="body",
        source_hash="src",
        parameters=[],
        return_annotation=None,
        parent=None,
        bases=[],
        methods=[],
        raw_calls=[],
        docstring_summary=None,
    )


def _elements() -> dict[str, CodeElement]:
    return {
        "src/auth.py::__module__": _make_element(
            "src/auth.py::__module__",
            ElementKind.MODULE,
            "src/auth.py",
            "__module__",
            "__module__",
        ),
        "src/auth.py::AuthManager": _make_element(
            "src/auth.py::AuthManager",
            ElementKind.CLASS,
            "src/auth.py",
            "AuthManager",
            "AuthManager",
        ),
        "src/auth.py::AuthManager.validate_token": _make_element(
            "src/auth.py::AuthManager.validate_token",
            ElementKind.METHOD,
            "src/auth.py",
            "validate_token",
            "AuthManager.validate_token",
        ),
        "src/auth.py::authenticate": _make_element(
            "src/auth.py::authenticate",
            ElementKind.FUNCTION,
            "src/auth.py",
            "authenticate",
            "authenticate",
        ),
        "src/cache.py::__module__": _make_element(
            "src/cache.py::__module__",
            ElementKind.MODULE,
            "src/cache.py",
            "__module__",
            "__module__",
        ),
        "src/cache.py::cache_lookup": _make_element(
            "src/cache.py::cache_lookup",
            ElementKind.FUNCTION,
            "src/cache.py",
            "cache_lookup",
            "cache_lookup",
        ),
    }


class TestResolvedMapping:
    def test_defaults(self):
        mapping = ResolvedMapping(
            element_id="src/auth.py::AuthManager",
            ref_type="class_name_backtick",
            lineno=3,
            confidence=0.85,
        )
        assert mapping.text == ""
        assert mapping.context == ""
        assert mapping.section == ""


class TestDocMapperResolveClassName:
    def test_resolve_class_name(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="AuthManager",
            ref_type="class_name_backtick",
            lineno=5,
            confidence=0.85,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].element_id == "src/auth.py::AuthManager"

    def test_resolve_function_name(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="cache_lookup",
            ref_type="function_call_backtick",
            lineno=10,
            confidence=0.90,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].element_id == "src/cache.py::cache_lookup"

    def test_resolve_dotted_method(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="AuthManager.validate_token",
            ref_type="method_call_backtick",
            lineno=7,
            confidence=0.90,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].element_id == "src/auth.py::AuthManager.validate_token"


class TestDocMapperFilePath:
    def test_file_path_resolves_to_module_element(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="src/auth.py",
            ref_type="file_path_backtick",
            lineno=3,
            confidence=0.95,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].element_id == "src/auth.py::__module__"

    def test_file_path_not_found_returns_empty(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="src/missing.py",
            ref_type="file_path_backtick",
            lineno=3,
            confidence=0.95,
        )
        results = mapper.resolve(ref)
        assert results == []


class TestDocMapperAmbiguity:
    def test_ambiguous_reduces_confidence(self):
        """Two elements with same simple name -> confidence halved."""
        elements = _elements()
        # Add a second AuthManager in a different file
        elements["src/other.py::AuthManager"] = _make_element(
            "src/other.py::AuthManager",
            ElementKind.CLASS,
            "src/other.py",
            "AuthManager",
            "AuthManager",
        )
        mapper = DocMapper(elements)
        ref = RawReference(
            text="AuthManager",
            ref_type="class_name_backtick",
            lineno=5,
            confidence=0.85,
        )
        results = mapper.resolve(ref)
        assert len(results) == 2
        for r in results:
            assert r.confidence < 0.85

    def test_unresolvable_returns_empty(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="NonExistentClass",
            ref_type="class_name_backtick",
            lineno=5,
            confidence=0.85,
        )
        results = mapper.resolve(ref)
        assert results == []

    def test_ambiguous_confidence_below_threshold_returns_empty(self):
        """When confidence/count < 0.10, return empty list."""
        elements = {}
        # Create 20 elements with the same name to push confidence/count below threshold
        for i in range(20):
            eid = f"src/file{i}.py::SameName"
            elements[eid] = _make_element(
                eid,
                ElementKind.CLASS,
                f"src/file{i}.py",
                "SameName",
                "SameName",
            )
        mapper = DocMapper(elements)
        ref = RawReference(
            text="SameName",
            ref_type="class_name_backtick",
            lineno=5,
            confidence=0.85,
        )
        results = mapper.resolve(ref)
        # 0.85 / 20 = 0.0425 < 0.10 -> return empty
        assert results == []


class TestDocMapperFallbackPaths:
    def test_name_fallback_when_qualified_name_differs(self):
        """Simple name fallback is used when qualified_name lookup misses."""
        # Create an element whose qualified_name has a module prefix,
        # so direct lookup of "SomeClass" fails the qualified_name index.
        elements = {
            "pkg/mod.py::SomeClass": _make_element(
                "pkg/mod.py::SomeClass",
                ElementKind.CLASS,
                "pkg/mod.py",
                "SomeClass",
                "mod.SomeClass",  # qualified_name differs from simple name
            ),
        }
        mapper = DocMapper(elements)
        ref = RawReference(
            text="SomeClass",
            ref_type="class_name_backtick",
            lineno=1,
            confidence=0.85,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].element_id == "pkg/mod.py::SomeClass"

    def test_dotted_fallback_when_qualified_name_has_module_prefix(self):
        """_resolve_dotted finds element when qualified_name has module prefix."""
        # Element's qualified_name is "pkg.MyClass.my_method" (has module prefix),
        # but we're looking up "MyClass.my_method" — qualified_name lookup misses
        # because the key is "pkg.MyClass.my_method", not "MyClass.my_method".
        # The dotted fallback should find it via suffix matching.
        elements = {
            "pkg/mod.py::MyClass.my_method": _make_element(
                "pkg/mod.py::MyClass.my_method",
                ElementKind.METHOD,
                "pkg/mod.py",
                "my_method",
                "pkg.MyClass.my_method",  # qualified_name with module prefix
            ),
        }
        mapper = DocMapper(elements)
        ref = RawReference(
            text="MyClass.my_method",
            ref_type="method_call_backtick",
            lineno=1,
            confidence=0.90,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].element_id == "pkg/mod.py::MyClass.my_method"

    def test_dotted_fallback_returns_empty_when_not_found(self):
        """_resolve_dotted returns empty list when dotted name has no match."""
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="Unknown.method",
            ref_type="method_call_backtick",
            lineno=1,
            confidence=0.90,
        )
        results = mapper.resolve(ref)
        assert results == []


class TestDocMapperPreservesFields:
    def test_preserves_text_and_section(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="AuthManager",
            ref_type="class_name_backtick",
            lineno=5,
            confidence=0.85,
            context="Use the AuthManager for auth.",
            section="Authentication Guide",
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        r = results[0]
        assert r.text == "AuthManager"
        assert r.context == "Use the AuthManager for auth."
        assert r.section == "Authentication Guide"
        assert r.lineno == 5
        assert r.ref_type == "class_name_backtick"

    def test_preserves_confidence(self):
        mapper = DocMapper(_elements())
        ref = RawReference(
            text="authenticate",
            ref_type="function_call_backtick",
            lineno=1,
            confidence=0.90,
        )
        results = mapper.resolve(ref)
        assert len(results) == 1
        assert results[0].confidence == 0.90


class TestDocMapperDuplicateNames:
    def test_duplicate_names_across_files(self):
        """Two AuthManagers in different files -> both returned with reduced confidence."""
        elements = _elements()
        elements["src/other.py::AuthManager"] = _make_element(
            "src/other.py::AuthManager",
            ElementKind.CLASS,
            "src/other.py",
            "AuthManager",
            "AuthManager",
        )
        mapper = DocMapper(elements)
        ref = RawReference(
            text="AuthManager",
            ref_type="class_name_backtick",
            lineno=5,
            confidence=0.85,
        )
        results = mapper.resolve(ref)
        assert len(results) == 2
        element_ids = {r.element_id for r in results}
        assert "src/auth.py::AuthManager" in element_ids
        assert "src/other.py::AuthManager" in element_ids
        # Confidence should be reduced
        for r in results:
            assert r.confidence == pytest.approx(0.85 / 2)
