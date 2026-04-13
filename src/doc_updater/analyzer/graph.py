"""Code dependency graph backed by networkx."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx

from doc_updater.analyzer.base import EdgeKind, GraphEdge


class CodeGraph:
    """Directed dependency graph for code elements."""

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_element(self, element_id: str, kind: str) -> None:
        """Add a node representing a code element."""
        self._g.add_node(element_id, kind=kind)

    def add_edge(self, edge: GraphEdge) -> None:
        """Add a directed edge to the graph."""
        if not self._g.has_node(edge.source):
            self._g.add_node(edge.source)
        if not self._g.has_node(edge.target):
            self._g.add_node(edge.target)
        self._g.add_edge(edge.source, edge.target, kind=edge.kind.value)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_dependencies(
        self, element_id: str, max_hops: int = 3
    ) -> list[tuple[str, int]]:
        """BFS forward from *element_id*; return (node, hop_distance) pairs."""
        return self._bfs(self._g, element_id, max_hops)

    def get_dependents(
        self, element_id: str, max_hops: int = 3
    ) -> list[tuple[str, int]]:
        """BFS on the reversed graph; return nodes that depend on *element_id*."""
        return self._bfs(self._g.reverse(copy=False), element_id, max_hops)

    def impact_radius(
        self, changed_elements: list[str], max_hops: int = 3
    ) -> dict[str, int]:
        """Reverse BFS from *changed_elements*; return {node: min_hop_distance}."""
        rev = self._g.reverse(copy=False)
        return self._multi_source_bfs(rev, changed_elements, max_hops)

    def dependency_closure(
        self, element_ids: list[str], max_hops: int = 3
    ) -> dict[str, int]:
        """Forward BFS from *element_ids*; return {node: min_hop_distance}."""
        return self._multi_source_bfs(self._g, element_ids, max_hops)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_serializable(self) -> dict[str, Any]:
        """Convert to a JSON-compatible dict."""
        nodes = [
            {"id": n, "kind": self._g.nodes[n].get("kind", "")}
            for n in self._g.nodes
        ]
        edges = [
            {"source": u, "target": v, "kind": self._g.edges[u, v].get("kind", "")}
            for u, v in self._g.edges
        ]
        return {"nodes": nodes, "edges": edges}

    def export_html(
        self,
        path: str | Path,
        stale_elements: list[str] | None = None,
        doc_mappings: dict[str, Any] | None = None,
    ) -> None:
        """Export the graph as an interactive HTML file using vis.js.

        Parameters
        ----------
        path:
            Destination file path for the HTML output.
        stale_elements:
            Optional list of element IDs that should be highlighted red.
        doc_mappings:
            Optional mapping of doc paths to their reference data (used for
            tooltip context).
        """
        stale_set: set[str] = set(stale_elements or [])
        doc_mappings = doc_mappings or {}

        # Collect stale counts from doc_mappings for the stats panel
        stale_doc_count = len(
            [
                dp
                for dp, dd in doc_mappings.items()
                if isinstance(dd, dict) and dd.get("status") in ("stale", "STALE")
            ]
        )

        # Build vis.js node / edge structures
        vis_nodes: list[dict[str, Any]] = []
        vis_edges: list[dict[str, Any]] = []

        _KIND_SHAPE: dict[str, str] = {
            "FUNCTION": "circle",
            "METHOD": "circle",
            "CLASS": "diamond",
            "MODULE": "box",
        }
        _KIND_COLOR: dict[str, str] = {
            "FUNCTION": "#7EC8A0",
            "METHOD": "#67B7DC",
            "CLASS": "#4A90D9",
            "MODULE": "#A0A0A0",
        }
        _STALE_COLOR = "#FF4444"

        for node_id in self._g.nodes:
            kind = self._g.nodes[node_id].get("kind", "")
            is_stale = node_id in stale_set
            color = _STALE_COLOR if is_stale else _KIND_COLOR.get(kind, "#A0A0A0")
            shape = _KIND_SHAPE.get(kind, "ellipse")
            # Short label: last component of element_id
            label = node_id.split("::")[-1] if "::" in node_id else node_id
            import html as _html
            safe_id = _html.escape(node_id)
            safe_kind = _html.escape(kind)
            safe_label = _html.escape(label)
            vis_nodes.append(
                {
                    "id": node_id,
                    "label": safe_label,
                    "title": f"<b>{safe_id}</b><br>Kind: {safe_kind}"
                    + (" <b>[STALE]</b>" if is_stale else ""),
                    "color": {"background": color, "border": "#222222"},
                    "shape": shape,
                    "font": {"color": "#E0E0E0"},
                }
            )

        for i, (u, v) in enumerate(self._g.edges):
            edge_kind = self._g.edges[u, v].get("kind", "CALLS")
            dashes = edge_kind == "INHERITS"
            edge_color = "#C8A020" if dashes else "#888888"
            vis_edges.append(
                {
                    "id": i,
                    "from": u,
                    "to": v,
                    "dashes": dashes,
                    "color": {"color": edge_color},
                    "arrows": "to",
                    "title": edge_kind,
                }
            )

        n_nodes = len(vis_nodes)
        n_edges = len(vis_edges)
        n_stale = len(stale_set)

        nodes_json = json.dumps(vis_nodes)
        edges_json = json.dumps(vis_edges)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>doc-updater: Code Graph</title>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    body {{
      background: #0D1117;
      color: #E0E0E0;
      font-family: sans-serif;
      margin: 0;
      padding: 0;
    }}
    #legend {{
      background: #161B22;
      padding: 8px 16px;
      display: flex;
      gap: 20px;
      align-items: center;
      border-bottom: 1px solid #30363D;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
    }}
    .legend-dot {{
      width: 14px;
      height: 14px;
      border-radius: 3px;
      display: inline-block;
    }}
    #stats {{
      background: #161B22;
      padding: 6px 16px;
      font-size: 13px;
      border-bottom: 1px solid #30363D;
    }}
    #controls {{
      background: #161B22;
      padding: 6px 16px;
      border-bottom: 1px solid #30363D;
    }}
    #search {{
      background: #21262D;
      color: #E0E0E0;
      border: 1px solid #30363D;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 13px;
      width: 260px;
    }}
    #network {{
      width: 100%;
      height: calc(100vh - 120px);
    }}
  </style>
</head>
<body>
  <div id="legend">
    <strong>Legend:</strong>
    <div class="legend-item"><div class="legend-dot" style="background:#4A90D9;"></div> Class</div>
    <div class="legend-item"><div class="legend-dot" style="background:#67B7DC;"></div> Method</div>
    <div class="legend-item"><div class="legend-dot" style="background:#7EC8A0;"></div> Function</div>
    <div class="legend-item"><div class="legend-dot" style="background:#FF4444;"></div> Stale</div>
    <div class="legend-item"><div class="legend-dot" style="background:#888888;"></div> Calls (solid)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#C8A020;"></div> Inherits (dashed)</div>
  </div>
  <div id="stats">
    Nodes: <b>{n_nodes}</b> &nbsp;|&nbsp; Edges: <b>{n_edges}</b> &nbsp;|&nbsp; Stale: <b>{n_stale}</b> &nbsp;|&nbsp; Stale docs: <b>{stale_doc_count}</b>
  </div>
  <div id="controls">
    <input id="search" type="text" placeholder="Search nodes..." />
  </div>
  <div id="network"></div>
  <script>
    var nodesData = {nodes_json};
    var edgesData = {edges_json};

    var nodesById = {{}};
    nodesData.forEach(function(n) {{ nodesById[n.id] = n; }});

    var nodes = new vis.DataSet(nodesData);
    var edges = new vis.DataSet(edgesData);
    var container = document.getElementById("network");
    var data = {{ nodes: nodes, edges: edges }};
    var options = {{
      background: "#0D1117",
      physics: {{ stabilization: true }},
      nodes: {{ borderWidth: 1 }},
      edges: {{ smooth: {{ type: "dynamic" }} }},
    }};
    var network = new vis.Network(container, data, options);

    document.getElementById("search").addEventListener("input", function() {{
      var term = this.value.toLowerCase();
      var updates = [];
      nodesData.forEach(function(n) {{
        var match = term === "" || n.label.toLowerCase().includes(term) || n.id.toLowerCase().includes(term);
        updates.push({{ id: n.id, hidden: !match }});
      }});
      nodes.update(updates);
    }});
  </script>
</body>
</html>
"""
        Path(path).write_text(html, encoding="utf-8")

    def export_json(self, path: str | Path) -> None:
        """Export the graph as a JSON file."""
        Path(path).write_text(
            json.dumps(self.to_serializable(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def from_serializable(cls, data: dict[str, Any]) -> "CodeGraph":
        """Reconstruct a CodeGraph from the dict produced by *to_serializable*."""
        g = cls()
        for node_data in data.get("nodes", []):
            g.add_element(node_data["id"], node_data.get("kind", ""))
        for edge_data in data.get("edges", []):
            kind_str = edge_data.get("kind", EdgeKind.CALLS.value)
            try:
                kind = EdgeKind(kind_str)
            except ValueError:
                kind = EdgeKind.CALLS
            g.add_edge(
                GraphEdge(
                    source=edge_data["source"],
                    target=edge_data["target"],
                    kind=kind,
                )
            )
        return g

    # ------------------------------------------------------------------
    # Internal BFS helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bfs(
        graph: nx.DiGraph, start: str, max_hops: int
    ) -> list[tuple[str, int]]:
        """Single-source BFS; skip *start* from results."""
        if start not in graph:
            return []
        visited: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        while queue:
            node, depth = queue.popleft()
            if node in visited:
                continue
            visited[node] = depth
            if depth < max_hops:
                for neighbour in graph.successors(node):
                    if neighbour not in visited:
                        queue.append((neighbour, depth + 1))
        # Exclude the start node itself
        return [(n, d) for n, d in visited.items() if n != start]

    @staticmethod
    def _multi_source_bfs(
        graph: nx.DiGraph, sources: list[str], max_hops: int
    ) -> dict[str, int]:
        """Multi-source BFS; returns min distances, excludes the source nodes."""
        visited: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque()
        source_set = set(sources)
        for s in sources:
            if s in graph:
                queue.append((s, 0))
                visited[s] = 0
        while queue:
            node, depth = queue.popleft()
            if depth < max_hops:
                for neighbour in graph.successors(node):
                    if neighbour not in visited:
                        visited[neighbour] = depth + 1
                        queue.append((neighbour, depth + 1))
        return {n: d for n, d in visited.items() if n not in source_set}
