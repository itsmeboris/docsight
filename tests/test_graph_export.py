"""Tests for CodeGraph.export_html and export_zoom_html."""

import pytest

from doc_updater.analyzer.base import (
    CodeElement,
    EdgeKind,
    ElementKind,
    GraphEdge,
)
from doc_updater.analyzer.graph import CodeGraph, export_zoom_html


@pytest.fixture()
def simple_graph() -> CodeGraph:
    """A small graph with a class, two methods, and a function."""
    graph = CodeGraph()
    graph.add_element("file.py::MyClass", "CLASS")
    graph.add_element("file.py::MyClass.my_method", "METHOD")
    graph.add_element("file.py::my_func", "FUNCTION")
    graph.add_edge(
        GraphEdge(
            source="file.py::MyClass.my_method",
            target="file.py::my_func",
            kind=EdgeKind.CALLS,
        )
    )
    return graph


class TestExportHtml:
    """Tests for the flat vis.js HTML export."""

    def test_export_html_creates_file(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """export_html creates a file on disk."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        assert out.exists()

    def test_export_html_contains_vis_network(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Exported HTML contains a vis.Network call."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "vis.Network" in content

    def test_export_html_contains_node_labels(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Node labels appear in the HTML output."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "MyClass" in content
        assert "my_method" in content
        assert "my_func" in content

    def test_export_html_uses_cdn_url(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """HTML includes the vis.js CDN script tag."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js" in content

    def test_export_html_dark_background(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """HTML uses the dark theme background colour."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "#0D1117" in content


class TestStaleNodesHighlighted:
    """Tests for stale node highlighting in the flat export."""

    def test_stale_nodes_get_red_color(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Stale nodes are rendered with the red stale colour."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out, stale_elements=["file.py::MyClass.my_method"])
        content = out.read_text(encoding="utf-8")
        assert "#FF4444" in content

    def test_non_stale_nodes_not_all_red(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Non-stale colour codes are still present when some nodes are stale."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out, stale_elements=["file.py::MyClass.my_method"])
        content = out.read_text(encoding="utf-8")
        assert "#4A90D9" in content or "#7EC8A0" in content

    def test_no_stale_elements_no_crash(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Passing an empty stale list does not crash."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out, stale_elements=[])
        assert out.exists()


class TestSearchUsesHidden:
    """Tests for the search/filter behaviour in the flat export."""

    def test_search_uses_hidden_property(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Search handler uses the 'hidden' node property."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "hidden" in content

    def test_search_does_not_use_opacity(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Search handler does not use opacity (it should use hidden)."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        search_idx = content.find('getElementById("search")')
        assert search_idx != -1
        search_section = content[search_idx : search_idx + 500]
        assert "opacity" not in search_section

    def test_search_uses_hidden_in_updates(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Update objects use the 'hidden' key, not 'opacity'."""
        out = tmp_path / "graph.html"
        simple_graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "hidden: !match" in content or '"hidden"' in content or "hidden:" in content


class TestHtmlEscaping:
    """Regression test: HTML injection in tooltips must be escaped."""

    def test_tooltip_escapes_html(self, tmp_path):
        """Malicious element IDs are HTML-escaped in tooltips."""
        graph = CodeGraph()
        malicious_id = '<img src=x onerror=alert(1)>'
        graph.add_element(malicious_id, "function")
        out = tmp_path / "graph.html"
        graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        assert "&lt;img" in content


class TestExportJson:
    """Tests for the JSON graph export."""

    def test_export_json_creates_file(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """export_json creates a file on disk."""
        out = tmp_path / "graph.json"
        simple_graph.export_json(out)
        assert out.exists()

    def test_export_json_valid_structure(self, simple_graph, tmp_path):  # pylint: disable=redefined-outer-name
        """Exported JSON has 'nodes' and 'edges' keys."""
        import json

        out = tmp_path / "graph.json"
        simple_graph.export_json(out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "nodes" in data
        assert "edges" in data


# ---------------------------------------------------------------------------
# Semantic zoom export
# ---------------------------------------------------------------------------


def _make_element(eid, kind, name, parent=None):
    """Helper to build a CodeElement for zoom tests."""
    return CodeElement(
        element_id=eid, kind=kind, file=eid.split("::")[0], name=name,
        qualified_name=name, lineno=1, end_lineno=2,
        signature_hash="sig", body_hash="body", source_hash="src",
        parameters=[], return_annotation=None, parent=parent,
        bases=[], methods=[], raw_calls=[], docstring_summary=None,
    )


class TestExportZoomHtml:
    """Tests for the semantic-zoom graph export."""

    def test_creates_file(self, tmp_path):
        """export_zoom_html creates an HTML file."""
        elements = {
            "a.py::Foo": _make_element("a.py::Foo", ElementKind.CLASS, "Foo"),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        assert out.exists()

    def test_contains_file_and_element_data(self, tmp_path):
        """Output HTML contains embedded file paths and element names."""
        elements = {
            "a.py::Foo": _make_element("a.py::Foo", ElementKind.CLASS, "Foo"),
            "a.py::Foo.bar": _make_element(
                "a.py::Foo.bar", ElementKind.METHOD, "bar", parent="a.py::Foo"
            ),
            "b.py::helper": _make_element(
                "b.py::helper", ElementKind.FUNCTION, "helper"
            ),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        assert "a.py" in content
        assert "b.py" in content
        assert "Foo" in content
        assert "bar" in content
        assert "helper" in content

    def test_edges_embedded(self, tmp_path):
        """Edge data is included in the output."""
        elements = {
            "a.py::f": _make_element("a.py::f", ElementKind.FUNCTION, "f"),
            "b.py::g": _make_element("b.py::g", ElementKind.FUNCTION, "g"),
        }
        edge = GraphEdge(source="a.py::f", target="b.py::g", kind=EdgeKind.CALLS)
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [edge], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        assert "CALLS" in content

    def test_stale_elements_flagged(self, tmp_path):
        """Elements from truly stale docs have stale:true in the data."""
        elements = {
            "a.py::f": _make_element("a.py::f", ElementKind.FUNCTION, "f"),
        }
        state = {
            "last_report": {
                "doc.md": {
                    "status": "stale",
                    "issues": [{"element_id": "a.py::f", "change_type": "signature",
                                "confidence": 0.9, "hops": 0, "detail": "changed"}],
                }
            }
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, state, out)
        content = out.read_text(encoding="utf-8")
        assert '"stale": true' in content or '"stale":true' in content

    def test_possibly_stale_not_labelled_stale(self, tmp_path):
        """Elements from possibly_stale docs must NOT have stale:true."""
        import json as _json

        elements = {
            "a.py::f": _make_element("a.py::f", ElementKind.FUNCTION, "f"),
        }
        state = {
            "last_report": {
                "doc.md": {
                    "status": "possibly_stale",
                    "issues": [{"element_id": "a.py::f", "change_type": "transitive",
                                "confidence": 0.5, "hops": 1, "detail": "dep changed"}],
                }
            }
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, state, out)
        content = out.read_text(encoding="utf-8")
        start = content.index("var G=") + len("var G=")
        end = content.index(";\nvar expanded")
        data = _json.loads(content[start:end])
        elem = data["files"]["a.py"]["elements"][0]
        assert elem["stale"] is False
        assert elem["possibly_stale"] is True

    def test_module_only_file_not_dropped(self, tmp_path):
        """Files with only a MODULE element still appear as file nodes."""
        import json as _json

        elements = {
            "init.py::__module__": _make_element(
                "init.py::__module__", ElementKind.MODULE, "__module__"
            ),
            "a.py::f": _make_element("a.py::f", ElementKind.FUNCTION, "f"),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        start = content.index("var G=") + len("var G=")
        end = content.index(";\nvar expanded")
        data = _json.loads(content[start:end])
        assert "init.py" in data["files"]
        assert "a.py" in data["files"]

    def test_methods_nested_under_class(self, tmp_path):
        """Methods appear in the methods array of their parent class."""
        import json as _json

        elements = {
            "a.py::C": _make_element("a.py::C", ElementKind.CLASS, "C"),
            "a.py::C.m": _make_element(
                "a.py::C.m", ElementKind.METHOD, "m", parent="a.py::C"
            ),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        start = content.index("var G=") + len("var G=")
        end = content.index(";\nvar expanded")
        data = _json.loads(content[start:end])
        file_data = data["files"]["a.py"]
        cls = file_data["elements"][0]
        assert cls["name"] == "C"
        assert len(cls["methods"]) == 1
        assert cls["methods"][0]["name"] == "m"

    def test_has_zoom_ui_elements(self, tmp_path):
        """Output contains zoom UI: collapse button, double-click handler."""
        elements = {
            "a.py::f": _make_element("a.py::f", ElementKind.FUNCTION, "f"),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        assert "Collapse All" in content
        assert "doubleClick" in content
        assert "vis.Network" in content

    def test_script_tag_in_name_escaped(self, tmp_path):
        """Element names containing </script> must not break the HTML."""
        elements = {
            "a.py::bad</script>": _make_element(
                "a.py::bad</script>", ElementKind.FUNCTION, "bad</script>"
            ),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        # Raw '</script>' must NOT appear inside the <script> block
        script_start = content.index("<script>") + len("<script>")
        script_end = content.rindex("</script>")
        script_body = content[script_start:script_end]
        assert "</script>" not in script_body

    def test_placeholder_in_name_not_reprocessed(self, tmp_path):
        """Element names containing placeholder strings must not be substituted."""
        elements = {
            "a.py::__N_FILES__": _make_element(
                "a.py::__N_FILES__", ElementKind.FUNCTION, "__N_FILES__"
            ),
        }
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        # The literal string __N_FILES__ must survive in the JSON data
        assert "__N_FILES__" in content

    def test_flat_export_escapes_script_tag(self, tmp_path):
        """Flat export also escapes </script> in JSON."""
        graph = CodeGraph()
        graph.add_element("a.py::bad</script>", "FUNCTION")
        out = tmp_path / "graph.html"
        graph.export_html(out)
        content = out.read_text(encoding="utf-8")
        script_start = content.index("<script>") + len("<script>")
        script_end = content.rindex("</script>")
        script_body = content[script_start:script_end]
        assert "</script>" not in script_body

    def test_module_edges_resolve_to_file_node(self, tmp_path):
        """Edges targeting MODULE elements are mapped to their file node."""
        elements = {
            "a.py::f": _make_element("a.py::f", ElementKind.FUNCTION, "f"),
            "b.py::__module__": _make_element(
                "b.py::__module__", ElementKind.MODULE, "__module__"
            ),
        }
        edge = GraphEdge(source="a.py::f", target="b.py::__module__", kind=EdgeKind.IMPORTS)
        out = tmp_path / "zoom.html"
        export_zoom_html(elements, [edge], {}, {}, out)
        content = out.read_text(encoding="utf-8")
        # The JS maps MODULE IDs to file nodes; the edge data must be present
        assert "IMPORTS" in content
        # The JS module-mapping line must exist
        assert '+"::__module__"' in content
