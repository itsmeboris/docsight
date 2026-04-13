"""Tests for the Python AST analyzer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from doc_updater.analyzer.base import ElementKind
from doc_updater.analyzer.python_analyzer import PythonAnalyzer


@pytest.fixture
def analyzer():
    return PythonAnalyzer()


@pytest.fixture
def write_py(tmp_path):
    """Helper: write Python source to a temp file and return the Path."""

    def _write(name: str, source: str) -> Path:
        p = tmp_path / name
        p.write_text(textwrap.dedent(source), encoding="utf-8")
        return p

    return _write


# ---------------------------------------------------------------------------
# supported_extensions
# ---------------------------------------------------------------------------


class TestSupportedExtensions:
    def test_py_in_extensions(self, analyzer):
        assert ".py" in analyzer.supported_extensions()


# ---------------------------------------------------------------------------
# Function extraction
# ---------------------------------------------------------------------------


class TestExtractsFunction:
    def test_name_kind_params_return_docstring(self, analyzer, write_py):
        path = write_py(
            "simple.py",
            """\
            def greet(name: str, count: int = 1) -> str:
                \"\"\"Say hello.\"\"\"
                return f"hello {name}" * count
            """,
        )
        fa = analyzer.analyze_file(path)
        assert not fa.parse_errors
        fn = next(e for e in fa.elements if e.name == "greet")
        assert fn.kind == ElementKind.FUNCTION
        assert fn.return_annotation == "str"
        assert fn.docstring_summary == "Say hello."
        param_names = [p.name for p in fn.parameters]
        assert param_names == ["name", "count"]
        count_p = next(p for p in fn.parameters if p.name == "count")
        assert count_p.annotation == "int"
        assert count_p.default == "1"


# ---------------------------------------------------------------------------
# Class + method extraction
# ---------------------------------------------------------------------------


class TestExtractsClassWithMethods:
    def test_class_kind_and_methods_list(self, analyzer, write_py):
        path = write_py(
            "cls.py",
            """\
            class Foo:
                \"\"\"A foo.\"\"\"

                def bar(self) -> None:
                    pass

                def baz(self, x: int) -> int:
                    return x
            """,
        )
        fa = analyzer.analyze_file(path)
        cls_el = next(e for e in fa.elements if e.name == "Foo")
        assert cls_el.kind == ElementKind.CLASS
        assert set(cls_el.methods) == {"bar", "baz"}

        bar = next(e for e in fa.elements if e.name == "bar")
        assert bar.kind == ElementKind.METHOD
        assert bar.parent == cls_el.element_id

        baz = next(e for e in fa.elements if e.name == "baz")
        assert baz.kind == ElementKind.METHOD
        baz_params = [p.name for p in baz.parameters]
        # 'self' excluded from parameters list
        assert baz_params == ["x"]


# ---------------------------------------------------------------------------
# body_hash stability / signature_hash sensitivity
# ---------------------------------------------------------------------------


class TestBodyHashStableOnSignatureChange:
    def test_adding_param_does_not_change_body_hash(self, analyzer, write_py):
        path_a = write_py(
            "fn_a.py",
            """\
            def compute(x: int) -> int:
                result = x * 2
                return result
            """,
        )
        path_b = write_py(
            "fn_b.py",
            """\
            def compute(x: int, extra: str = "hi") -> int:
                result = x * 2
                return result
            """,
        )
        fa_a = analyzer.analyze_file(path_a)
        fa_b = analyzer.analyze_file(path_b)
        fn_a = next(e for e in fa_a.elements if e.name == "compute")
        fn_b = next(e for e in fa_b.elements if e.name == "compute")
        assert fn_a.body_hash == fn_b.body_hash


class TestSignatureHashIncludesDefaults:
    def test_changing_default_changes_signature_hash(self, analyzer, write_py):
        path_a = write_py(
            "sig_a.py",
            """\
            def run(strict: bool = True) -> None:
                pass
            """,
        )
        path_b = write_py(
            "sig_b.py",
            """\
            def run(strict: bool = False) -> None:
                pass
            """,
        )
        fa_a = analyzer.analyze_file(path_a)
        fa_b = analyzer.analyze_file(path_b)
        fn_a = next(e for e in fa_a.elements if e.name == "run")
        fn_b = next(e for e in fa_b.elements if e.name == "run")
        assert fn_a.signature_hash != fn_b.signature_hash


# ---------------------------------------------------------------------------
# raw_calls extraction
# ---------------------------------------------------------------------------


class TestExtractsRawCalls:
    def test_simple_calls_in_raw_calls(self, analyzer, write_py):
        path = write_py(
            "calls.py",
            """\
            def foo():
                bar()
                obj.method()
            """,
        )
        fa = analyzer.analyze_file(path)
        fn = next(e for e in fa.elements if e.name == "foo")
        assert "bar" in fn.raw_calls
        assert "obj.method" in fn.raw_calls


class TestTracksLocalBindings:
    def test_instance_method_call_resolves_to_class_method(self, analyzer, write_py):
        path = write_py(
            "bind.py",
            """\
            def authenticate():
                mgr = AuthManager()
                mgr.validate_token("x")
            """,
        )
        fa = analyzer.analyze_file(path)
        fn = next(e for e in fa.elements if e.name == "authenticate")
        assert "AuthManager.validate_token" in fn.raw_calls


# ---------------------------------------------------------------------------
# Syntax error handling
# ---------------------------------------------------------------------------


class TestSyntaxErrorReported:
    def test_parse_errors_populated_elements_empty(self, analyzer, write_py):
        path = write_py(
            "broken.py",
            """\
            def oops(
                this is not valid python
            """,
        )
        fa = analyzer.analyze_file(path)
        assert len(fa.parse_errors) > 0
        assert fa.elements == []


# ---------------------------------------------------------------------------
# Import extraction
# ---------------------------------------------------------------------------


class TestExtractsImports:
    @pytest.mark.parametrize(
        "source,expected_module,expected_names",
        [
            (
                "from os.path import join, exists\n",
                "os.path",
                ["join", "exists"],
            ),
            (
                "import sys\n",
                "sys",
                ["sys"],
            ),
        ],
    )
    def test_import_recorded(
        self, analyzer, write_py, source, expected_module, expected_names
    ):
        path = write_py("imp.py", source)
        fa = analyzer.analyze_file(path)
        imp = next(i for i in fa.imports if i.module == expected_module)
        for name in expected_names:
            assert name in imp.names


# ---------------------------------------------------------------------------
# MODULE element
# ---------------------------------------------------------------------------


class TestCreatesModuleElement:
    def test_module_element_exists_with_correct_hashes(self, analyzer, write_py):
        path = write_py(
            "mod.py",
            """\
            def alpha():
                pass

            def beta():
                pass
            """,
        )
        fa = analyzer.analyze_file(path)
        mod = next(e for e in fa.elements if e.kind == ElementKind.MODULE)
        assert mod.element_id.endswith("::__module__")
        # body_hash changes when code changes
        assert mod.body_hash

    def test_module_element_id_uses_rel_path(self, analyzer, tmp_path):
        """element_id for MODULE is rel_path::__module__ relative to the file name."""
        path = tmp_path / "mymod.py"
        path.write_text("x = 1\n", encoding="utf-8")
        fa = analyzer.analyze_file(path)
        mod = next(e for e in fa.elements if e.kind == ElementKind.MODULE)
        # element_id should contain the filename
        assert "mymod.py" in mod.element_id

    def test_module_signature_hash_includes_top_level_names(self, analyzer, write_py):
        """Adding a top-level name changes signature_hash."""
        path_a = write_py("ma.py", "def foo(): pass\n")
        path_b = write_py("mb.py", "def foo(): pass\ndef bar(): pass\n")
        fa_a = analyzer.analyze_file(path_a)
        fa_b = analyzer.analyze_file(path_b)
        mod_a = next(e for e in fa_a.elements if e.kind == ElementKind.MODULE)
        mod_b = next(e for e in fa_b.elements if e.kind == ElementKind.MODULE)
        assert mod_a.signature_hash != mod_b.signature_hash

    def test_module_body_hash_stable_on_comment_change(self, analyzer, tmp_path):
        """Comments (which don't appear in AST body_hash) don't change body_hash."""
        path_a = tmp_path / "ca.py"
        path_b = tmp_path / "cb.py"
        path_a.write_text("def foo():\n    return 1\n", encoding="utf-8")
        path_b.write_text("# a comment\ndef foo():\n    return 1\n", encoding="utf-8")
        fa_a = analyzer.analyze_file(path_a)
        fa_b = analyzer.analyze_file(path_b)
        mod_a = next(e for e in fa_a.elements if e.kind == ElementKind.MODULE)
        mod_b = next(e for e in fa_b.elements if e.kind == ElementKind.MODULE)
        assert mod_a.body_hash == mod_b.body_hash


# ---------------------------------------------------------------------------
# resolve_calls
# ---------------------------------------------------------------------------


class TestResolveCalls:
    def test_resolve_calls_generates_edges(self, analyzer, write_py):
        """resolve_calls returns GraphEdge objects for known element ids."""
        path = write_py(
            "rc.py",
            """\
            def caller():
                callee()

            def callee():
                pass
            """,
        )
        fa = analyzer.analyze_file(path)
        elements = {e.element_id: e for e in fa.elements}
        analyses = {str(path): fa}
        edges = analyzer.resolve_calls(elements, analyses)
        # Find caller element
        caller_el = next(e for e in fa.elements if e.name == "caller")
        callee_el = next(e for e in fa.elements if e.name == "callee")
        edge_pairs = {(e.source, e.target) for e in edges}
        assert (caller_el.element_id, callee_el.element_id) in edge_pairs

    def test_resolve_calls_inheritance_edges(self, analyzer, write_py):
        """resolve_calls emits INHERITS edges for class bases."""
        path = write_py(
            "inh.py",
            """\
            class Base:
                pass

            class Child(Base):
                pass
            """,
        )
        fa = analyzer.analyze_file(path)
        elements = {e.element_id: e for e in fa.elements}
        analyses = {str(path): fa}
        edges = analyzer.resolve_calls(elements, analyses)
        from doc_updater.analyzer.base import EdgeKind

        inh_edges = [e for e in edges if e.kind == EdgeKind.INHERITS]
        child_el = next(e for e in fa.elements if e.name == "Child")
        base_el = next(e for e in fa.elements if e.name == "Base")
        inh_targets = {(e.source, e.target) for e in inh_edges}
        assert (child_el.element_id, base_el.element_id) in inh_targets

    def test_ambiguous_same_file_call_resolved(self, analyzer, tmp_path):
        """When two files define the same function, same-file is preferred."""
        file_a = tmp_path / "a.py"
        file_b = tmp_path / "b.py"
        file_a.write_text("def helper(): pass\ndef caller():\n    helper()\n", encoding="utf-8")
        file_b.write_text("def helper(): pass\n", encoding="utf-8")
        fa_a = analyzer.analyze_file(file_a)
        fa_b = analyzer.analyze_file(file_b)
        elements = {}
        for fa in [fa_a, fa_b]:
            for el in fa.elements:
                elements[el.element_id] = el
        analyses = {str(file_a): fa_a, str(file_b): fa_b}
        edges = analyzer.resolve_calls(elements, analyses)
        caller_el = next(e for e in fa_a.elements if e.name == "caller")
        helper_a = next(e for e in fa_a.elements if e.name == "helper")
        edge_pairs = {(e.source, e.target) for e in edges}
        assert (caller_el.element_id, helper_a.element_id) in edge_pairs

    def test_ambiguous_inheritance_same_file(self, analyzer, tmp_path):
        """When two files define the same base class, same-file is preferred."""
        file_a = tmp_path / "ia.py"
        file_b = tmp_path / "ib.py"
        file_a.write_text("class Base: pass\nclass Child(Base): pass\n", encoding="utf-8")
        file_b.write_text("class Base: pass\n", encoding="utf-8")
        fa_a = analyzer.analyze_file(file_a)
        fa_b = analyzer.analyze_file(file_b)
        elements = {}
        for fa in [fa_a, fa_b]:
            for el in fa.elements:
                elements[el.element_id] = el
        analyses = {str(file_a): fa_a, str(file_b): fa_b}
        edges = analyzer.resolve_calls(elements, analyses)
        from doc_updater.analyzer.base import EdgeKind
        inh_edges = [e for e in edges if e.kind == EdgeKind.INHERITS]
        child_el = next(e for e in fa_a.elements if e.name == "Child")
        base_a = next(e for e in fa_a.elements if e.name == "Base")
        inh_pairs = {(e.source, e.target) for e in inh_edges}
        assert (child_el.element_id, base_a.element_id) in inh_pairs


# ---------------------------------------------------------------------------
# Advanced parameter extraction
# ---------------------------------------------------------------------------


class TestAdvancedParameters:
    def test_varargs_extracted(self, analyzer, write_py):
        path = write_py(
            "var.py",
            """\
            def fn(*args: int, **kwargs: str) -> None:
                pass
            """,
        )
        fa = analyzer.analyze_file(path)
        fn = next(e for e in fa.elements if e.name == "fn")
        kinds = {p.kind for p in fn.parameters}
        assert "VAR_POSITIONAL" in kinds
        assert "VAR_KEYWORD" in kinds

    def test_keyword_only_params(self, analyzer, write_py):
        path = write_py(
            "kw.py",
            """\
            def fn(*, strict: bool = True) -> None:
                pass
            """,
        )
        fa = analyzer.analyze_file(path)
        fn = next(e for e in fa.elements if e.name == "fn")
        kw_params = [p for p in fn.parameters if p.kind == "KEYWORD_ONLY"]
        assert len(kw_params) == 1
        assert kw_params[0].name == "strict"
        assert kw_params[0].default == "True"

    def test_no_default_is_none(self, analyzer, write_py):
        """Parameters with no default have default=None."""
        path = write_py(
            "nodef.py",
            """\
            def fn(x: int) -> None:
                pass
            """,
        )
        fa = analyzer.analyze_file(path)
        fn = next(e for e in fa.elements if e.name == "fn")
        x_param = next(p for p in fn.parameters if p.name == "x")
        assert x_param.default is None


# ---------------------------------------------------------------------------
# resolve_calls: qualified method lookup via element_id index
# ---------------------------------------------------------------------------


class TestResolveCallsQualifiedMethod:
    def test_method_call_resolved_via_qualified_id(self, analyzer, write_py):
        """When mgr = AuthManager(); mgr.do(), raw_call is 'AuthManager.do'.
        resolve_calls should find the method element by qualified lookup."""
        path = write_py(
            "qm.py",
            """\
            class Worker:
                def run(self) -> None:
                    pass

            def start():
                w = Worker()
                w.run()
            """,
        )
        fa = analyzer.analyze_file(path)
        elements = {e.element_id: e for e in fa.elements}
        analyses = {str(path): fa}
        edges = analyzer.resolve_calls(elements, analyses)
        start_el = next(e for e in fa.elements if e.name == "start")
        run_el = next(e for e in fa.elements if e.name == "run")
        edge_pairs = {(e.source, e.target) for e in edges}
        assert (start_el.element_id, run_el.element_id) in edge_pairs

    def test_dotted_call_fallback_to_method_name_lookup(self, analyzer, write_py):
        """When obj.method() is called without a known binding, fall back to
        searching by method name alone when there is exactly one match."""
        path = write_py(
            "fb.py",
            """\
            class Helper:
                def process(self) -> None:
                    pass

            def run(h):
                h.process()
            """,
        )
        fa = analyzer.analyze_file(path)
        elements = {e.element_id: e for e in fa.elements}
        analyses = {str(path): fa}
        edges = analyzer.resolve_calls(elements, analyses)
        run_el = next(e for e in fa.elements if e.name == "run")
        process_el = next(e for e in fa.elements if e.name == "process")
        edge_pairs = {(e.source, e.target) for e in edges}
        assert (run_el.element_id, process_el.element_id) in edge_pairs
