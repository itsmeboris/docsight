"""Command-line interface for docsight."""
# pylint: disable=too-many-lines

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
import rich.console

from docsight.analyzer.graph import CodeGraph
from docsight.analyzer.python_analyzer import PythonAnalyzer
from docsight.config import (
    expand_file_path_docs,
    get_exclude_patterns,
    load_config,
    should_exclude,
)
from docsight.store.json_store import JsonStore


@click.group()
@click.option(
    "--repo",
    default=None,
    metavar="PATH",
    help="Path to the repository root (default: current directory).",
)
@click.pass_context
def cli(ctx: click.Context, repo: str | None) -> None:
    """docsight: detect stale documentation."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = Path(repo) if repo is not None else Path(os.getcwd())


@cli.command()
@click.option(
    "--no-baseline",
    is_flag=True,
    default=False,
    help="Skip auto-baseline (only create directory and .gitignore).",
)
@click.pass_context
def init(ctx: click.Context, no_baseline: bool) -> None:
    """Initialise docsight and set the baseline.

    Creates .docsight/, updates .gitignore, then auto-indexes,
    scans, and stores a verified baseline so the tool is immediately
    usable.  Pass --no-baseline to skip the baseline step.
    """
    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"

    # Create the store directory (idempotent).
    store_dir.mkdir(parents=True, exist_ok=True)

    # Add entries to .gitignore (idempotent — only add if not already present).
    gitignore = repo / ".gitignore"
    entries = [".docsight/"]

    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
    else:
        existing = ""

    additions = [e for e in entries if e not in existing]
    if additions:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        existing += "\n".join(additions) + "\n"
        gitignore.write_text(existing, encoding="utf-8")

    click.echo(f"Initialized docsight in {store_dir}")

    if no_baseline:
        return

    # Auto-baseline: index + scan + store verified state
    config = load_config(repo)
    exclude = get_exclude_patterns(config)
    store = JsonStore(store_dir)
    _run_index(repo, store, exclude=exclude)
    _run_scan(repo, store, exclude=exclude)
    ctx.invoke(check, baseline=True)

    # Install pre-push hook if this is a git repo
    hooks_dir = repo / ".git" / "hooks"
    if hooks_dir.exists():
        ctx.invoke(install)


@cli.command()
@click.option(
    "--keep-gitignore",
    is_flag=True,
    default=False,
    help="Do not remove the .docsight/ entry from .gitignore.",
)
@click.pass_context
def clean(ctx: click.Context, keep_gitignore: bool) -> None:
    """Remove all docsight data from the repository."""
    import shutil

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"

    # Always clean .gitignore, even if .docsight/ was already removed
    if not keep_gitignore:
        gitignore = repo / ".gitignore"
        if gitignore.exists():
            lines = gitignore.read_text(encoding="utf-8").splitlines(keepends=True)
            remove = {".docsight/"}
            filtered = [ln for ln in lines if ln.strip() not in remove]
            if len(filtered) != len(lines):
                gitignore.write_text("".join(filtered), encoding="utf-8")
                click.echo("Removed .docsight/ entry from .gitignore")

    if not store_dir.exists():
        click.echo("Nothing to clean — .docsight/ does not exist.")
        return

    shutil.rmtree(store_dir)
    click.echo(f"Removed {store_dir}")


# ---------------------------------------------------------------------------
# hooks command
# ---------------------------------------------------------------------------

_PRE_PUSH_HOOK = """\
#!/bin/sh
# docsight: fail push if docs are stale
# Consume stdin (git sends ref data; not reading it can hang the hook)
cat > /dev/null
# Skip gracefully if docsight is not installed
command -v docsight >/dev/null 2>&1 || exit 0
docsight check
"""


@cli.group()
def hooks() -> None:
    """Install or remove git hooks for docsight."""


@hooks.command()
@click.pass_context
def install(ctx: click.Context) -> None:
    """Install a pre-push hook that runs docsight check."""
    repo: Path = ctx.obj["repo"]
    hooks_dir = repo / ".git" / "hooks"
    if not hooks_dir.exists():
        click.echo("Not a git repository (no .git/hooks/).", err=True)
        sys.exit(1)

    hook_path = hooks_dir / "pre-push"
    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if "docsight check" in existing:
            click.echo("pre-push hook already installed.")
            return
        # Append to existing hook (stdin may already be drained by
        # the existing hook, but cat /dev/null is safe to repeat)
        if not existing.endswith("\n"):
            existing += "\n"
        existing += (
            "\n# docsight: fail push if docs are stale\n"
            "# Consume stdin (git sends ref data; not reading it can hang the hook)\n"
            "cat > /dev/null\n"
            "command -v docsight >/dev/null 2>&1 || exit 0\n"
            "docsight check\n"
        )
        hook_path.write_text(existing, encoding="utf-8")
    else:
        hook_path.write_text(_PRE_PUSH_HOOK, encoding="utf-8")

    hook_path.chmod(0o755)
    click.echo(f"Installed pre-push hook: {hook_path}")


@hooks.command()
@click.pass_context
def uninstall(ctx: click.Context) -> None:
    """Remove the docsight pre-push hook."""
    repo: Path = ctx.obj["repo"]
    hook_path = repo / ".git" / "hooks" / "pre-push"
    if not hook_path.exists():
        click.echo("No pre-push hook found.")
        return

    content = hook_path.read_text(encoding="utf-8")
    if "docsight check" not in content:
        click.echo("pre-push hook does not contain docsight — nothing to remove.")
        return

    # Remove all lines that are part of the docsight block
    _block_markers = {"docsight", "cat > /dev/null", "Consume stdin"}
    lines = content.splitlines(keepends=True)
    filtered = [
        ln for ln in lines
        if not any(m in ln for m in _block_markers)
    ]
    remaining = "".join(filtered).strip()
    if remaining and remaining != "#!/bin/sh":
        hook_path.write_text(remaining + "\n", encoding="utf-8")
        click.echo("Removed docsight from pre-push hook (other hooks preserved).")
    else:
        hook_path.unlink()
        click.echo("Removed pre-push hook.")


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
    store_dir = repo / ".docsight"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)

    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    analyzer = PythonAnalyzer()
    py_files = sorted(repo.rglob("*.py"))

    # Exclude files inside the store directory itself + user-configured patterns
    py_files = [
        p for p in py_files
        if store_dir not in p.parents and p != store_dir
        and not should_exclude(str(p.relative_to(repo)), exclude)
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

    from docsight.docs.mapper import DocMapper
    from docsight.docs.scanner import DocScanner

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store = JsonStore(store_dir)

    # Load index
    all_elements = store.load_index()
    if not all_elements:
        click.echo("No index found. Run 'docsight index' first.", err=True)
        sys.exit(1)

    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    scanner = DocScanner()
    mapper = DocMapper(all_elements)

    # Find markdown files
    md_files = sorted(repo.rglob("*.md"))
    md_files = [
        f for f in md_files
        if store_dir not in f.parents and f != store_dir
        and not should_exclude(str(f.relative_to(repo)), exclude)
    ]

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


def _stale_eids_from_report(last_report: dict) -> list[str]:
    """Extract stale element IDs from a last_report dict."""
    result: list[str] = []
    for doc_data in last_report.values():
        if not isinstance(doc_data, dict):
            continue
        if doc_data.get("status", "") not in ("stale", "STALE"):
            continue
        for issue in doc_data.get("issues", []):
            eid = issue.get("element_id", "") if isinstance(issue, dict) else ""
            if eid:
                result.append(eid)
    return result


def _run_index(repo: Path, store: JsonStore,
               exclude: list[str] | None = None) -> None:
    """Internal helper: run the index step with skip_errors=True."""
    store_dir = repo / ".docsight"
    exclude = exclude or []
    analyzer = PythonAnalyzer()
    py_files = sorted(repo.rglob("*.py"))
    py_files = [
        p for p in py_files
        if store_dir not in p.parents and p != store_dir
        and not should_exclude(str(p.relative_to(repo)), exclude)
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


def _run_scan(repo: Path, store: JsonStore,
              exclude: list[str] | None = None) -> None:
    """Internal helper: run the scan step."""
    import hashlib

    from docsight.docs.mapper import DocMapper
    from docsight.docs.scanner import DocScanner

    store_dir = repo / ".docsight"
    exclude = exclude or []
    all_elements = store.load_index()
    if not all_elements:
        return

    scanner = DocScanner()
    mapper = DocMapper(all_elements)

    md_files = sorted(repo.rglob("*.md"))
    md_files = [
        f for f in md_files
        if store_dir not in f.parents and f != store_dir
        and not should_exclude(str(f.relative_to(repo)), exclude)
    ]

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
    from docsight.staleness.detector import DocStatus, StalenessDetector
    from docsight.staleness.reporter import (
        has_stale,
        print_details,
        print_summary,
        to_json,
    )

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)
    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    # Auto-run index (skip_errors) + scan
    _run_index(repo, store, exclude=exclude)
    _run_scan(repo, store, exclude=exclude)

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
            "Warning: baseline was created with an older format (absolute paths). "
            "Run 'docsight check --baseline' to re-baseline.",
            err=True,
        )
        # Clear verified entirely so detector returns UNVERIFIED (not false HEALTHY)
        verified = {}
        state["verified"] = {}
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
    check_report = detector.check_all()

    # Serialize report for storage (statuses stored as string values)
    from docsight.staleness.detector import StalenessIssue

    serializable_report: dict[str, dict] = {}
    for doc_path, doc_data in check_report.items():
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
        click.echo(to_json(check_report))
    else:
        print_summary(check_report)
        print_details(check_report)

    if has_stale(check_report):
        sys.exit(1)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show the last staleness check summary."""
    from docsight.staleness.reporter import print_summary

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store = JsonStore(store_dir)

    state = store.load_state()
    last_report = state.get("last_report")

    if last_report is None:
        click.echo("No report found. Run 'docsight check' first.", err=True)
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
@click.option(
    "--flat",
    is_flag=True,
    default=False,
    help="Use flat vis.js layout instead of semantic zoom.",
)
@click.pass_context
def graph(ctx: click.Context, export_format: str, output: str | None,
          flat: bool) -> None:
    """Export the code dependency graph (semantic zoom by default)."""
    from docsight.analyzer.graph import export_zoom_html

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)
    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    # Auto-run index + scan if index is missing
    elements = store.load_index()
    if not elements:
        _run_index(repo, store, exclude=exclude)
        _run_scan(repo, store, exclude=exclude)
        elements = store.load_index()

    edges = store.load_edges()
    mappings = store.load_mappings()
    state = store.load_state()

    # Determine output path
    ext = "json" if export_format.lower() == "json" else "html"
    out_path = Path(output) if output else store_dir / f"graph.{ext}"

    if export_format.lower() == "json":
        graph_obj = CodeGraph()
        for eid, el in elements.items():
            graph_obj.add_element(eid, el.kind.value)
        for edge in edges:
            graph_obj.add_edge(edge)
        graph_obj.export_json(out_path)
    elif flat:
        graph_obj = CodeGraph()
        for eid, el in elements.items():
            graph_obj.add_element(eid, el.kind.value)
        for edge in edges:
            graph_obj.add_edge(edge)
        stale_elements = _stale_eids_from_report(state.get("last_report", {}))
        graph_obj.export_html(out_path, stale_elements=stale_elements)
    else:
        export_zoom_html(elements, edges, mappings, state, out_path)

    click.echo(f"Graph exported to {out_path}")


