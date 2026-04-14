"""Generate an interactive HTML report with file-level drill-down."""

from __future__ import annotations

import html as _html
from pathlib import Path
from typing import Any


def generate_html_report(
    elements: dict[str, Any],
    mappings: dict[str, dict],
    state: dict[str, dict],
    output_path: str | Path,
) -> None:
    """Build a hierarchical HTML report: files -> classes -> methods.

    The report is a self-contained HTML file with no external dependencies.
    Files are collapsible sections. Each element shows its kind, staleness
    status, and which docs reference it.
    """
    last_report = state.get("last_report", {})

    # Build stale element set from last report
    stale_eids: set[str] = set()
    for doc_data in last_report.values():
        if not isinstance(doc_data, dict):
            continue
        for issue in doc_data.get("issues", []):
            eid = issue.get("element_id", "") if isinstance(issue, dict) else ""
            if eid:
                stale_eids.add(eid)

    # Build documented element set from mappings
    documented_eids: set[str] = set()
    # Also build reverse map: element_id -> list of doc paths
    eid_to_docs: dict[str, list[str]] = {}
    for doc_path, doc_data in mappings.items():
        for ref in doc_data.get("mapped", []):
            eid = ref.get("element_id", "")
            documented_eids.add(eid)
            eid_to_docs.setdefault(eid, []).append(doc_path)

    # Group elements by file
    files: dict[str, list[dict]] = {}
    for eid, elem in elements.items():
        if eid.endswith("::__module__"):
            continue
        file_path = elem.file if hasattr(elem, "file") else eid.split("::")[0]
        name = elem.name if hasattr(elem, "name") else eid.split("::")[-1]
        kind = elem.kind.value if hasattr(elem, "kind") else "?"
        parent = elem.parent if hasattr(elem, "parent") else None

        entry = {
            "eid": eid,
            "name": name,
            "kind": kind,
            "parent": parent,
            "is_stale": eid in stale_eids,
            "is_documented": eid in documented_eids,
            "docs": eid_to_docs.get(eid, []),
        }
        files.setdefault(file_path, []).append(entry)

    # Build doc staleness summary
    doc_summary: list[dict] = []
    for doc_path, doc_data in last_report.items():
        if not isinstance(doc_data, dict):
            continue
        status = doc_data.get("status", "healthy")
        n_issues = len(doc_data.get("issues", []))
        doc_summary.append({
            "path": doc_path,
            "status": status,
            "issues": n_issues,
        })

    # Sort files and elements
    for file_elems in files.values():
        file_elems.sort(key=lambda e: (e["kind"] != "CLASS", e["name"]))

    # Build HTML
    file_sections = []
    for file_path in sorted(files.keys()):
        elems = files[file_path]
        n_total = len(elems)
        n_stale = sum(1 for e in elems if e["is_stale"])
        n_undoc = sum(1 for e in elems if not e["is_documented"])

        # File status badge
        if n_stale > 0:
            file_badge = '<span class="badge stale">stale</span>'
        elif n_undoc > 0:
            file_badge = '<span class="badge undoc">undocumented</span>'
        else:
            file_badge = '<span class="badge ok">ok</span>'

        # Build element rows grouped by class
        classes: dict[str | None, list[dict]] = {}
        for elem in elems:
            classes.setdefault(elem["parent"], []).append(elem)

        rows_html = ""
        # First render top-level elements (parent=None)
        for elem in classes.get(None, []):
            if elem["kind"] == "CLASS":
                # Render class as a group
                methods = [e for e in elems if e["parent"] == elem["eid"]]
                rows_html += _render_class(elem, methods)
            else:
                rows_html += _render_element(elem, indent=0)

        safe_path = _html.escape(file_path)
        file_sections.append(f"""
<details class="file-section">
  <summary class="file-header">
    <span class="file-icon">&#128196;</span>
    <span class="file-path">{safe_path}</span>
    {file_badge}
    <span class="file-stats">{n_total} elements</span>
  </summary>
  <div class="file-body">{rows_html}</div>
</details>""")

    # Doc summary section
    doc_rows = ""
    for doc in sorted(doc_summary, key=lambda d: d["path"]):
        status = doc["status"]
        cls = "stale" if status in ("stale", "possibly_stale") else "ok"
        badge = f'<span class="badge {cls}">{_html.escape(status)}</span>'
        doc_rows += (
            f'<div class="doc-row">'
            f'<span class="doc-path">{_html.escape(doc["path"])}</span>'
            f'{badge}'
            f'</div>\n'
        )

    # Stats
    total_elems = sum(len(v) for v in files.values())
    total_stale = sum(1 for f in files.values() for e in f if e["is_stale"])
    total_undoc = sum(
        1 for f in files.values()
        for e in f
        if not e["is_documented"] and not e["name"].startswith("_")
    )
    total_doc = total_elems - total_undoc
    cov_pct = (total_doc / total_elems * 100) if total_elems else 100

    html = _HTML_TEMPLATE.format(
        n_files=len(files),
        n_elements=total_elems,
        n_stale=total_stale,
        n_undoc=total_undoc,
        cov_pct=f"{cov_pct:.0f}",
        file_sections="\n".join(file_sections),
        doc_rows=doc_rows,
    )

    Path(output_path).write_text(html, encoding="utf-8")


