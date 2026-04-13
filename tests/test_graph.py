"""Tests for the CodeGraph dependency graph."""

from __future__ import annotations

import pytest

from doc_updater.analyzer.base import EdgeKind, GraphEdge
from doc_updater.analyzer.graph import CodeGraph


@pytest.fixture
def chain_graph():
    """Build a chain graph: A->B->C->D, A->E."""
    g = CodeGraph()
    for node in ["A", "B", "C", "D", "E"]:
        g.add_element(node, "FUNCTION")
    for src, tgt in [("A", "B"), ("B", "C"), ("C", "D"), ("A", "E")]:
        g.add_edge(GraphEdge(source=src, target=tgt, kind=EdgeKind.CALLS))
    return g


class TestEmptyGraph:
    def test_dependencies_on_empty(self):
        g = CodeGraph()
        assert g.get_dependencies("X") == []

    def test_dependents_on_empty(self):
        g = CodeGraph()
        assert g.get_dependents("X") == []

    def test_impact_radius_empty(self):
        g = CodeGraph()
        assert g.impact_radius(["X"]) == {}

    def test_dependency_closure_empty(self):
        g = CodeGraph()
        assert g.dependency_closure(["X"]) == {}


class TestGetDependencies:
    def test_direct_deps_of_a(self, chain_graph):
        deps = dict(chain_graph.get_dependencies("A", max_hops=1))
        assert deps == {"B": 1, "E": 1}

    def test_transitive_deps_of_a(self, chain_graph):
        deps = dict(chain_graph.get_dependencies("A", max_hops=3))
        assert "B" in deps and "C" in deps and "D" in deps and "E" in deps
        assert deps["B"] == 1
        assert deps["C"] == 2
        assert deps["D"] == 3

    def test_max_hops_limits_depth(self, chain_graph):
        deps = dict(chain_graph.get_dependencies("A", max_hops=2))
        assert "D" not in deps  # D is 3 hops away

    def test_leaf_has_no_deps(self, chain_graph):
        assert chain_graph.get_dependencies("D") == []


class TestGetDependents:
    def test_direct_dependents_of_b(self, chain_graph):
        deps = dict(chain_graph.get_dependents("B", max_hops=1))
        assert deps == {"A": 1}

    def test_transitive_dependents_of_d(self, chain_graph):
        deps = dict(chain_graph.get_dependents("D", max_hops=3))
        assert "C" in deps and "B" in deps and "A" in deps
        assert deps["C"] == 1
        assert deps["B"] == 2
        assert deps["A"] == 3

    def test_root_has_no_dependents(self, chain_graph):
        assert chain_graph.get_dependents("A") == []


class TestImpactRadius:
    def test_changing_b_impacts_a(self, chain_graph):
        result = chain_graph.impact_radius(["B"], max_hops=3)
        assert "A" in result

    def test_changing_d_impacts_chain(self, chain_graph):
        result = chain_graph.impact_radius(["D"], max_hops=3)
        assert "C" in result
        assert "B" in result
        assert "A" in result

    def test_changing_leaf_e(self, chain_graph):
        result = chain_graph.impact_radius(["E"], max_hops=3)
        assert "A" in result

    def test_changed_elements_not_in_result(self, chain_graph):
        """The changed elements themselves should not appear in the result."""
        result = chain_graph.impact_radius(["D"], max_hops=3)
        assert "D" not in result

    def test_multiple_changed_elements(self, chain_graph):
        result = chain_graph.impact_radius(["D", "E"], max_hops=3)
        assert "A" in result

    def test_hops_value_is_minimum_distance(self, chain_graph):
        result = chain_graph.impact_radius(["D"], max_hops=3)
        assert result["C"] == 1
        assert result["B"] == 2
        assert result["A"] == 3


class TestDependencyClosure:
    def test_closure_of_a(self, chain_graph):
        result = chain_graph.dependency_closure(["A"], max_hops=3)
        assert "B" in result and "C" in result and "D" in result and "E" in result

    def test_closure_excludes_source(self, chain_graph):
        result = chain_graph.dependency_closure(["A"], max_hops=3)
        assert "A" not in result

    def test_closure_respects_max_hops(self, chain_graph):
        result = chain_graph.dependency_closure(["A"], max_hops=2)
        assert "D" not in result


class TestSerializationRoundtrip:
    def test_nodes_and_edges_survive_roundtrip(self, chain_graph):
        data = chain_graph.to_serializable()
        g2 = CodeGraph.from_serializable(data)
        # Check same dependencies
        deps_orig = set(n for n, _ in chain_graph.get_dependencies("A", max_hops=3))
        deps_new = set(n for n, _ in g2.get_dependencies("A", max_hops=3))
        assert deps_orig == deps_new

    def test_empty_graph_serialization(self):
        g = CodeGraph()
        data = g.to_serializable()
        g2 = CodeGraph.from_serializable(data)
        assert g2.get_dependencies("X") == []

    def test_serializable_format(self, chain_graph):
        data = chain_graph.to_serializable()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    def test_unknown_edge_kind_defaults_to_calls(self):
        """from_serializable falls back to CALLS for unknown edge kinds."""
        data = {
            "nodes": [{"id": "X", "kind": "FUNCTION"}, {"id": "Y", "kind": "FUNCTION"}],
            "edges": [{"source": "X", "target": "Y", "kind": "UNKNOWN_KIND"}],
        }
        g = CodeGraph.from_serializable(data)
        # Edge should exist with CALLS kind (fallback)
        assert g.get_dependencies("X") != []


class TestAddEdgeAutoCreatesNodes:
    def test_add_edge_without_prior_add_element(self):
        """add_edge should auto-create nodes that don't exist yet."""
        g = CodeGraph()
        g.add_edge(GraphEdge(source="P", target="Q", kind=EdgeKind.CALLS))
        deps = dict(g.get_dependencies("P"))
        assert "Q" in deps


class TestBfsRevisitProtection:
    def test_diamond_dependency_single_hop_count(self):
        """In a diamond A->B, A->C, B->D, C->D, D should appear once."""
        g = CodeGraph()
        for n in ["A", "B", "C", "D"]:
            g.add_element(n, "FUNCTION")
        for src, tgt in [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]:
            g.add_edge(GraphEdge(source=src, target=tgt, kind=EdgeKind.CALLS))
        deps = dict(g.get_dependencies("A", max_hops=3))
        # D should be reachable and appear only once (at hop 2)
        assert deps["D"] == 2
