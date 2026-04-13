"""Command-line interface for doc-updater."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from doc_updater.analyzer.graph import CodeGraph
from doc_updater.analyzer.python_analyzer import PythonAnalyzer
from doc_updater.store.json_store import JsonStore


@click.group()
@click.option(
    "--repo",
    default=None,
    metavar="PATH",
    help="Path to the repository root (default: current directory).",
)
@click.pass_context
def cli(ctx: click.Context, repo: str | None) -> None:
    """doc-updater: detect stale documentation."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = Path(repo) if repo is not None else Path(os.getcwd())


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialise doc-updater in the repository."""
    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"

    # Create the store directory (idempotent).
    store_dir.mkdir(parents=True, exist_ok=True)

    # Add entry to .gitignore (idempotent — only add if not already present).
    gitignore = repo / ".gitignore"
    entry = ".doc-updater/"

    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        if entry not in existing:
            # Ensure we start on a fresh line.
            if existing and not existing.endswith("\n"):
                existing += "\n"
            gitignore.write_text(existing + entry + "\n", encoding="utf-8")
    else:
        gitignore.write_text(entry + "\n", encoding="utf-8")

    click.echo(f"Initialized doc-updater in {store_dir}")


@cli.command()
@click.option(
    "--skip-errors",
    is_flag=True,
    default=False,
    help="Continue indexing even if parse errors are encountered.",
)
@click.pass_context
def index(ctx: click.Context, skip_errors: bool) -> None:
    """Walk the repository, analyse Python files, and build the index."""
    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)

    analyzer = PythonAnalyzer()
    py_files = sorted(repo.rglob("*.py"))

    # Exclude files inside the store directory itself
    py_files = [
        p for p in py_files if store_dir not in p.parents and p != store_dir
    ]

    analyses = {}
    all_errors: list[str] = []

    for py_file in py_files:
        fa = analyzer.analyze_file(py_file)
        analyses[str(py_file)] = fa
        if fa.parse_errors:
            all_errors.extend(fa.parse_errors)
            if not skip_errors:
                for err in fa.parse_errors:
                    click.echo(f"Parse error in {py_file}: {err}", err=True)

    if all_errors and not skip_errors:
        sys.exit(1)

    # Build element index
    all_elements = {}
    for fa in analyses.values():
        for el in fa.elements:
            all_elements[el.element_id] = el

    # Resolve calls and build graph
    edges = analyzer.resolve_calls(all_elements, analyses)
    graph = CodeGraph()
    for eid, el in all_elements.items():
        graph.add_element(eid, el.kind.value)
    for edge in edges:
        graph.add_edge(edge)

    # Persist
    store.save_index(all_elements)
    store.save_file_analyses(analyses)
    store.save_edges(edges)

    n_files = len(py_files)
    n_elements = len(all_elements)
    n_edges = len(edges)
    click.echo(f"Indexed {n_files} files, {n_elements} elements, {n_edges} edges")


@cli.command()
@click.pass_context
def scan(ctx: click.Context) -> None:
    """Scan documentation and auto-detect code references."""
    import hashlib

    from doc_updater.docs.mapper import DocMapper
    from doc_updater.docs.scanner import DocScanner

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    store = JsonStore(store_dir)

    # Load index
    all_elements = store.load_index()
    if not all_elements:
        click.echo("No index found. Run 'doc-updater index' first.", err=True)
        sys.exit(1)

    scanner = DocScanner()
    mapper = DocMapper(all_elements)

    # Find markdown files
    md_files = sorted(repo.rglob("*.md"))
    md_files = [f for f in md_files if store_dir not in f.parents and f != store_dir]

    mappings: dict[str, dict] = {}
    total_mapped = 0
    total_unmapped = 0

    for md_file in md_files:
        rel_path = str(md_file.relative_to(repo))
        content = md_file.read_text(encoding="utf-8")
        file_hash = hashlib.sha256(content.encode()).hexdigest()

        raw_refs = scanner.scan_file(md_file)
        mapped_refs: list[dict] = []
        unmapped_refs: list[dict] = []

        for raw_ref in raw_refs:
            results = mapper.resolve(raw_ref)
            if results:
                for r in results:
                    mapped_refs.append({
                        "element_id": r.element_id,
                        "ref_type": r.ref_type,
                        "text": r.text,
                        "context": r.context,
                        "section": r.section,
                        "lineno": r.lineno,
                        "confidence": r.confidence,
                    })
            else:
                unmapped_refs.append({
                    "text": raw_ref.text,
                    "ref_type": raw_ref.ref_type,
                    "lineno": raw_ref.lineno,
                })

        mappings[rel_path] = {
            "file_hash": file_hash,
            "mapped": mapped_refs,
            "unmapped": unmapped_refs,
        }
        total_mapped += len(mapped_refs)
        total_unmapped += len(unmapped_refs)

    store.save_mappings(mappings)
    click.echo(f"Scanned {len(md_files)} docs, {total_mapped} references mapped, {total_unmapped} unmapped")