def _render_class(cls_elem: dict, methods: list[dict]) -> str:
    """Render a class with its methods as a nested collapsible."""
    status_cls = _status_class(cls_elem)
    safe_name = _html.escape(cls_elem["name"])
    docs_html = _docs_badges(cls_elem["docs"])

    method_rows = ""
    for m in sorted(methods, key=lambda x: x["name"]):
        method_rows += _render_element(m, indent=1)

    n_methods = len(methods)
    return f"""
<details class="class-section" open>
  <summary class="elem-row {status_cls}">
    <span class="kind-badge class">CLASS</span>
    <span class="elem-name">{safe_name}</span>
    {docs_html}
    <span class="method-count">{n_methods} methods</span>
  </summary>
  <div class="class-body">{method_rows}</div>
</details>"""


def _render_element(elem: dict, indent: int = 0) -> str:
    """Render a single element row."""
    status_cls = _status_class(elem)
    safe_name = _html.escape(elem["name"])
    kind = elem["kind"].upper()
    kind_cls = elem["kind"].lower()
    docs_html = _docs_badges(elem["docs"])
    indent_cls = "indent" if indent > 0 else ""

    return (
        f'<div class="elem-row {status_cls} {indent_cls}">'
        f'<span class="kind-badge {kind_cls}">{kind}</span>'
        f'<span class="elem-name">{safe_name}</span>'
        f'{docs_html}'
        f'</div>\n'
    )


def _status_class(elem: dict) -> str:
    """Return CSS class for element status."""
    if elem["is_stale"]:
        return "status-stale"
    if not elem["is_documented"] and not elem["name"].startswith("_"):
        return "status-undoc"
    return "status-ok"