@cli.command()
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output file path (default: .docsight/report.html).")
@click.pass_context
def report(ctx: click.Context, output: str | None) -> None:
    """Generate an interactive HTML report with file-level drill-down."""
    from docsight.report import generate_html_report

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store = JsonStore(store_dir)
    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    # Auto-run index + scan if needed
    elements = store.load_index()
    if not elements:
        _run_index(repo, store, exclude=exclude)
        _run_scan(repo, store, exclude=exclude)
        elements = store.load_index()

    mappings = store.load_mappings()
    state = store.load_state()

    out_path = Path(output) if output else store_dir / "report.html"
    generate_html_report(elements, mappings, state, out_path)
    click.echo(f"Report generated: {out_path}")


@cli.command()
@click.argument("doc")
@click.pass_context
def show(ctx: click.Context, doc: str) -> None:
    """Show staleness details for a specific documentation file."""
    from docsight.staleness.reporter import print_doc_tree

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store = JsonStore(store_dir)

    state = store.load_state()
    last_report = state.get("last_report")

    if last_report is None:
        click.echo("No report found. Run 'docsight check' first.", err=True)
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


@cli.command()
@click.option("--json", "output_json", is_flag=True, default=False, help="Output JSON.")
@click.option(
    "--include-private",
    is_flag=True,
    default=False,
    help="Include private/underscore-prefixed elements.",
)
@click.option(
    "--all-elements",
    is_flag=True,
    default=False,
    help="Count every element (default: only public API — classes + module-level functions).",
)
@click.option(
    "--gaps",
    is_flag=True,
    default=False,
    help="Show files with zero documented public API, sorted by dependency weight.",
)
@click.pass_context
def coverage(ctx: click.Context, output_json: bool, include_private: bool,
             all_elements: bool, gaps: bool) -> None:
    """Show which code elements are documented and which are not."""
    from rich.table import Table

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store = JsonStore(store_dir)
    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    # Auto-run index + scan if needed
    elements = store.load_index()
    if not elements:
        _run_index(repo, store, exclude=exclude)
        _run_scan(repo, store, exclude=exclude)
        elements = store.load_index()

    mappings = store.load_mappings()

    # Collect all documented element IDs
    documented_eids: set[str] = set()
    for doc_data in mappings.values():
        for ref in doc_data.get("mapped", []):
            documented_eids.add(ref.get("element_id", ""))

    # File-path coverage: if a doc references a file path, expand to cover
    # all elements in that file (shared logic with report/graph).
    documented_eids = expand_file_path_docs(documented_eids, elements)

    if gaps:
        _coverage_gaps(store, elements, documented_eids, output_json)
        return

    # Categorise elements
    documented: list[str] = []
    undocumented: list[str] = []

    for eid, elem in elements.items():
        # Skip module-level elements
        if eid.endswith("::__module__"):
            continue
        # Skip private unless requested
        name = elem.name if hasattr(elem, "name") else eid.split("::")[-1]
        if not include_private and name.startswith("_"):
            continue

        # Default (API-only): only count classes + module-level functions.
        # Methods are covered by their parent class's documentation.
        if not all_elements:
            kind = elem.kind.value if hasattr(elem, "kind") else ""
            parent = elem.parent if hasattr(elem, "parent") else None
            if kind == "METHOD":
                continue
            if kind == "FUNCTION" and parent is not None:
                continue

        if eid in documented_eids:
            documented.append(eid)
        else:
            undocumented.append(eid)

    total = len(documented) + len(undocumented)
    pct = (len(documented) / total * 100) if total else 100.0

    mode = "all" if all_elements else "api"

    if output_json:
        import json as _json
        click.echo(_json.dumps({
            "mode": mode,
            "total": total,
            "documented": len(documented),
            "undocumented": len(undocumented),
            "coverage_pct": round(pct, 1),
            "undocumented_elements": sorted(undocumented),
        }, indent=2))
        return

    label = "elements" if all_elements else "public API elements"
    console = rich.console.Console()
    console.print(
        f"\nDoc coverage: [bold]{len(documented)}/{total}[/bold] "
        f"{label} documented ([bold]{pct:.0f}%[/bold])\n"
    )

    if undocumented:
        table = Table(title="Undocumented Elements", show_lines=False)
        table.add_column("Element", style="yellow")
        table.add_column("Kind", style="dim")
        table.add_column("File", style="dim")
        for eid in sorted(undocumented):
            elem = elements[eid]
            name = elem.name if hasattr(elem, "name") else eid
            kind = elem.kind.value if hasattr(elem, "kind") else "?"
            file_path = elem.file if hasattr(elem, "file") else "?"
            table.add_row(eid, kind, file_path)
        console.print(table)
    else:
        console.print("[green]All public elements are documented![/green]")


