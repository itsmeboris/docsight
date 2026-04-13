"""Tests for doc_updater.staleness.reporter."""

from __future__ import annotations

import json

import pytest

from doc_updater.staleness.detector import DocStatus, StalenessIssue
from doc_updater.staleness.reporter import has_stale, summarize, to_json


def _make_report(
    statuses: list[DocStatus],
    with_issues: bool = False,
) -> dict[str, dict]:
    """Build a minimal report dict from a list of statuses."""
    report: dict[str, dict] = {}
    for i, status in enumerate(statuses):
        issues = []
        if with_issues and status in (DocStatus.STALE, DocStatus.POSSIBLY_STALE):
            issues = [
                StalenessIssue(
                    element_id="mod.func",
                    change_type="signature",
                    confidence=0.9,
                )
            ]
        report[f"docs/doc{i}.md"] = {"status": status, "issues": issues}
    return report


class TestSummarize:
    @pytest.mark.parametrize(
        "statuses, expected",
        [
            (
                [DocStatus.HEALTHY, DocStatus.STALE, DocStatus.POSSIBLY_STALE, DocStatus.UNVERIFIED],
                {"total": 4, "healthy": 1, "stale": 1, "possibly_stale": 1, "unverified": 1},
            ),
            (
                [DocStatus.HEALTHY, DocStatus.HEALTHY],
                {"total": 2, "healthy": 2, "stale": 0, "possibly_stale": 0, "unverified": 0},
            ),
            (
                [],
                {"total": 0, "healthy": 0, "stale": 0, "possibly_stale": 0, "unverified": 0},
            ),
            (
                [DocStatus.STALE, DocStatus.STALE],
                {"total": 2, "healthy": 0, "stale": 2, "possibly_stale": 0, "unverified": 0},
            ),
        ],
    )
    def test_summary_counts(self, statuses, expected):
        report = _make_report(statuses)
        result = summarize(report)
        assert result == expected

    def test_summary_with_string_status(self):
        """summarize handles string status values (from deserialized JSON)."""
        report = {
            "docs/doc.md": {"status": "stale", "issues": []},
            "docs/doc2.md": {"status": "healthy", "issues": []},
        }
        result = summarize(report)
        assert result["stale"] == 1
        assert result["healthy"] == 1


class TestHasStale:
    @pytest.mark.parametrize(
        "statuses, expected_has_stale",
        [
            ([DocStatus.HEALTHY], False),
            ([DocStatus.STALE], True),
            ([DocStatus.POSSIBLY_STALE], True),
            ([DocStatus.UNVERIFIED], False),
            ([DocStatus.HEALTHY, DocStatus.STALE], True),
            ([], False),
        ],
    )
    def test_has_stale(self, statuses, expected_has_stale):
        report = _make_report(statuses)
        assert has_stale(report) == expected_has_stale

    def test_has_stale_with_string_status(self):
        """has_stale handles string status values."""
        report = {
            "docs/doc.md": {"status": "stale", "issues": []},
        }
        assert has_stale(report) is True


class TestToJson:
    def test_json_output_is_valid_json(self):
        report = _make_report([DocStatus.HEALTHY, DocStatus.STALE], with_issues=True)
        result = to_json(report)
        parsed = json.loads(result)
        assert "summary" in parsed
        assert "docs" in parsed

    def test_json_output_summary_counts(self):
        report = _make_report([DocStatus.HEALTHY, DocStatus.STALE])
        result = to_json(report)
        parsed = json.loads(result)
        assert parsed["summary"]["total"] == 2
        assert parsed["summary"]["healthy"] == 1
        assert parsed["summary"]["stale"] == 1

    def test_json_output_doc_status(self):
        report = _make_report([DocStatus.STALE], with_issues=True)
        result = to_json(report)
        parsed = json.loads(result)
        doc_key = list(parsed["docs"].keys())[0]
        assert parsed["docs"][doc_key]["status"] == "stale"

    def test_json_output_issues_serialized(self):
        issues = [
            StalenessIssue(
                element_id="mod.func",
                change_type="signature",
                confidence=0.9,
                hops=0,
                detail="sig changed",
            )
        ]
        report = {
            "docs/guide.md": {"status": DocStatus.STALE, "issues": issues}
        }
        result = to_json(report)
        parsed = json.loads(result)
        doc = parsed["docs"]["docs/guide.md"]
        assert len(doc["issues"]) == 1
        issue = doc["issues"][0]
        assert issue["element_id"] == "mod.func"
        assert issue["change_type"] == "signature"
        assert issue["confidence"] == pytest.approx(0.9)
        assert issue["hops"] == 0
        assert issue["detail"] == "sig changed"

    def test_json_empty_report(self):
        report: dict = {}
        result = to_json(report)
        parsed = json.loads(result)
        assert parsed["summary"]["total"] == 0
        assert parsed["docs"] == {}
