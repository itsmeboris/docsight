"""Python AST-based code analyzer."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Optional

from doc_updater.analyzer.base import (
    CodeAnalyzer,
    CodeElement,
    EdgeKind,
    ElementKind,
    FileAnalysis,
    GraphEdge,
    ImportInfo,
    Parameter,
)


def _hash(text: str) -> str:
    """Return a short SHA-256 hex digest of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _is_docstring(stmt: ast.stmt) -> bool:
    """Return True if *stmt* is a bare string literal (docstring)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _body_hash(body: list[ast.stmt]) -> str:
    """Hash only the non-docstring body statements."""
    parts = [ast.dump(s) for s in body if not _is_docstring(s)]
    return _hash("|".join(parts))


def _annotation_str(node: Optional[ast.expr]) -> Optional[str]:
    """Convert an annotation AST node to a string representation."""
    if node is None:
        return None
    return ast.unparse(node)


def _default_str(node: ast.expr) -> str:
    """Convert a default value AST node to a string representation."""
    return ast.unparse(node)


def _extract_params(
    args: ast.arguments,
) -> list[Parameter]:
    """Extract Parameter objects from a function's argument spec."""
    params: list[Parameter] = []

    # Build (arg, default) pairs — defaults are right-aligned
    all_args = args.posonlyargs + args.args
    n_defaults = len(args.defaults)
    n_args = len(all_args)

    for i, arg in enumerate(all_args):
        default_index = i - (n_args - n_defaults)
        default = _default_str(args.defaults[default_index]) if default_index >= 0 else None
        kind = "POSITIONAL_ONLY" if arg in args.posonlyargs else "POSITIONAL_OR_KEYWORD"
        params.append(
            Parameter(
                name=arg.arg,
                annotation=_annotation_str(arg.annotation),
                default=default,
                kind=kind,
            )
        )

    # *args
    if args.vararg:
        params.append(
            Parameter(
                name=args.vararg.arg,
                annotation=_annotation_str(args.vararg.annotation),
                default=None,
                kind="VAR_POSITIONAL",
            )
        )

    # keyword-only args
    for i, arg in enumerate(args.kwonlyargs):
        kw_default = args.kw_defaults[i]
        params.append(
            Parameter(
                name=arg.arg,
                annotation=_annotation_str(arg.annotation),
                default=_default_str(kw_default) if kw_default is not None else None,
                kind="KEYWORD_ONLY",
            )
        )

    # **kwargs
    if args.kwarg:
        params.append(
            Parameter(
                name=args.kwarg.arg,
                annotation=_annotation_str(args.kwarg.annotation),
                default=None,
                kind="VAR_KEYWORD",
            )
        )

    return params


def _signature_hash(name: str, params: list[Parameter], return_ann: Optional[str]) -> str:
    """Compute signature hash from name, params (excl. self), and return annotation."""
    param_parts = [
        f"{p.name}:{p.annotation}:{p.default}:{p.kind}"
        for p in params
        if p.name != "self"
    ]
    param_canon = "|".join(param_parts)
    return _hash(f"{name}|{param_canon}|{return_ann}")


def _docstring_summary(node: ast.AST) -> Optional[str]:
    """Extract the first line of a docstring from an AST node."""
    doc = ast.get_docstring(node)
    if doc:
        return doc.splitlines()[0]
    return None