def _docs_badges(docs: list[str]) -> str:
    """Render small badges for docs that reference this element."""
    if not docs:
        return '<span class="no-docs">no docs</span>'
    badges = []
    for doc in docs:
        short = doc.split("/")[-1] if "/" in doc else doc
        badges.append(f'<span class="doc-badge">{_html.escape(short)}</span>')
    return " ".join(badges)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>doc-updater report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0d1117; color: #c9d1d9;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    font-size: 14px; line-height: 1.5;
  }}
  header {{
    background: #161b22; border-bottom: 1px solid #30363d;
    padding: 16px 24px; display: flex; align-items: center; gap: 24px;
  }}
  header h1 {{ font-size: 18px; font-weight: 600; }}
  .stats {{ display: flex; gap: 20px; font-size: 13px; color: #8b949e; }}
  .stats b {{ color: #c9d1d9; }}
  .stats .warn {{ color: #d29922; }}
  .stats .bad {{ color: #f85149; }}
  main {{ max-width: 960px; margin: 0 auto; padding: 20px 24px; }}
  h2 {{
    font-size: 14px; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.5px; color: #8b949e; margin: 24px 0 12px;
    border-bottom: 1px solid #21262d; padding-bottom: 6px;
  }}

  /* File sections */
  .file-section {{
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    margin-bottom: 8px;
  }}
  .file-header {{
    padding: 10px 16px; cursor: pointer; display: flex;
    align-items: center; gap: 10px; font-size: 13px;
    list-style: none;
  }}
  .file-header::-webkit-details-marker {{ display: none; }}
  .file-header::before {{
    content: "\\25B6"; font-size: 10px; color: #484f58;
    transition: transform 0.15s;
  }}
  details[open] > .file-header::before {{ transform: rotate(90deg); }}
  .file-icon {{ font-size: 16px; }}
  .file-path {{ font-family: monospace; font-weight: 500; flex: 1; }}
  .file-stats {{ color: #484f58; font-size: 12px; }}
  .file-body {{ padding: 0 16px 12px; }}

  /* Element rows */
  .elem-row {{
    padding: 6px 8px; border-radius: 4px; margin: 2px 0;
    display: flex; align-items: center; gap: 8px; font-size: 13px;
  }}
  .elem-row.indent {{ margin-left: 24px; }}
  .elem-row:hover {{ background: #1c2128; }}
  .elem-row.status-stale {{ border-left: 3px solid #f85149; }}
  .elem-row.status-undoc {{ border-left: 3px solid #d29922; }}
  .elem-row.status-ok {{ border-left: 3px solid transparent; }}
  .elem-name {{ font-family: monospace; font-weight: 500; }}

  /* Class sections */
  .class-section {{ margin: 4px 0; }}
  .class-body {{ padding-left: 8px; }}

  /* Kind badges */
  .kind-badge {{
    font-size: 10px; font-weight: 600; padding: 1px 6px;
    border-radius: 3px; text-transform: uppercase; min-width: 56px;
    text-align: center; display: inline-block;
  }}
  .kind-badge.class {{ background: #1f3a5f; color: #58a6ff; }}
  .kind-badge.method {{ background: #1a3a4a; color: #67b7dc; }}
  .kind-badge.function {{ background: #1a3a2a; color: #7ec8a0; }}

  /* Status badges */
  .badge {{
    font-size: 11px; font-weight: 500; padding: 1px 8px;
    border-radius: 10px;
  }}
  .badge.ok {{ background: #1a3a2a; color: #7ec8a0; }}
  .badge.stale {{ background: #3d1a1a; color: #f85149; }}
  .badge.undoc {{ background: #3d2e1a; color: #d29922; }}

  /* Doc badges */
  .doc-badge {{
    font-size: 10px; background: #21262d; color: #8b949e;
    padding: 1px 6px; border-radius: 3px; font-family: monospace;
  }}
  .no-docs {{
    font-size: 10px; color: #484f58; font-style: italic;
  }}

  /* Doc summary rows */
  .doc-row {{
    padding: 6px 8px; display: flex; align-items: center; gap: 10px;
    font-size: 13px; font-family: monospace;
  }}
  .doc-path {{ flex: 1; }}
</style>
</head>
<body>
<header>
  <h1>doc-updater report</h1>
  <div class="stats">
    <span>Files: <b>{n_files}</b></span>
    <span>Elements: <b>{n_elements}</b></span>
    <span>Stale: <b class="bad">{n_stale}</b></span>
    <span>Undocumented: <b class="warn">{n_undoc}</b></span>
    <span>Coverage: <b>{cov_pct}%</b></span>
  </div>
</header>
<main>
  <h2>Documentation Status</h2>
  {doc_rows}

  <h2>Code Elements by File</h2>
  {file_sections}
</main>
</body>
</html>"""
