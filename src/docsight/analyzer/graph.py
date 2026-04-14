"""Code dependency graph backed by networkx."""

from __future__ import annotations

import html as _html
import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx

from docsight.analyzer.base import EdgeKind, GraphEdge

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

        # Escape '</' to prevent script-tag breakout (XSS)
        nodes_json = json.dumps(vis_nodes).replace("</", r"<\/")
        edges_json = json.dumps(vis_edges).replace("</", r"<\/")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>docsight: Code Graph</title>
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
    <h1>docsight graph</h1>
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


# ------------------------------------------------------------------
# Semantic-zoom graph export (standalone, not a CodeGraph method)
# ------------------------------------------------------------------


def export_zoom_html(
    elements: dict[str, Any],
    edges: list[GraphEdge],
    mappings: dict[str, dict],
    state: dict[str, dict],
    output_path: str | Path,
) -> None:
    """Export a semantic-zoom graph: files -> classes -> methods.

    The generated HTML uses vis.js.  The initial view shows one node per
    file with aggregated inter-file edges.  Double-clicking a file expands
    it into its classes and module-level functions; double-clicking a class
    reveals its methods.  A small header node for each expanded file allows
    collapsing back.
    """
    last_report = state.get("last_report", {})

    # Stale / possibly-stale element sets (distinguished by doc status)
    stale_eids: set[str] = set()
    possibly_stale_eids: set[str] = set()
    for doc_data in last_report.values():
        if not isinstance(doc_data, dict):
            continue
        doc_status = doc_data.get("status", "")
        for issue in doc_data.get("issues", []):
            eid = issue.get("element_id", "") if isinstance(issue, dict) else ""
            if not eid:
                continue
            if doc_status in ("stale", "STALE"):
                stale_eids.add(eid)
            elif doc_status in ("possibly_stale", "POSSIBLY_STALE"):
                possibly_stale_eids.add(eid)

    # Documented element set
    documented_eids: set[str] = set()
    for doc_data in mappings.values():
        for ref in doc_data.get("mapped", []):
            documented_eids.add(ref.get("element_id", ""))

    # Group elements by file (track all files, including module-only ones)
    all_files: set[str] = set()
    file_elems: dict[str, list[dict]] = {}
    for eid, elem in elements.items():
        file_path = elem.file if hasattr(elem, "file") else eid.split("::")[0]
        all_files.add(file_path)
        if eid.endswith("::__module__"):
            continue
        name = elem.name if hasattr(elem, "name") else eid.split("::")[-1]
        kind = elem.kind.value if hasattr(elem, "kind") else "?"
        parent = elem.parent if hasattr(elem, "parent") else None
        file_elems.setdefault(file_path, []).append({
            "id": eid, "name": name, "kind": kind,
            "parent": parent,
            "stale": eid in stale_eids,
            "possibly_stale": eid in possibly_stale_eids,
            "documented": eid in documented_eids,
        })

    # Build structured JSON blob
    graph_data: dict[str, Any] = {"files": {}, "edges": []}
    for file_path in sorted(all_files):
        elems = file_elems.get(file_path, [])
        class_methods: dict[str, list[dict]] = {}
        class_list: list[dict] = []
        func_list: list[dict] = []
        for elem in elems:
            if elem["kind"] == "CLASS":
                class_list.append(elem)
                class_methods.setdefault(elem["id"], [])
            elif elem["kind"] == "METHOD":
                class_methods.setdefault(elem["parent"] or "", []).append(elem)
            elif elem["kind"] == "FUNCTION":
                func_list.append(elem)
        structured = []
        for cls in sorted(class_list, key=lambda x: x["name"]):
            methods = sorted(
                class_methods.get(cls["id"], []), key=lambda x: x["name"]
            )
            structured.append({**cls, "methods": methods})
        for func in sorted(func_list, key=lambda x: x["name"]):
            structured.append({**func, "methods": []})
        n_stale = sum(1 for e in elems if e["stale"])
        n_ps = sum(1 for e in elems if e.get("possibly_stale"))
        graph_data["files"][file_path] = {
            "n_elements": len(elems),
            "n_stale": n_stale,
            "has_stale": n_stale > 0,
            "has_possibly_stale": n_ps > 0,
            "elements": structured,
        }

    for edge in edges:
        graph_data["edges"].append({
            "source": edge.source, "target": edge.target,
            "kind": edge.kind.value,
        })

    n_files = len(graph_data["files"])
    n_elements = sum(f["n_elements"] for f in graph_data["files"].values())
    n_edges = len(graph_data["edges"])
    n_stale = sum(f["n_stale"] for f in graph_data["files"].values())

    # Escape '</' to prevent script-tag breakout (XSS).
    # Replace numeric placeholders FIRST, then inject JSON LAST so that
    # placeholder strings inside the JSON data are never re-processed.
    safe_json = json.dumps(graph_data).replace("</", r"<\/")
    html = (_ZOOM_TEMPLATE
            .replace("__N_FILES__", str(n_files))
            .replace("__N_ELEMENTS__", str(n_elements))
            .replace("__N_EDGES__", str(n_edges))
            .replace("__N_STALE__", str(n_stale))
            .replace("__GRAPH_DATA__", safe_json))
    Path(output_path).write_text(html, encoding="utf-8")


