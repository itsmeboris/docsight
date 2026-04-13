"""Staleness detection logic for doc-updater."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DocStatus(Enum):
    """Status of a documentation file with respect to code freshness."""

    HEALTHY = "healthy"
    STALE = "stale"
    POSSIBLY_STALE = "possibly_stale"
    UNVERIFIED = "unverified"


@dataclass
class StalenessIssue:
    """A single staleness issue detected for a documentation reference."""

    element_id: str
    change_type: str  # "signature", "body", "transitive", "reference_lost"
    confidence: float
    hops: int = 0
    detail: str = ""


class StalenessDetector:
    """Detect stale documentation by comparing current code to verified state."""

    def __init__(
        self,
        elements: dict[str, Any],
        mappings: dict[str, dict],
        state: dict[str, Any],
        graph: Any,
        decay: float = 0.6,
        max_hops: int = 3,
        min_confidence: float = 0.20,
    ) -> None:
        self._elements = elements
        self._mappings = mappings
        self._state = state
        self._graph = graph
        self._decay = decay
        self._max_hops = max_hops
        self._min_confidence = min_confidence

    def _get_hash(self, element: Any, hash_type: str) -> str | None:
        """Extract a hash from either a CodeElement object or a plain dict."""
        if isinstance(element, dict):
            return element.get(hash_type)
        return getattr(element, hash_type, None)

    def check_all(self) -> dict[str, dict]:
        """Check all documented files and return a staleness report.

        Returns:
            dict mapping doc_path -> {"status": DocStatus, "issues": list[StalenessIssue]}
        """
        verified_state: dict[str, dict] = self._state.get("verified", {})
        report: dict[str, dict] = {}

        for doc_path, doc_data in self._mappings.items():
            mapped_refs: list[dict] = doc_data.get("mapped", [])
            doc_verified = verified_state.get(doc_path)

            if doc_verified is None:
                report[doc_path] = {
                    "status": DocStatus.UNVERIFIED,
                    "issues": [],
                }
                continue

            element_hashes: dict[str, str] = doc_verified.get("element_hashes", {})
            dependency_hashes: dict[str, str] = doc_verified.get(
                "dependency_hashes", {}
            )

            issues: list[StalenessIssue] = []

            for ref in mapped_refs:
                element_id: str = ref.get("element_id", "")
                ref_confidence: float = ref.get("confidence", 1.0)

                # Check if element still exists
                if element_id not in self._elements:
                    issues.append(
                        StalenessIssue(
                            element_id=element_id,
                            change_type="reference_lost",
                            confidence=ref_confidence,
                            hops=0,
                            detail=f"Element '{element_id}' no longer exists in the index",
                        )
                    )
                    continue

                current_element = self._elements[element_id]

                # Check signature hash
                verified_sig = element_hashes.get(f"{element_id}:signature")
                current_sig = self._get_hash(current_element, "signature_hash")
                if verified_sig is not None and current_sig is not None:
                    if verified_sig != current_sig:
                        issues.append(
                            StalenessIssue(
                                element_id=element_id,
                                change_type="signature",
                                confidence=ref_confidence * 1.0,
                                hops=0,
                                detail=f"Signature of '{element_id}' has changed",
                            )
                        )

                # Check body hash
                verified_body = element_hashes.get(f"{element_id}:body")
                current_body = self._get_hash(current_element, "body_hash")
                if verified_body is not None and current_body is not None:
                    if verified_body != current_body:
                        issues.append(
                            StalenessIssue(
                                element_id=element_id,
                                change_type="body",
                                confidence=ref_confidence * 0.8,
                                hops=0,
                                detail=f"Body of '{element_id}' has changed",
                            )
                        )

            # Check transitive changes via dependency_hashes
            # dependency_hashes maps dep_element_id -> verified_hash (with hops embedded)
            # Respect max_hops: skip deps beyond the configured limit
            if self._max_hops <= 0:
                # direct-only mode: skip transitive checks entirely
                pass
            for dep_id, dep_info in (dependency_hashes.items() if self._max_hops > 0 else []):
                # dep_info can be a dict with "hash" and "hops", or just a string hash
                if isinstance(dep_info, dict):
                    verified_dep_hash = dep_info.get("hash")
                    hops = dep_info.get("hops", 1)
                else:
                    verified_dep_hash = dep_info
                    hops = 1

                # Skip dependencies beyond max_hops
                if hops > self._max_hops:
                    continue

                if dep_id not in self._elements:
                    continue

                current_dep_element = self._elements[dep_id]
                current_dep_hash = self._get_hash(current_dep_element, "source_hash")
                if current_dep_hash is None:
                    current_dep_hash = self._get_hash(
                        current_dep_element, "signature_hash"
                    )

                if verified_dep_hash is None or current_dep_hash is None:
                    continue

                if verified_dep_hash != current_dep_hash:
                    # Find which refs relate to this dependency
                    # Use the max confidence among direct refs as base
                    if mapped_refs:
                        base_confidence = max(
                            ref.get("confidence", 1.0) for ref in mapped_refs
                        )
                    else:
                        base_confidence = 1.0

                    transitive_confidence = base_confidence * (
                        self._decay**hops
                    )

                    if transitive_confidence >= self._min_confidence:
                        issues.append(
                            StalenessIssue(
                                element_id=dep_id,
                                change_type="transitive",
                                confidence=transitive_confidence,
                                hops=hops,
                                detail=(
                                    f"Dependency '{dep_id}' has changed "
                                    f"({hops} hop(s) away)"
                                ),
                            )
                        )

            # Determine overall status
            if not issues:
                status = DocStatus.HEALTHY
            else:
                max_confidence = max(issue.confidence for issue in issues)
                if max_confidence >= 0.70:
                    status = DocStatus.STALE
                else:
                    status = DocStatus.POSSIBLY_STALE

            report[doc_path] = {"status": status, "issues": issues}

        return report
