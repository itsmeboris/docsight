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
        fa = analyzer.analyze_file(py_file, repo_root=repo)
        analyses[fa.file] = fa
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
    dep_graph = CodeGraph()
    for eid, el in all_elements.items():
        dep_graph.add_element(eid, el.kind.value)
    for edge in edges:
        dep_graph.add_edge(edge)

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


def _run_index(repo: Path, store: JsonStore) -> None:
    """Internal helper: run the index step with skip_errors=True."""
    store_dir = repo / ".doc-updater"
    analyzer = PythonAnalyzer()
    py_files = sorted(repo.rglob("*.py"))
    py_files = [
        p for p in py_files if store_dir not in p.parents and p != store_dir
    ]

    analyses = {}
    for py_file in py_files:
        fa = analyzer.analyze_file(py_file, repo_root=repo)
        analyses[fa.file] = fa

    all_elements = {}
    for fa in analyses.values():
        for el in fa.elements:
            all_elements[el.element_id] = el

    edges = analyzer.resolve_calls(all_elements, analyses)
    dep_graph = CodeGraph()
    for eid, el in all_elements.items():
        dep_graph.add_element(eid, el.kind.value)
    for edge in edges:
        dep_graph.add_edge(edge)

    store.save_index(all_elements)
    store.save_file_analyses(analyses)
    store.save_edges(edges)


def _run_scan(repo: Path, store: JsonStore) -> None:
    """Internal helper: run the scan step."""
    import hashlib

    from doc_updater.docs.mapper import DocMapper
    from doc_updater.docs.scanner import DocScanner

    store_dir = repo / ".doc-updater"
    all_elements = store.load_index()
    if not all_elements:
        return

    scanner = DocScanner()
    mapper = DocMapper(all_elements)

    md_files = sorted(repo.rglob("*.md"))
    md_files = [f for f in md_files if store_dir not in f.parents and f != store_dir]

    mappings: dict[str, dict] = {}

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

    store.save_mappings(mappings)