def _coverage_gaps(
    store: JsonStore,
    elements: dict,
    documented_eids: set[str],
    output_json: bool,
) -> None:
    """Show files with zero documented public API, sorted by dep weight."""
    edges = store.load_edges()

    # Build graph to count dependents per file
    dep_graph = CodeGraph()
    for eid, el in elements.items():
        dep_graph.add_element(eid, el.kind.value)
    for edge in edges:
        dep_graph.add_edge(edge)

    # Group public API by file, check if any are documented
    file_api: dict[str, list[str]] = {}
    for eid, elem in elements.items():
        if eid.endswith("::__module__"):
            continue
        name = elem.name if hasattr(elem, "name") else eid.split("::")[-1]
        if name.startswith("_"):
            continue
        kind = elem.kind.value if hasattr(elem, "kind") else ""
        parent = elem.parent if hasattr(elem, "parent") else None
        if kind == "METHOD" or (kind == "FUNCTION" and parent is not None):
            continue
        file_path = elem.file if hasattr(elem, "file") else ""
        file_api.setdefault(file_path, []).append(eid)

    # Find gap files (zero documented public API)
    gap_files: list[dict] = []
    for file_path, api_eids in sorted(file_api.items()):
        n_documented = sum(1 for e in api_eids if e in documented_eids)
        if n_documented > 0:
            continue
        # Count how many other files have edges INTO this file's elements
        all_file_eids = {
            eid for eid, el in elements.items()
            if (el.file if hasattr(el, "file") else "") == file_path
        }
        dependent_files: set[str] = set()
        for eid in all_file_eids:
            for dep_eid, _hops in dep_graph.get_dependents(eid, max_hops=1):
                dep_file = dep_eid.split("::")[0] if "::" in dep_eid else ""
                if dep_file and dep_file != file_path:
                    dependent_files.add(dep_file)
        gap_files.append({
            "file": file_path,
            "public_api": len(api_eids),
            "depended_on_by": len(dependent_files),
        })

    # Sort by dependency weight (most depended-on first)
    gap_files.sort(key=lambda g: (-g["depended_on_by"], g["file"]))

    if output_json:
        import json as _json
        click.echo(_json.dumps({
            "gap_files": gap_files,
            "total_gap_files": len(gap_files),
            "total_gap_elements": sum(g["public_api"] for g in gap_files),
        }, indent=2))
        return

    console = rich.console.Console()
    if not gap_files:
        console.print(
            "\n[green]No coverage gaps — every file with public API "
            "has at least one documented element.[/green]\n"
        )
        return

    total_elems = sum(g["public_api"] for g in gap_files)
    console.print(
        f"\n[bold]Coverage gaps:[/bold] {len(gap_files)} file(s) with "
        f"{total_elems} undocumented public API elements\n"
    )
    from rich.table import Table
    table = Table(show_lines=False)
    table.add_column("File", style="yellow")
    table.add_column("Public API", justify="right")
    table.add_column("Depended on by", justify="right", style="dim")
    for g in gap_files:
        dep_label = f"{g['depended_on_by']} file(s)" if g["depended_on_by"] else "—"
        table.add_row(g["file"], str(g["public_api"]), dep_label)
    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# impact command
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("target")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output JSON.")
@click.option("--max-hops", default=3, show_default=True,
              help="Maximum hops for impact analysis.")