_ZOOM_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>docsight: Code Graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
#header{background:#161b22;padding:10px 20px;display:flex;align-items:center;gap:24px;border-bottom:1px solid #30363d;flex-wrap:wrap}
#header h1{font-size:16px;font-weight:600;white-space:nowrap}
.legend{display:flex;gap:14px;font-size:12px;align-items:center}
.legend-item{display:flex;align-items:center;gap:4px}
.dot{width:10px;height:10px;border-radius:2px;display:inline-block}
#controls{background:#161b22;padding:8px 20px;display:flex;gap:12px;align-items:center;border-bottom:1px solid #30363d;font-size:12px}
#search{background:#0d1117;color:#c9d1d9;border:1px solid #30363d;padding:5px 12px;border-radius:6px;font-size:13px;width:240px}
#search:focus{outline:none;border-color:#58a6ff}
.stat{color:#8b949e}.stat b{color:#c9d1d9}
.btn{background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px}
.btn:hover{background:#30363d}
#network{width:100%;height:calc(100vh - 90px)}
#hint{position:fixed;bottom:12px;left:50%;transform:translateX(-50%);background:#161b22;border:1px solid #30363d;padding:6px 16px;border-radius:6px;font-size:12px;color:#8b949e;pointer-events:none}
</style>
</head>
<body>
<div id="header">
  <h1>docsight graph</h1>
  <div class="legend">
    <span class="legend-item"><span class="dot" style="background:#58a6ff;border-radius:0"></span>File</span>
    <span class="legend-item"><span class="dot" style="background:#4a90d9"></span>Class</span>
    <span class="legend-item"><span class="dot" style="background:#67b7dc"></span>Method</span>
    <span class="legend-item"><span class="dot" style="background:#7ec8a0"></span>Function</span>
    <span class="legend-item"><span class="dot" style="background:#f85149"></span>Stale</span>
    <span class="legend-item"><span class="dot" style="background:#d29922"></span>Possibly stale</span>
  </div>
</div>
<div id="controls">
  <input id="search" type="text" placeholder="Search nodes..." />
  <button class="btn" id="btnCollapse">Collapse All</button>
  <span class="stat">Files: <b>__N_FILES__</b></span>
  <span class="stat">Elements: <b>__N_ELEMENTS__</b></span>
  <span class="stat">Edges: <b>__N_EDGES__</b></span>
  <span class="stat">Stale: <b>__N_STALE__</b></span>
</div>
<div id="network"></div>
<div id="hint">Double-click a node to expand &middot; Double-click header to collapse</div>
<script>
var G=__GRAPH_DATA__;
var expanded={files:{},classes:{}};

var nodes=new vis.DataSet();
var edges=new vis.DataSet();
var container=document.getElementById("network");
var network=new vis.Network(container,{nodes:nodes,edges:edges},{
  layout:{improvedLayout:false},
  physics:{
    solver:"forceAtlas2Based",
    forceAtlas2Based:{gravitationalConstant:-80,centralGravity:0.01,springLength:150,springConstant:0.02,damping:0.4},
    stabilization:{iterations:150,fit:true}
  },
  nodes:{
    borderWidth:1,
    font:{color:"#c9d1d9",size:12,face:"monospace",strokeWidth:2,strokeColor:"#0d1117"}
  },
  edges:{
    width:0.8,smooth:{type:"continuous"},color:{inherit:false}
  },
  interaction:{hover:true,tooltipDelay:150,hideEdgesOnDrag:true}
});

var STALE="#f85149",WARN="#d29922",FILE_OK="#58a6ff",CLASS_C="#4a90d9",METHOD_C="#67b7dc",FUNC_C="#7ec8a0";

function esc(s){var d=document.createElement("div");d.textContent=s;return d.innerHTML;}

function fileNode(fp,f){
  var c=f.has_stale?STALE:f.has_possibly_stale?WARN:FILE_OK;
  var short=fp.split("/").slice(-2).join("/");
  return{id:"file:"+fp,label:short,
    title:"<b>"+esc(fp)+"</b><br>"+f.n_elements+" elements"+(f.n_stale?"<br><b style='color:#f85149'>"+f.n_stale+" stale</b>":""),
    shape:"box",color:{background:c,border:"#333"},size:20,font:{size:11},
    _t:"file",_fp:fp};
}

function hdrNode(fp){
  var short=fp.split("/").pop();
  return{id:"hdr:"+fp,label:"\u{1F4C1} "+short,
    title:"Double-click to collapse <b>"+esc(fp)+"</b>",
    shape:"box",color:{background:"#21262d",border:"#30363d"},
    size:12,font:{size:9,color:"#8b949e"},
    _t:"hdr",_fp:fp};
}

function elemNode(e){
  var c=e.stale?STALE:e.possibly_stale?WARN:(e.kind==="CLASS"?CLASS_C:e.kind==="METHOD"?METHOD_C:FUNC_C);
  var shape=e.kind==="CLASS"?"diamond":"dot";
  var sz=e.kind==="CLASS"?12:8;
  var sub="";
  if(e.kind==="CLASS"&&e.methods&&e.methods.length)
    sub="<br>"+e.methods.length+" methods";
  return{id:e.id,label:e.name,
    title:"<b>"+esc(e.id)+"</b><br>Kind: "+e.kind
      +(e.stale?"<br><b style='color:#f85149'>STALE</b>":"")
      +(e.documented?"<br>Documented":"")+sub,
    shape:shape,color:{background:c,border:"#333"},size:sz,
    _t:e.kind==="CLASS"?"class":"elem",_fp:e.id.split("::")[0],_eid:e.id};
}

function rebuild(pos){
  var oldPos=network.getPositions();
  nodes.clear();edges.clear();
  var nl=[],map={};
  var fps=Object.keys(G.files).sort();
  fps.forEach(function(fp){
    var f=G.files[fp];
    if(expanded.files[fp]){
      var h=hdrNode(fp);
      var op=oldPos["file:"+fp]||pos;
      if(op){h.x=op.x;h.y=op.y;}
      nl.push(h);
      f.elements.forEach(function(e){
        var n=elemNode(e);
        if(op){n.x=op.x+(Math.random()-0.5)*80;n.y=op.y+(Math.random()-0.5)*80;}
        nl.push(n);map[e.id]=e.id;
        if(e.kind==="CLASS"&&expanded.classes[e.id]){
          (e.methods||[]).forEach(function(m){
            var mn=elemNode(m);
            if(op){mn.x=op.x+(Math.random()-0.5)*80;mn.y=op.y+(Math.random()-0.5)*80;}
            nl.push(mn);map[m.id]=m.id;
          });
        }else if(e.kind==="CLASS"){
          (e.methods||[]).forEach(function(m){map[m.id]=e.id;});
        }
      });
    }else{
      nl.push(fileNode(fp,f));
      var fid="file:"+fp;
      f.elements.forEach(function(e){
        map[e.id]=fid;
        (e.methods||[]).forEach(function(m){map[m.id]=fid;});
      });
    }
    // Map the MODULE element to the same visible node so IMPORTS edges resolve
    var modId=fp+"::__module__";
    if(!map[modId])map[modId]=expanded.files[fp]?"hdr:"+fp:"file:"+fp;
  });

  var em={};
  G.edges.forEach(function(e){
    var s=map[e.source],t=map[e.target];
    if(s&&t&&s!==t){
      var k=s+">"+t;
      if(!em[k])em[k]={from:s,to:t,n:0,inh:false};
      em[k].n++;
      if(e.kind==="INHERITS")em[k].inh=true;
    }
  });
  var el=[],ei=0;
  Object.keys(em).forEach(function(k){
    var e=em[k];
    el.push({id:ei++,from:e.from,to:e.to,arrows:"to",
      dashes:e.inh,
      color:{color:e.inh?"#c8a020":"#555"},
      width:Math.min(0.5+Math.log2(1+e.n),3),
      title:e.n+" connection(s)"});
  });
  nodes.add(nl);edges.add(el);
}

network.on("doubleClick",function(p){
  if(!p.nodes.length)return;
  var nid=p.nodes[0],n=nodes.get(nid);
  if(!n)return;
  var pos=network.getPositions([nid])[nid];
  if(n._t==="file"){
    expanded.files[n._fp]=true;
    rebuild(pos);
  }else if(n._t==="hdr"){
    delete expanded.files[n._fp];
    var pre=n._fp+"::";
    Object.keys(expanded.classes).forEach(function(c){if(c.indexOf(pre)===0)delete expanded.classes[c];});
    rebuild(pos);
  }else if(n._t==="class"){
    if(expanded.classes[n._eid])delete expanded.classes[n._eid];
    else expanded.classes[n._eid]=true;
    rebuild(pos);
  }
});

document.getElementById("btnCollapse").addEventListener("click",function(){
  expanded={files:{},classes:{}};rebuild();
});

document.getElementById("search").addEventListener("input",function(){
  var t=this.value.toLowerCase();
  if(!t){nodes.forEach(function(n){nodes.update({id:n.id,hidden:false});});return;}
  var matchFp={};
  Object.keys(G.files).forEach(function(fp){
    if(fp.toLowerCase().indexOf(t)>=0){matchFp[fp]=true;return;}
    G.files[fp].elements.forEach(function(e){
      if(e.name.toLowerCase().indexOf(t)>=0||e.id.toLowerCase().indexOf(t)>=0)matchFp[fp]=true;
      (e.methods||[]).forEach(function(m){
        if(m.name.toLowerCase().indexOf(t)>=0||m.id.toLowerCase().indexOf(t)>=0)matchFp[fp]=true;
      });
    });
  });
  nodes.forEach(function(n){
    var show=false;
    if(n._t==="file"||n._t==="hdr")show=!!matchFp[n._fp];
    else show=(n.label||"").toLowerCase().indexOf(t)>=0||(n.id||"").toLowerCase().indexOf(t)>=0||!!matchFp[n._fp];
    nodes.update({id:n.id,hidden:!show});
  });
});

rebuild();
</script>
</body>
</html>
"""