@cli.command()
@click.option(
    "--baseline",
    is_flag=True,
    default=False,
    help="Store current hashes as verified baseline.",
)
@click.option("--json", "output_json", is_flag=True, default=False, help="Output JSON.")
@click.option(
    "--max-hops",
    default=3,
    show_default=True,
    help="Maximum transitive hops to check.",
)
@click.option(
    "--direct-only",
    is_flag=True,
    default=False,
    help="Only check direct references (max_hops=0).",
)
@click.pass_context
def check(
    ctx: click.Context,
    baseline: bool,
    output_json: bool,
    max_hops: int,
    direct_only: bool,
) -> None:
    """Check documentation for staleness."""
    from doc_updater.staleness.detector import DocStatus, StalenessDetector
    from doc_updater.staleness.reporter import (
        has_stale,
        print_details,
        print_summary,
        to_json,
    )

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)

    # Auto-run index (skip_errors) + scan
    _run_index(repo, store)
    _run_scan(repo, store)

    # Load data
    elements = store.load_index()
    mappings = store.load_mappings()
    state = store.load_state()
    edges = store.load_edges()

    # Rebuild graph
    dep_graph = CodeGraph()
    for eid, el in elements.items():
        dep_graph.add_element(eid, el.kind.value)
    for edge in edges:
        dep_graph.add_edge(edge)

    effective_max_hops = 0 if direct_only else max_hops

    if baseline:
        # Store current hashes as verified state
        verified: dict[str, dict] = {}

        for doc_path, doc_data in mappings.items():
            mapped_refs: list[dict] = doc_data.get("mapped", [])
            element_hashes: dict[str, str] = {}
            direct_element_ids: list[str] = []

            for ref in mapped_refs:
                eid = ref.get("element_id", "")
                if eid in elements:
                    el = elements[eid]
                    element_hashes[f"{eid}:signature"] = el.signature_hash
                    element_hashes[f"{eid}:body"] = el.body_hash
                    direct_element_ids.append(eid)

            # Compute dependency closure
            dep_closure = dep_graph.dependency_closure(
                direct_element_ids, max_hops=effective_max_hops
            )

            dependency_hashes: dict[str, dict] = {}
            for dep_id, hops in dep_closure.items():
                if dep_id in elements:
                    dep_el = elements[dep_id]
                    # Use source_hash as the transitive hash
                    dep_hash = dep_el.source_hash
                    dependency_hashes[dep_id] = {"hash": dep_hash, "hops": hops}

            verified[doc_path] = {
                "element_hashes": element_hashes,
                "dependency_hashes": dependency_hashes,
            }

        state["verified"] = verified

        # Build an "all healthy" report for baseline
        baseline_report: dict[str, dict] = {}
        for doc_path in mappings:
            baseline_report[doc_path] = {
                "status": DocStatus.HEALTHY.value,
                "issues": [],
            }
        state["last_report"] = baseline_report
        state["format_version"] = 2  # relative-path element IDs

        store.save_state(state)
        click.echo("Baseline stored.")
        return

    # Reference-lost comparison (Codex fix #23):
    # Compare previously-baselined refs against current mappings.
    # If a ref existed in baseline but is now absent from current mapped refs
    # (e.g., function was renamed), inject it back into mappings so the
    # detector can flag it as reference_lost.
    #
    # Skip if baseline was created with an older format (absolute paths)
    # to avoid false reference_lost on upgrade.
    verified = state.get("verified", {})
    state_version = state.get("format_version", 1)
    if state_version < 2 and verified:
        click.echo(
            "Warning: baseline was created with an older version. "
            "Run 'doc-updater check --baseline' to re-baseline.",
            err=True,
        )
        verified = {}  # skip reference-lost for old baselines
    for doc_path, doc_verified in verified.items():
        if doc_path not in mappings:
            continue
        current_mapped_eids = {
            r.get("element_id")
            for r in mappings[doc_path].get("mapped", [])
        }
        for key in doc_verified.get("element_hashes", {}):
            # Keys are "{eid}:signature" or "{eid}:body"
            if not key.endswith(":signature"):
                continue
            eid = key[: -len(":signature")]
            if eid not in current_mapped_eids:
                # This element was in the baseline but is no longer mapped
                # Inject a synthetic mapped ref so the detector picks it up
                mappings[doc_path].setdefault("mapped", []).append({
                    "element_id": eid,
                    "ref_type": "baseline_reference_lost",
                    "confidence": 0.95,
                    "lineno": 0,
                    "text": eid.split("::")[-1] if "::" in eid else eid,
                })

    # Run detection
    detector = StalenessDetector(
        elements=elements,
        mappings=mappings,
        state=state,
        graph=dep_graph,
        max_hops=effective_max_hops,
    )
    report = detector.check_all()

    # Serialize report for storage (statuses stored as string values)
    from doc_updater.staleness.detector import StalenessIssue

    serializable_report: dict[str, dict] = {}
    for doc_path, doc_data in report.items():
        doc_status = doc_data.get("status")
        status_str = (
            doc_status.value if isinstance(doc_status, DocStatus) else str(doc_status)
        )
        issues_out = []
        for issue in doc_data.get("issues", []):
            if isinstance(issue, StalenessIssue):
                issues_out.append({
                    "element_id": issue.element_id,
                    "change_type": issue.change_type,
                    "confidence": issue.confidence,
                    "hops": issue.hops,
                    "detail": issue.detail,
                })
            else:
                issues_out.append(issue)
        serializable_report[doc_path] = {
            "status": status_str,
            "issues": issues_out,
        }

    state["last_report"] = serializable_report
    store.save_state(state)

    if output_json:
        click.echo(to_json(report))
    else:
        print_summary(report)
        print_details(report)

    if has_stale(report):
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the last staleness check summary."""
    from doc_updater.staleness.reporter import print_summary

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    store = JsonStore(store_dir)

    state = store.load_state()
    last_report = state.get("last_report")

    if last_report is None:
        click.echo("No report found. Run 'doc-updater check' first.", err=True)
        sys.exit(1)

    print_summary(last_report)


@cli.command()
@click.option(
    "--export",
    "export_format",
    default="html",
    show_default=True,
    type=click.Choice(["html", "json"], case_sensitive=False),
    help="Export format: html or json.",
)
@click.option(
    "--output",
    "-o",
    default=None,
    metavar="PATH",
    help="Output file path (default: <repo>/graph.html or graph.json).",
)
@click.pass_context
def graph(ctx: click.Context, export_format: str, output: str | None) -> None:
    """Export the code dependency graph."""
    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)

    # Auto-run index + scan if index is missing
    elements = store.load_index()
    if not elements:
        _run_index(repo, store)
        _run_scan(repo, store)
        elements = store.load_index()

    edges = store.load_edges()

    # Build graph
    graph_obj = CodeGraph()
    for eid, el in elements.items():
        graph_obj.add_element(eid, el.kind.value)
    for edge in edges:
        graph_obj.add_edge(edge)

    # Determine stale elements from last report
    state = store.load_state()
    last_report = state.get("last_report", {})
    stale_elements: list[str] = []
    for _doc_path, doc_data in last_report.items():
        if isinstance(doc_data, dict):
            doc_status = doc_data.get("status", "")
            if doc_status in ("stale", "STALE"):
                for issue in doc_data.get("issues", []):
                    eid = issue.get("element_id", "") if isinstance(issue, dict) else ""
                    if eid:
                        stale_elements.append(eid)

    # Determine output path
    ext = "json" if export_format.lower() == "json" else "html"
    out_path = Path(output) if output else repo / f"graph.{ext}"

    if export_format.lower() == "json":
        graph_obj.export_json(out_path)
    else:
        graph_obj.export_html(out_path, stale_elements=stale_elements, doc_mappings=last_report)

    click.echo(f"Graph exported to {out_path}")


@cli.command()
@click.argument("doc")
@click.pass_context
def show(ctx: click.Context, doc: str) -> None:
    """Show staleness details for a specific documentation file."""
    from doc_updater.staleness.reporter import print_doc_tree

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".doc-updater"
    store = JsonStore(store_dir)

    state = store.load_state()
    last_report = state.get("last_report")

    if last_report is None:
        click.echo("No report found. Run 'doc-updater check' first.", err=True)
        sys.exit(1)

    # Find the doc in the report (support partial path matching)
    doc_key = None
    if doc in last_report:
        doc_key = doc
    else:
        for key in last_report:
            if key.endswith(doc) or doc in key:
                doc_key = key
                break

    if doc_key is None:
        click.echo(f"Document '{doc}' not found in last report.", err=True)
        sys.exit(1)

    doc_data = last_report[doc_key]

    # Load mappings to get refs
    mappings = store.load_mappings()
    refs: list[dict] = []
    if doc_key in mappings:
        refs = mappings[doc_key].get("mapped", [])

    print_doc_tree(doc_key, doc_data, refs)
