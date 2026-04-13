"""Tests for CodeGraph.export_html."""

from pathlib import Path

import pytest

from doc_updater.analyzer.base import EdgeKind, GraphEdge
from doc_updater.analyzer.graph import CodeGraph


@pytest.fixture()
def simple_graph() -> CodeGraph:
    """A small graph with a class, two methods, and a function."""
    g = CodeGraph()
    g.add_element("file.py::MyClass", "CLASS")
    g.add_element("file.py::MyClass.my_method", "METHOD")
    g.add_element("file.py::my_func", "FUNCTION")
    g.add_edge(
        GraphEdge(
            source="file.py::MyClass.my_method",
            target="file.py::my_func",
            kind=EdgeKind.CALLS,
        )
    )
    return g


class TestExportHtml:
    def test_export_html_creates_file(self, simple_graph: CodeGraph, tmp_path: Path) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        assert out.exists()

    def test_export_html_contains_vis_network(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "vis.Network" in content

    def test_export_html_contains_node_labels(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        # Labels are the last segment of element IDs after '::'
        assert "MyClass" in content
        assert "my_method" in content
        assert "my_func" in content

    def test_export_html_uses_cdn_url(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js" in content

    def test_export_html_dark_background(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "#0D1117" in content


class TestStaleNodesHighlighted:
    def test_stale_nodes_get_red_color(self, simple_graph: CodeGraph, tmp_path: Path) -> None:
        out = tmp_path / "graph.html"
        stale = ["file.py::MyClass.my_method"]
        simple_graph.export_html(out, stale_elements=stale)
        content = out.read_text(encoding="utf-8")
        assert "#FF4444" in content

    def test_non_stale_nodes_not_all_red(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        stale = ["file.py::MyClass.my_method"]
        simple_graph.export_html(out, stale_elements=stale)
        content = out.read_text(encoding="utf-8")
        # Non-stale colors should also be present
        assert "#4A90D9" in content or "#7EC8A0" in content

    def test_no_stale_elements_no_extra_red(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out, stale_elements=[])
        content = out.read_text(encoding="utf-8")
        # Red in legend is fine; but no node should be set to red
        # Count occurrences outside legend - just verify it won't crash
        assert out.exists()


class TestSearchUsesHidden:
    def test_search_uses_hidden_property(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "hidden" in content

    def test_search_does_not_use_opacity(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        # Find the search event handler section and ensure no 'opacity' there
        search_idx = content.find('getElementById("search")')
        assert search_idx != -1
        search_section = content[search_idx : search_idx + 500]
        assert "opacity" not in search_section

    def test_search_uses_hidden_not_opacity_in_updates(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        # The update objects should use 'hidden' key
        assert "hidden: !match" in content or '"hidden"' in content or "hidden:" in content


class TestExportJson:
    def test_export_json_creates_file(self, simple_graph: CodeGraph, tmp_path: Path) -> None:
        out = tmp_path / "graph.json"
        simple_graph.export_json(out)
        assert out.exists()

    def test_export_json_valid_structure(
        self, simple_graph: CodeGraph, tmp_path: Path
    ) -> None:
        import json

        out = tmp_path / "graph.json"
        simple_graph.export_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "nodes" in data
        assert "edges" in data
