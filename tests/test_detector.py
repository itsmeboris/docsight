"""Tests for doc_updater.staleness.detector."""

from __future__ import annotations

import pytest

from doc_updater.analyzer.base import EdgeKind, ElementKind, GraphEdge
from doc_updater.analyzer.graph import CodeGraph
from doc_updater.staleness.detector import DocStatus, StalenessDetector, StalenessIssue


def _make_element(sig_hash: str, body_hash: str) -> dict:
    """Return a plain-dict element with the given hashes."""
    return {
        "signature_hash": sig_hash,
        "body_hash": body_hash,
        "source_hash": sig_hash + body_hash,
    }


def _make_graph() -> CodeGraph:
    g = CodeGraph()
    return g


def _detector(
    elements: dict,
    mappings: dict,
    state: dict,
    graph: CodeGraph | None = None,
    **kwargs,
) -> StalenessDetector:
    if graph is None:
        graph = _make_graph()
    return StalenessDetector(elements, mappings, state, graph, **kwargs)


class TestStalenessDetectorHealthy:
    def test_healthy_no_changes(self):
        """No changes at all → HEALTHY."""
        elements = {"mod.func": _make_element("sig_aaa", "body_bbb")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ],
                "unmapped": [],
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert "docs/guide.md" in report
        assert report["docs/guide.md"]["status"] == DocStatus.HEALTHY
        assert report["docs/guide.md"]["issues"] == []

    def test_healthy_no_mapped_refs(self):
        """Doc with no mapped refs but verified → HEALTHY."""
        elements = {}
        mappings = {
            "docs/empty.md": {
                "mapped": [],
                "unmapped": [],
            }
        }
        state = {
            "verified": {
                "docs/empty.md": {
                    "element_hashes": {},
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/empty.md"]["status"] == DocStatus.HEALTHY


class TestStalenessDetectorSignature:
    def test_stale_signature_change(self):
        """Signature changed → STALE (confidence = ref_confidence * 1.0)."""
        elements = {"mod.func": _make_element("sig_NEW", "body_bbb")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_OLD",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/guide.md"]["status"] == DocStatus.STALE
        issues = report["docs/guide.md"]["issues"]
        assert any(i.change_type == "signature" for i in issues)

    @pytest.mark.parametrize("ref_confidence", [0.9, 1.0, 0.75])
    def test_stale_signature_confidence(self, ref_confidence):
        """Signature change confidence = ref_confidence * 1.0."""
        elements = {"mod.func": _make_element("sig_NEW", "body_bbb")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {
                        "element_id": "mod.func",
                        "confidence": ref_confidence,
                        "ref_type": "code",
                    }
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_OLD",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        sig_issues = [
            i
            for i in report["docs/guide.md"]["issues"]
            if i.change_type == "signature"
        ]
        assert len(sig_issues) == 1
        assert sig_issues[0].confidence == pytest.approx(ref_confidence * 1.0)


class TestStalenessDetectorBody:
    def test_stale_or_possibly_stale_body_change(self):
        """Body changed → confidence = ref_confidence * 0.8; status depends on threshold."""
        elements = {"mod.func": _make_element("sig_aaa", "body_NEW")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_OLD",
                    },
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        status = report["docs/guide.md"]["status"]
        # confidence = 0.9 * 0.8 = 0.72 >= 0.70 → STALE
        assert status in (DocStatus.STALE, DocStatus.POSSIBLY_STALE)
        body_issues = [
            i
            for i in report["docs/guide.md"]["issues"]
            if i.change_type == "body"
        ]
        assert len(body_issues) == 1
        assert body_issues[0].confidence == pytest.approx(0.9 * 0.8)

    def test_body_change_low_confidence_possibly_stale(self):
        """Body change with low ref_confidence → POSSIBLY_STALE."""
        # confidence = 0.5 * 0.8 = 0.40 < 0.70
        elements = {"mod.func": _make_element("sig_aaa", "body_NEW")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.5, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_OLD",
                    },
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/guide.md"]["status"] == DocStatus.POSSIBLY_STALE


class TestStalenessDetectorTransitive:
    def test_transitive_change_detected(self):
        """Dependency hash changed → transitive issue."""
        elements = {
            "mod.func": _make_element("sig_aaa", "body_bbb"),
            "mod.dep": _make_element("dep_NEW", "dep_body"),
        }
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 1.0, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {
                        "mod.dep": {"hash": "dep_OLD_dep_body", "hops": 1}
                    },
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        issues = report["docs/guide.md"]["issues"]
        transitive = [i for i in issues if i.change_type == "transitive"]
        assert len(transitive) == 1
        assert transitive[0].element_id == "mod.dep"
        assert transitive[0].hops == 1

    def test_transitive_confidence_decay(self):
        """Transitive confidence = base * decay^hops."""
        # base confidence = 0.90, decay=0.6, hops=1 → 0.90 * 0.6 = 0.54
        elements = {
            "mod.func": _make_element("sig_aaa", "body_bbb"),
            "mod.dep": _make_element("dep_NEW", "dep_body"),
        }
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {
                        "mod.dep": {"hash": "dep_OLD_dep_body", "hops": 1}
                    },
                }
            }
        }
        det = _detector(elements, mappings, state, decay=0.6)
        report = det.check_all()
        transitive = [
            i
            for i in report["docs/guide.md"]["issues"]
            if i.change_type == "transitive"
        ]
        assert len(transitive) == 1
        assert transitive[0].confidence == pytest.approx(0.9 * 0.6)

    def test_transitive_below_min_confidence_excluded(self):
        """Transitive issue below min_confidence is not reported."""
        # 0.9 * 0.6^3 = 0.9 * 0.216 = 0.1944 < 0.20
        elements = {
            "mod.func": _make_element("sig_aaa", "body_bbb"),
            "mod.dep": _make_element("dep_NEW", "dep_body"),
        }
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {
                        "mod.dep": {"hash": "dep_OLD_dep_body", "hops": 3}
                    },
                }
            }
        }
        det = _detector(elements, mappings, state, decay=0.6, min_confidence=0.20)
        report = det.check_all()
        issues = report["docs/guide.md"]["issues"]
        transitive = [i for i in issues if i.change_type == "transitive"]
        assert len(transitive) == 0