class _CallExtractor(ast.NodeVisitor):
    """Walk a function/method body and collect call references.

    Tracks simple local variable bindings of the form ``var = ClassName()``,
    then when ``var.method()`` is seen it records ``ClassName.method`` instead
    of the generic ``var.method``.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []
        # Maps local var name -> class name (from `var = ClassName()`)
        self._bindings: dict[str, str] = {}

    def visit_Assign(self, node: ast.Assign) -> None:  # pylint: disable=invalid-name
        """Record ``var = ClassName()`` bindings."""
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            var_name = node.targets[0].id
            class_name = node.value.func.id
            self._bindings[var_name] = class_name
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # pylint: disable=invalid-name
        """Record calls, resolving local bindings where possible."""
        if isinstance(node.func, ast.Name):
            self.calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            obj = node.func.value
            attr = node.func.attr
            if isinstance(obj, ast.Name):
                bound_class = self._bindings.get(obj.id)
                if bound_class:
                    self.calls.append(f"{bound_class}.{attr}")
                else:
                    self.calls.append(f"{obj.id}.{attr}")
        self.generic_visit(node)


class PythonAnalyzer(CodeAnalyzer):
    """Analyze Python source files using the stdlib ``ast`` module."""

    def supported_extensions(self) -> list[str]:
        return [".py"]

    def analyze_file(self, path: Path, repo_root: Path | None = None) -> FileAnalysis:
        """Parse *path* and return its FileAnalysis."""
        if repo_root is not None:
            try:
                rel_path = str(path.relative_to(repo_root))
            except ValueError:
                rel_path = str(path)
        else:
            rel_path = str(path)
        source = path.read_text(encoding="utf-8")

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            return FileAnalysis(
                file=rel_path,
                elements=[],
                imports=[],
                parse_errors=[str(exc)],
            )

        elements: list[CodeElement] = []
        imports: list[ImportInfo] = []

        # --- collect imports ---
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportInfo(
                            module=alias.name,
                            names=[alias.asname or alias.name],
                            alias=alias.asname,
                            lineno=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                imports.append(
                    ImportInfo(
                        module=module,
                        names=names,
                        alias=None,
                        lineno=node.lineno,
                    )
                )

        # --- collect top-level class and function definitions ---
        top_level_names: list[str] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                top_level_names.append(node.name)
                el = self._extract_function(node, rel_path, parent=None, kind=ElementKind.FUNCTION)
                elements.append(el)
            elif isinstance(node, ast.ClassDef):
                top_level_names.append(node.name)
                cls_el, method_els = self._extract_class(node, rel_path)
                elements.append(cls_el)
                elements.extend(method_els)

        # --- MODULE element ---
        module_id = f"{rel_path}::__module__"
        mod_sig_hash = _hash("|".join(sorted(top_level_names)))
        mod_body_hash = _hash(ast.dump(tree))
        module_el = CodeElement(
            element_id=module_id,
            kind=ElementKind.MODULE,
            file=rel_path,
            name="__module__",
            qualified_name=module_id,
            lineno=1,
            end_lineno=len(source.splitlines()) or 1,
            signature_hash=mod_sig_hash,
            body_hash=mod_body_hash,
            source_hash=_hash(source),
            parameters=[],
            return_annotation=None,
            parent=None,
            bases=[],
            methods=[],
            raw_calls=[],
            docstring_summary=_docstring_summary(tree),
        )
        elements.append(module_el)

        return FileAnalysis(
            file=rel_path,
            elements=elements,
            imports=imports,
            parse_errors=[],
        )

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file: str,
        parent: Optional[str],
        kind: ElementKind,
    ) -> CodeElement:
        params = _extract_params(node.args)
        # Exclude 'self' from method parameters list
        if kind == ElementKind.METHOD:
            params = [p for p in params if p.name != "self"]
        return_ann = _annotation_str(node.returns)
        sig_hash = _signature_hash(node.name, params, return_ann)
        b_hash = _body_hash(node.body)
        source_text = ast.unparse(node)

        extractor = _CallExtractor()
        for stmt in node.body:
            extractor.visit(stmt)

        # Build element_id
        if parent:
            element_id = f"{file}::{parent.split('::')[-1]}.{node.name}"
        else:
            element_id = f"{file}::{node.name}"

        return CodeElement(
            element_id=element_id,
            kind=kind,
            file=file,
            name=node.name,
            qualified_name=element_id,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            signature_hash=sig_hash,
            body_hash=b_hash,
            source_hash=_hash(source_text),
            parameters=params,
            return_annotation=return_ann,
            parent=parent,
            bases=[],
            methods=[],
            raw_calls=extractor.calls,
            docstring_summary=_docstring_summary(node),
        )

    def _extract_class(
        self,
        node: ast.ClassDef,
        file: str,
    ) -> tuple[CodeElement, list[CodeElement]]:
        element_id = f"{file}::{node.name}"
        bases = [ast.unparse(b) for b in node.bases]

        method_elements: list[CodeElement] = []
        method_names: list[str] = []

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_names.append(child.name)
                m_el = self._extract_function(
                    child, file, parent=element_id, kind=ElementKind.METHOD
                )
                method_elements.append(m_el)

        # Class signature: name + bases + method names
        sig_text = f"{node.name}|{'|'.join(bases)}|{'|'.join(method_names)}"
        sig_hash = _hash(sig_text)
        b_hash = _body_hash(node.body)

        cls_el = CodeElement(
            element_id=element_id,
            kind=ElementKind.CLASS,
            file=file,
            name=node.name,
            qualified_name=element_id,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            signature_hash=sig_hash,
            body_hash=b_hash,
            source_hash=_hash(ast.unparse(node)),
            parameters=[],
            return_annotation=None,
            parent=None,
            bases=bases,
            methods=method_names,
            raw_calls=[],
            docstring_summary=_docstring_summary(node),
        )
        return cls_el, method_elements

    def resolve_calls(
        self,
        elements: dict[str, CodeElement],
        analyses: dict[str, FileAnalysis],
    ) -> list[GraphEdge]:
        """Resolve raw_calls to GraphEdge objects.

        Generates CALLS edges from raw call strings and INHERITS edges from
        class base declarations.
        """
        edges: list[GraphEdge] = []

        # Build name lookup maps:
        # simple_name -> list of element_ids (may be ambiguous)
        name_to_ids: dict[str, list[str]] = {}
        # "ClassName.method_name" -> element_id
        qualified_to_id: dict[str, str] = {}

        for eid, el in elements.items():
            # Index by simple name
            name_to_ids.setdefault(el.name, []).append(eid)
            # Index by qualified name components
            # For methods: file::ClassName.method_name
            parts = eid.split("::")
            if len(parts) == 2 and "." in parts[1]:
                qualified_to_id[parts[1]] = eid

        # --- CALLS edges ---
        for eid, el in elements.items():
            for raw_call in el.raw_calls:
                target_id: Optional[str] = None
                if "." in raw_call:
                    # Try qualified lookup first
                    target_id = qualified_to_id.get(raw_call)
                    if target_id is None:
                        # Try finding by method name alone across all elements
                        method_name = raw_call.split(".")[-1]
                        candidates = name_to_ids.get(method_name, [])
                        if len(candidates) == 1:
                            target_id = candidates[0]
                else:
                    candidates = name_to_ids.get(raw_call, [])
                    if len(candidates) == 1:
                        target_id = candidates[0]
                    elif len(candidates) > 1:
                        # Prefer same-file element
                        same_file = [c for c in candidates if c.startswith(el.file + "::")]
                        if len(same_file) == 1:
                            target_id = same_file[0]

                if target_id and target_id != eid:
                    edges.append(GraphEdge(source=eid, target=target_id, kind=EdgeKind.CALLS))

        # --- INHERITS edges ---
        for eid, el in elements.items():
            if el.kind == ElementKind.CLASS:
                for base_name in el.bases:
                    candidates = name_to_ids.get(base_name, [])
                    if len(candidates) == 1:
                        edges.append(
                            GraphEdge(source=eid, target=candidates[0], kind=EdgeKind.INHERITS)
                        )
                    elif len(candidates) > 1:
                        same_file = [c for c in candidates if c.startswith(el.file + "::")]
                        if same_file:
                            edges.append(
                                GraphEdge(
                                    source=eid,
                                    target=same_file[0],
                                    kind=EdgeKind.INHERITS,
                                )
                            )

        # Deduplicate edges
        return list(dict.fromkeys(edges))
