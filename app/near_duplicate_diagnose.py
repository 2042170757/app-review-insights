"""Read-only diagnosis for Phase 1 near duplicate behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.review_processing import (
    DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    _cosine_similarity,
    _tfidf_vectors,
    process_reviews,
)


@dataclass(frozen=True)
class DiagnosisGroup:
    name: str
    left: str
    right: str


@dataclass(frozen=True)
class DiagnosisResult:
    group: DiagnosisGroup
    cosine_similarity: float
    threshold: float
    marked_near_duplicate: bool


GROUPS = [
    DiagnosisGroup(
        name="Group A",
        left="The subscription is too expensive.",
        right="The subscription is very expensive.",
    ),
    DiagnosisGroup(
        name="Group B",
        left="The subscription is too expensive.",
        right="The subscription price is extremely expensive.",
    ),
    DiagnosisGroup(
        name="Group C",
        left="The subscription is too expensive.",
        right="Subscription price is way too high.",
    ),
    DiagnosisGroup(
        name="Group D",
        left="The subscription is too expensive.",
        right="This app crashes when I open it.",
    ),
]


def main() -> int:
    results = diagnose_near_duplicate_groups()
    print_diagnosis(results)
    return 0


def diagnose_near_duplicate_groups(
    groups: list[DiagnosisGroup] | None = None,
    *,
    threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> list[DiagnosisResult]:
    return [_diagnose_group(group, threshold=threshold) for group in (groups or GROUPS)]


def print_diagnosis(results: list[DiagnosisResult]) -> None:
    print("Near Duplicate Algorithm Diagnosis")
    print("===================================")
    print("Algorithm:")
    print("word-level TF-IDF vectors over cleaned title/body text + cosine similarity")
    print()
    print(f"Threshold: {DEFAULT_NEAR_DUPLICATE_THRESHOLD}")
    print()
    for result in results:
        print(f"{result.group.name}:")
        print(f'left: "{result.group.left}"')
        print(f'right: "{result.group.right}"')
        print(f"cosine similarity: {result.cosine_similarity:.4f}")
        print(f"marked near duplicate: {str(result.marked_near_duplicate).upper()}")
        print()
    print("Recommendation:")
    print(
        "Current Phase 1 detects lexical near duplicates, not semantic similarity. "
        "Keep the deterministic TF-IDF path for conservative lexical duplicate flags, "
        "and handle semantic duplicate discovery in a later phase with a stronger "
        "method such as character n-gram TF-IDF, token/fuzzy similarity, local "
        "embeddings, or Phase 2 AI analysis."
    )


def _diagnose_group(group: DiagnosisGroup, *, threshold: float) -> DiagnosisResult:
    reviews = [
        _review("left", group.left),
        _review("right", group.right),
    ]
    processed = process_reviews(reviews)
    marked = any(review.near_duplicate_candidate for review in processed.reviews)
    return DiagnosisResult(
        group=group,
        cosine_similarity=_pair_similarity(group.left, group.right),
        threshold=threshold,
        marked_near_duplicate=marked,
    )


def _pair_similarity(left: str, right: str) -> float:
    vectors = _tfidf_vectors([left, right])
    return _cosine_similarity(vectors[0], vectors[1])


def _review(review_id: str, body: str) -> dict[str, Any]:
    return {
        "id": f"diagnose-{review_id}",
        "source": "diagnostic_fixture",
        "app_id": "diagnostic-app",
        "territory": "US",
        "rating": 3,
        "title": "",
        "body": body,
        "author": None,
        "created_at": "2026-08-15T00:00:00Z",
        "app_version": None,
        "source_url": None,
    }


if __name__ == "__main__":
    raise SystemExit(main())