@click.pass_context
def impact(ctx: click.Context, target: str, output_json: bool,
           max_hops: int) -> None:
    """Show the blast radius of changing a code element or file.

    TARGET can be an element ID (e.g. src/auth.py::AuthManager) or a
    file path (e.g. src/auth.py — expands to all elements in that file).
    """
    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)
    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    elements = store.load_index()
    if not elements:
        _run_index(repo, store, exclude=exclude)
        _run_scan(repo, store, exclude=exclude)
        elements = store.load_index()

    edges = store.load_edges()
    mappings = store.load_mappings()

    # Build graph
    dep_graph = CodeGraph()
    for eid, el in elements.items():
        dep_graph.add_element(eid, el.kind.value)
    for edge in edges:
        dep_graph.add_edge(edge)

    # Resolve target to element IDs
    seed_ids = _resolve_target(target, elements)
    if not seed_ids:
        click.echo(f"No elements found matching '{target}'.", err=True)
        sys.exit(1)

    # Reverse BFS: who depends on the changed elements?
    affected = dep_graph.impact_radius(seed_ids, max_hops=max_hops)

    # Build reverse mapping: element_id -> list of doc paths
    eid_to_docs: dict[str, list[str]] = {}
    for doc_path, doc_data in mappings.items():
        for ref in doc_data.get("mapped", []):
            eid = ref.get("element_id", "")
            if eid:
                eid_to_docs.setdefault(eid, []).append(doc_path)

    # Find affected docs (docs referencing any seed or affected element)
    all_affected_ids = set(seed_ids) | set(affected.keys())
    affected_docs: dict[str, list[str]] = {}
    for eid in all_affected_ids:
        for doc in eid_to_docs.get(eid, []):
            affected_docs.setdefault(doc, []).append(eid)

    if output_json:
        import json as _json
        click.echo(_json.dumps({
            "target": target,
            "seed_elements": seed_ids,
            "affected_elements": [
                {"element_id": eid, "hops": hops}
                for eid, hops in sorted(affected.items(), key=lambda x: x[1])
            ],
            "affected_docs": [
                {"doc": doc, "via": sorted(eids)}
                for doc, eids in sorted(affected_docs.items())
            ],
        }, indent=2))
        return

    console = rich.console.Console()
    console.print(f"\n[bold]Impact analysis for:[/bold] {target}\n")

    if not affected and not affected_docs:
        console.print("[green]No dependents found — change is isolated.[/green]")
        return

    if affected:
        from rich.table import Table
        table = Table(title="Affected Elements", show_lines=False)
        table.add_column("Element", style="yellow")
        table.add_column("Hops", style="dim", justify="right")
        for eid, hops in sorted(affected.items(), key=lambda x: x[1]):
            table.add_row(eid, str(hops))
        console.print(table)

    if affected_docs:
        console.print("\n[bold]Docs that may need updating:[/bold]")
        for doc, eids in sorted(affected_docs.items()):
            refs = ", ".join(e.split("::")[-1] for e in sorted(eids))
            console.print(f"  [cyan]{doc}[/cyan]  →  {refs}")
    console.print()


