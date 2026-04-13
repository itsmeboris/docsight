"""Code dependency graph backed by networkx."""

from __future__ import annotations

from collections import deque
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
