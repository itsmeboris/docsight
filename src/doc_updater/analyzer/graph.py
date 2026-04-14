"""Code dependency graph backed by networkx."""

from __future__ import annotations

import html as _html
import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx

from doc_updater.analyzer.base import EdgeKind, GraphEdge

# Node shape/colour constants for HTML export
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
    "MODULE": "#B07CC6",
}
_KIND_SIZE: dict[str, int] = {
    "FUNCTION": 4,
    "METHOD": 3,
    "CLASS": 8,
    "MODULE": 10,
}
_STALE_COLOR = "#FF4444"


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
    ) -> None:
        """Export the graph as an interactive HTML file using vis.js.

        Parameters
        ----------
        path:
            Destination file path for the HTML output.
        stale_elements:
            Optional list of element IDs that should be highlighted red.
        """
        stale_set: set[str] = set(stale_elements or [])

        # Build vis.js node / edge structures
        vis_nodes: list[dict[str, Any]] = []
        vis_edges: list[dict[str, Any]] = []

        for node_id in self._g.nodes:
            kind = self._g.nodes[node_id].get("kind", "")
            is_stale = node_id in stale_set
            color = _STALE_COLOR if is_stale else _KIND_COLOR.get(kind, "#A0A0A0")
            shape = _KIND_SHAPE.get(kind, "ellipse")
            # Short label: last component of element_id
            label = node_id.split("::")[-1] if "::" in node_id else node_id
            safe_id = _html.escape(node_id)
            safe_kind = _html.escape(kind)
            safe_label = _html.escape(label)
            size = _KIND_SIZE.get(kind, 8)
            vis_nodes.append(
                {
                    "id": node_id,
                    "label": safe_label,
                    "title": f"<b>{safe_id}</b><br>Kind: {safe_kind}"
                    + (" <b>[STALE]</b>" if is_stale else ""),
                    "color": {"background": color, "border": "#333333"},
                    "shape": shape,
                    "size": size,
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
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      background: #0D1117;
      color: #C9D1D9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    }}
    #header {{
      background: #161B22;
      padding: 10px 20px;
      display: flex;
      align-items: center;
      gap: 24px;
      border-bottom: 1px solid #30363D;
      flex-wrap: wrap;
    }}
    #header h1 {{ font-size: 16px; font-weight: 600; white-space: nowrap; }}
    .legend {{
      display: flex;
      gap: 14px;
      font-size: 12px;
      align-items: center;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}
    .dot {{
      width: 10px;
      height: 10px;
      border-radius: 2px;
      display: inline-block;
    }}
    #controls {{
      background: #161B22;
      padding: 8px 20px;
      display: flex;
      gap: 12px;
      align-items: center;
      border-bottom: 1px solid #30363D;
      font-size: 12px;
    }}
    #search {{
      background: #0D1117;
      color: #C9D1D9;
      border: 1px solid #30363D;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 13px;
      width: 240px;
    }}
    #search:focus {{ outline: none; border-color: #58A6FF; }}
    .stat {{ color: #8B949E; }}
    .stat b {{ color: #C9D1D9; }}
    #network {{
      width: 100%;
      height: calc(100vh - 90px);
    }}
  </style>
</head>
<body>
  <div id="header">
    <h1>doc-updater graph</h1>
    <div class="legend">
      <span class="legend-item"><span class="dot" style="background:#4A90D9"></span>Class</span>
      <span class="legend-item"><span class="dot" style="background:#67B7DC"></span>Method</span>
      <span class="legend-item"><span class="dot" style="background:#7EC8A0"></span>Function</span>
      <span class="legend-item"><span class="dot" style="background:#B07CC6"></span>Module</span>
      <span class="legend-item"><span class="dot" style="background:#FF4444"></span>Stale</span>
    </div>
  </div>
  <div id="controls">
    <input id="search" type="text" placeholder="Search nodes..." />
    <span class="stat">Nodes: <b>{n_nodes}</b></span>
    <span class="stat">Edges: <b>{n_edges}</b></span>
    <span class="stat">Stale: <b>{n_stale}</b></span>
  </div>
  <div id="network"></div>
  <script>
    var nodesData = {nodes_json};
    var edgesData = {edges_json};

    var nodes = new vis.DataSet(nodesData);
    var edges = new vis.DataSet(edgesData);
    var container = document.getElementById("network");
    var data = {{ nodes: nodes, edges: edges }};
    var options = {{
      layout: {{
        improvedLayout: false
      }},
      physics: {{
        solver: "forceAtlas2Based",
        forceAtlas2Based: {{
          gravitationalConstant: -120,
          centralGravity: 0.005,
          springLength: 200,
          springConstant: 0.015,
          damping: 0.4
        }},
        stabilization: {{
          iterations: 200,
          fit: true
        }}
      }},
      nodes: {{
        borderWidth: 1,
        font: {{
          color: "#C9D1D9",
          size: 10,
          face: "monospace",
          strokeWidth: 2,
          strokeColor: "#0D1117"
        }},
        scaling: {{
          label: {{
            enabled: true,
            min: 6,
            max: 12,
            drawThreshold: 12
          }}
        }}
      }},
      edges: {{
        width: 0.8,
        smooth: {{ type: "continuous" }},
        color: {{ inherit: false }}
      }},
      interaction: {{
        hover: true,
        tooltipDelay: 150,
        hideEdgesOnDrag: true,
        hideEdgesOnZoom: true
      }}
    }};
    var network = new vis.Network(container, data, options);

    // Search: filter nodes by name
    document.getElementById("search").addEventListener("input", function() {{
      var term = this.value.toLowerCase();
      var updates = [];
      nodesData.forEach(function(n) {{
        var match = term === ""
          || n.label.toLowerCase().includes(term)
          || n.id.toLowerCase().includes(term);
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