def _resolve_target(target: str, elements: dict) -> list[str]:
    """Resolve a CLI target to a list of element IDs.

    Accepts an exact element ID, a file path (expands to all elements
    in that file), or a partial match.
    """
    # Exact match
    if target in elements:
        return [target]

    # File path — expand to all non-module elements in that file
    file_matches = [
        eid for eid, el in elements.items()
        if (el.file if hasattr(el, "file") else "") == target
        and not eid.endswith("::__module__")
    ]
    if file_matches:
        return file_matches

    # Partial / suffix match
    partial = [
        eid for eid in elements
        if target in eid and not eid.endswith("::__module__")
    ]
    return partial


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------


@cli.command(name="diff")
@click.option("--base", default=None, metavar="REF",
              help="Git ref to compare against (default: stored baseline).")
@click.option("--json", "output_json", is_flag=True, default=False, help="Output JSON.")
@click.option("--max-hops", default=3, show_default=True,
              help="Maximum hops for impact analysis.")
@click.pass_context
def diff_cmd(ctx: click.Context, base: str | None, output_json: bool,
             max_hops: int) -> None:
    """Show which docs need updating based on code changes.

    Without --base, compares current code to the stored baseline.
    With --base REF, uses 'git diff REF' to find changed files, then
    re-analyses them to identify changed elements and affected docs.
    """
    import subprocess

    repo: Path = ctx.obj["repo"]
    store_dir = repo / ".docsight"
    store_dir.mkdir(parents=True, exist_ok=True)
    store = JsonStore(store_dir)
    config = load_config(repo)
    exclude = get_exclude_patterns(config)

    # Always re-index to get current state
    _run_index(repo, store, exclude=exclude)
    _run_scan(repo, store, exclude=exclude)

    current_elements = store.load_index()
    edges = store.load_edges()
    mappings = store.load_mappings()
    state = store.load_state()

    if base is not None:
        # Git-based diff: find changed Python files
        try:
            # Three-dot diff = changes on HEAD since merge-base with ref
            # (i.e. "what this branch changed", the PR semantic)
            result = subprocess.run(
                ["git", "-C", str(repo), "diff", "--name-only",
                 f"{base}...HEAD"],
                capture_output=True, text=True, check=True, timeout=30,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            click.echo(f"git diff failed: {exc}", err=True)
            sys.exit(1)
        changed_files = {
            f for f in result.stdout.strip().splitlines()
            if f.endswith(".py")
        }
    else:
        # Baseline-based diff: compare against stored verified hashes
        changed_files = None  # means "check all via baseline"

    # Build graph
    dep_graph = CodeGraph()
    for eid, el in current_elements.items():
        dep_graph.add_element(eid, el.kind.value)
    for edge in edges:
        dep_graph.add_edge(edge)

    # Find changed elements
    changed_elems = _find_changed_elements(
        current_elements, state, changed_files, exclude=exclude
    )

    if not changed_elems:
        if output_json:
            import json as _json
            click.echo(_json.dumps({
                "base": base or "baseline",
                "changed_elements": [],
                "affected_docs": [],
            }, indent=2))
        else:
            click.echo("No element changes detected.")
        return

    # Separate live vs deleted seeds (deleted elements aren't in graph)
    deleted_ids = {c["element_id"] for c in changed_elems
                   if c["change_type"] == "deleted"}
    live_seeds = [c["element_id"] for c in changed_elems
                  if c["change_type"] != "deleted"]

    # Impact analysis on live changed elements
    affected = dep_graph.impact_radius(live_seeds, max_hops=max_hops)

    # Map elements to docs (current mappings)
    eid_to_docs: dict[str, list[str]] = {}
    for doc_path, doc_data in mappings.items():
        for ref in doc_data.get("mapped", []):
            eid = ref.get("element_id", "")
            if eid:
                eid_to_docs.setdefault(eid, []).append(doc_path)

    # For deleted elements, check which docs referenced them in the baseline
    verified = state.get("verified", {})
    for doc_path, doc_verified in verified.items():
        for key in doc_verified.get("element_hashes", {}):
            if not key.endswith(":signature"):
                continue
            eid = key[: -len(":signature")]
            if eid in deleted_ids:
                eid_to_docs.setdefault(eid, []).append(doc_path)

    all_seeds = set(live_seeds) | deleted_ids
    all_affected = all_seeds | set(affected.keys())
    affected_docs: dict[str, list[dict]] = {}
    for eid in all_affected:
        hops = 0 if eid in all_seeds else affected.get(eid, 0)
        for doc in eid_to_docs.get(eid, []):
            affected_docs.setdefault(doc, []).append({
                "element_id": eid, "hops": hops,
            })

    if output_json:
        import json as _json
        click.echo(_json.dumps({
            "base": base or "baseline",
            "changed_elements": changed_elems,
            "affected_elements": [
                {"element_id": eid, "hops": hops}
                for eid, hops in sorted(affected.items(), key=lambda x: x[1])
            ],
            "affected_docs": [
                {"doc": doc, "via": sorted(refs, key=lambda r: r["hops"])}
                for doc, refs in sorted(affected_docs.items())
            ],
        }, indent=2))
        return

    console = rich.console.Console()
    console.print(
        f"\n[bold]Changes vs {base or 'baseline'}:[/bold] "
        f"{len(changed_elems)} element(s) changed\n"
    )

    from rich.table import Table
    table = Table(title="Changed Elements", show_lines=False)
    table.add_column("Element", style="red")
    table.add_column("Change", style="dim")
    for c in sorted(changed_elems, key=lambda x: x["element_id"]):
        table.add_row(c["element_id"], c["change_type"])
    console.print(table)

    if affected_docs:
        console.print("\n[bold]Docs that need updating:[/bold]")
        for doc, refs in sorted(affected_docs.items()):
            direct = [r for r in refs if r["hops"] == 0]
            trans = [r for r in refs if r["hops"] > 0]
            parts = []
            if direct:
                names = ", ".join(
                    r["element_id"].split("::")[-1] for r in direct
                )
                parts.append(f"direct: {names}")
            if trans:
                names = ", ".join(
                    r["element_id"].split("::")[-1] for r in trans
                )
                parts.append(f"transitive: {names}")
            console.print(f"  [cyan]{doc}[/cyan]  →  {'; '.join(parts)}")
    else:
        console.print(
            "\n[green]No docs reference the changed elements.[/green]"
        )
    console.print()


def _find_changed_elements(
    current_elements: dict,
    state: dict,
    changed_files: set[str] | None,
    exclude: list[str] | None = None,
) -> list[dict]:
    """Compare current element hashes to stored baseline.

    Returns a list of dicts: {element_id, change_type}.
    If *changed_files* is not None, only consider elements in those files.
    *exclude* patterns are used to suppress false-positive deletions for
    files that are excluded from indexing (vs genuinely removed).
    """
    verified = state.get("verified", {})
    # Collect all baseline hashes across all docs
    baseline_hashes: dict[str, dict[str, str]] = {}
    for doc_verified in verified.values():
        for key, value in doc_verified.get("element_hashes", {}).items():
            # Keys are "{eid}:signature" or "{eid}:body"
            if key.endswith(":signature"):
                eid = key[: -len(":signature")]
                baseline_hashes.setdefault(eid, {})["signature"] = value
            elif key.endswith(":body"):
                eid = key[: -len(":body")]
                baseline_hashes.setdefault(eid, {})["body"] = value

    changed: list[dict] = []
    for eid, elem in current_elements.items():
        if eid.endswith("::__module__"):
            continue
        file_path = elem.file if hasattr(elem, "file") else ""
        if changed_files is not None and file_path not in changed_files:
            continue
        if eid not in baseline_hashes:
            continue  # not baselined — can't compare

        bl = baseline_hashes[eid]
        if bl.get("signature") and bl["signature"] != elem.signature_hash:
            changed.append({"element_id": eid, "change_type": "signature"})
        elif bl.get("body") and bl["body"] != elem.body_hash:
            changed.append({"element_id": eid, "change_type": "body"})

    # Detect deleted/renamed elements: in baseline but no longer in current.
    # Without this, docs referencing a renamed function go silently unreported.
    # Only suppress if the element's file matches an exclude pattern — that
    # means the user intentionally excluded it, not that it was deleted.
    current_ids = set(current_elements.keys())
    exclude = exclude or []
    for eid in baseline_hashes:
        if eid in current_ids:
            continue
        eid_file = eid.split("::")[0] if "::" in eid else ""
        if eid_file and should_exclude(eid_file, exclude):
            continue  # file is excluded by config, not a real deletion
        if changed_files is not None and eid_file not in changed_files:
            continue
        changed.append({"element_id": eid, "change_type": "deleted"})

    return changed
