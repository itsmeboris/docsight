"""Rich-formatted reporter for staleness results."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from doc_updater.staleness.detector import DocStatus, StalenessIssue

_console = Console()


def summarize(report: dict[str, dict]) -> dict[str, int]:
    """Return counts of each status in the report.

    Returns a dict with keys: total, healthy, stale, possibly_stale, unverified.
    """
    counts: dict[str, int] = {
        "total": 0,
        "healthy": 0,
        "stale": 0,
        "possibly_stale": 0,
        "unverified": 0,
    }
    for doc_data in report.values():
        counts["total"] += 1
        status = doc_data.get("status")
        if status == DocStatus.HEALTHY or status == DocStatus.HEALTHY.value:
            counts["healthy"] += 1
        elif status == DocStatus.STALE or status == DocStatus.STALE.value:
            counts["stale"] += 1
        elif (
            status == DocStatus.POSSIBLY_STALE
            or status == DocStatus.POSSIBLY_STALE.value
        ):
            counts["possibly_stale"] += 1
        elif status == DocStatus.UNVERIFIED or status == DocStatus.UNVERIFIED.value:
            counts["unverified"] += 1
    return counts


def has_stale(report: dict[str, dict]) -> bool:
    """Return True if any document is STALE or POSSIBLY_STALE."""
    for doc_data in report.values():
        status = doc_data.get("status")
        if status in (
            DocStatus.STALE, DocStatus.STALE.value,
            DocStatus.POSSIBLY_STALE, DocStatus.POSSIBLY_STALE.value,
        ):
            return True
    return False


def print_summary(report: dict[str, dict], console: Console | None = None) -> None:
    """Print a Rich panel summarising the staleness report."""
    con = console or _console
    counts = summarize(report)

    lines = [
        f"Total docs:      {counts['total']}",
        f"Healthy:         {counts['healthy']}",
        f"Stale:           {counts['stale']}",
        f"Possibly stale:  {counts['possibly_stale']}",
        f"Unverified:      {counts['unverified']}",
    ]
    body = "\n".join(lines)
    con.print(Panel(body, title="Staleness Summary", expand=False))


def print_details(report: dict[str, dict], console: Console | None = None) -> None:
    """Print per-doc details for stale or possibly-stale documents."""
    con = console or _console

    for doc_path, doc_data in report.items():
        status = doc_data.get("status")
        issues: list[Any] = doc_data.get("issues", [])

        if status not in (
            DocStatus.STALE,
            DocStatus.STALE.value,
            DocStatus.POSSIBLY_STALE,
            DocStatus.POSSIBLY_STALE.value,
        ):
            continue

        status_str = status.value if isinstance(status, DocStatus) else str(status)
        con.print(f"\n[bold]{doc_path}[/bold] — {status_str}")
        for issue in issues:
            if isinstance(issue, StalenessIssue):
                con.print(
                    f"  • [{issue.change_type}] {issue.element_id} "
                    f"(confidence={issue.confidence:.2f}, hops={issue.hops})"
                )
                if issue.detail:
                    con.print(f"    {issue.detail}")
            elif isinstance(issue, dict):
                change_type = issue.get("change_type", "")
                element_id = issue.get("element_id", "")
                confidence = issue.get("confidence", 0.0)
                hops = issue.get("hops", 0)
                detail = issue.get("detail", "")
                con.print(
                    f"  • [{change_type}] {element_id} "
                    f"(confidence={confidence:.2f}, hops={hops})"
                )
                if detail:
                    con.print(f"    {detail}")


def print_doc_tree(
    doc_path: str,
    doc_data: dict,
    refs: list[dict],
    console: Console | None = None,
) -> None:
    """Print a Rich tree view for a single document (used by the show command)."""
    con = console or _console

    status = doc_data.get("status")
    status_str = status.value if isinstance(status, DocStatus) else str(status)

    tree = Tree(f"[bold]{doc_path}[/bold] [{status_str}]")

    issues: list[Any] = doc_data.get("issues", [])
    if issues:
        issues_branch = tree.add("[red]Issues[/red]")
        for issue in issues:
            if isinstance(issue, StalenessIssue):
                issues_branch.add(
                    f"[{issue.change_type}] {issue.element_id} "
                    f"(confidence={issue.confidence:.2f})"
                )
            elif isinstance(issue, dict):
                change_type = issue.get("change_type", "")
                element_id = issue.get("element_id", "")
                confidence = issue.get("confidence", 0.0)
                issues_branch.add(
                    f"[{change_type}] {element_id} (confidence={confidence:.2f})"
                )

    if refs:
        refs_branch = tree.add("[blue]References[/blue]")
        for ref in refs:
            element_id = ref.get("element_id", "")
            ref_type = ref.get("ref_type", "")
            confidence = ref.get("confidence", 0.0)
            refs_branch.add(
                f"{element_id} [{ref_type}] (confidence={confidence:.2f})"
            )

    con.print(tree)


def _issue_to_dict(issue: Any) -> dict:
    """Convert a StalenessIssue or dict to a plain dict for JSON serialization."""
    if isinstance(issue, StalenessIssue):
        return {
            "element_id": issue.element_id,
            "change_type": issue.change_type,
            "confidence": issue.confidence,
            "hops": issue.hops,
            "detail": issue.detail,
        }
    return issue


def to_json(report: dict[str, dict]) -> str:
    """Serialize the staleness report to a JSON string."""
    serializable: dict[str, dict] = {}
    for doc_path, doc_data in report.items():
        status = doc_data.get("status")
        status_str = status.value if isinstance(status, DocStatus) else str(status)
        issues = [_issue_to_dict(i) for i in doc_data.get("issues", [])]
        serializable[doc_path] = {
            "status": status_str,
            "issues": issues,
        }
    counts = summarize(report)
    stale_docs = [
        {"doc": doc_path, **doc_data}
        for doc_path, doc_data in serializable.items()
        if doc_data["status"] in ("stale", "possibly_stale")
    ]
    return json.dumps(
        {"summary": counts, "stale_docs": stale_docs, "docs": serializable},
        indent=2,
    )