class TestMaxHopsEnforcement:
    """Regression: max_hops=0 must skip transitive checks entirely."""

    def test_direct_only_skips_transitive(self):
        elements = {
            "mod.func": _make_element("sig_aaa", "body_bbb"),
            "mod.dep": _make_element("dep_NEW", "dep_body"),
        }
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                        "mod.func:body": "body_bbb",
                    },
                    "dependency_hashes": {
                        "mod.dep": {"hash": "dep_OLD", "hops": 1},
                    },
                }
            }
        }
        det = _detector(elements, mappings, state, max_hops=0)
        report = det.check_all()
        issues = report["docs/guide.md"]["issues"]
        transitive = [i for i in issues if i.change_type == "transitive"]
        assert len(transitive) == 0  # max_hops=0 skips transitive


class TestStalenessDetectorUnverified:
    def test_unverified_no_state(self):
        """No verified state for doc → UNVERIFIED."""
        elements = {"mod.func": _make_element("sig_aaa", "body_bbb")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {}  # no "verified" key at all
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/guide.md"]["status"] == DocStatus.UNVERIFIED

    def test_unverified_empty_verified_dict(self):
        """verified dict exists but no entry for this doc → UNVERIFIED."""
        elements = {"mod.func": _make_element("sig_aaa", "body_bbb")}
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {"verified": {}}
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/guide.md"]["status"] == DocStatus.UNVERIFIED

    def test_unverified_has_no_issues(self):
        """UNVERIFIED docs should have an empty issues list."""
        elements = {}
        mappings = {"docs/guide.md": {"mapped": []}}
        state = {}
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/guide.md"]["issues"] == []


class TestStalenessDetectorReferenceLost:
    def test_reference_lost_element_deleted(self):
        """Element deleted from index → reference_lost issue, status STALE."""
        elements = {}  # empty — element no longer exists
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {"element_id": "mod.func", "confidence": 0.9, "ref_type": "code"}
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {
                        "mod.func:signature": "sig_aaa",
                    },
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/guide.md"]["status"] == DocStatus.STALE
        issues = report["docs/guide.md"]["issues"]
        lost = [i for i in issues if i.change_type == "reference_lost"]
        assert len(lost) == 1
        assert lost[0].element_id == "mod.func"

    def test_reference_lost_high_confidence(self):
        """reference_lost uses the ref's confidence directly."""
        elements = {}
        ref_confidence = 0.85
        mappings = {
            "docs/guide.md": {
                "mapped": [
                    {
                        "element_id": "mod.func",
                        "confidence": ref_confidence,
                        "ref_type": "code",
                    }
                ]
            }
        }
        state = {
            "verified": {
                "docs/guide.md": {
                    "element_hashes": {},
                    "dependency_hashes": {},
                }
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        lost = [
            i
            for i in report["docs/guide.md"]["issues"]
            if i.change_type == "reference_lost"
        ]
        assert lost[0].confidence == pytest.approx(ref_confidence)


class TestStalenessDetectorMultipleDocs:
    def test_multiple_docs_independent(self):
        """Each doc is checked independently."""
        elements = {
            "mod.a": _make_element("sig_a", "body_a"),
            "mod.b": _make_element("sig_b_NEW", "body_b"),
        }
        mappings = {
            "docs/a.md": {
                "mapped": [
                    {"element_id": "mod.a", "confidence": 0.9, "ref_type": "code"}
                ]
            },
            "docs/b.md": {
                "mapped": [
                    {"element_id": "mod.b", "confidence": 0.9, "ref_type": "code"}
                ]
            },
        }
        state = {
            "verified": {
                "docs/a.md": {
                    "element_hashes": {
                        "mod.a:signature": "sig_a",
                        "mod.a:body": "body_a",
                    },
                    "dependency_hashes": {},
                },
                "docs/b.md": {
                    "element_hashes": {
                        "mod.b:signature": "sig_b_OLD",
                        "mod.b:body": "body_b",
                    },
                    "dependency_hashes": {},
                },
            }
        }
        det = _detector(elements, mappings, state)
        report = det.check_all()
        assert report["docs/a.md"]["status"] == DocStatus.HEALTHY
        assert report["docs/b.md"]["status"] == DocStatus.STALE
