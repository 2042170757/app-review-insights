"""Final read-only audit for Phase 1 review processing."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.review_processing import (
    DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    DEFAULT_OUTPUT_DIR,
    ProcessingConfig,
    _cosine_similarity,
    _tfidf_vectors,
    process_reviews,
)


PROCESSED_REVIEWS_PATH = DEFAULT_OUTPUT_DIR / "reviews.json"
PROCESSED_STATISTICS_PATH = DEFAULT_OUTPUT_DIR / "statistics.json"
PROCESSED_REPORT_PATH = DEFAULT_OUTPUT_DIR / "processing_report.json"


@dataclass
class AuditCheck:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Phase1AuditResult:
    raw_evidence: AuditCheck
    unknown_app: AuditCheck
    mixed_language: AuditCheck
    exact_duplicate: AuditCheck
    lexical_near_duplicate: AuditCheck
    semantic_boundary: AuditCheck
    statistics: AuditCheck
    json_input: AuditCheck
    csv_input: AuditCheck

    @property
    def checks(self) -> list[AuditCheck]:
        return [
            self.raw_evidence,
            self.unknown_app,
            self.mixed_language,
            self.exact_duplicate,
            self.lexical_near_duplicate,
            self.semantic_boundary,
            self.statistics,
            self.json_input,
            self.csv_input,
        ]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def main() -> int:
    result = run_phase1_audit()
    print_audit_result(result)
    return 0 if result.passed else 1


def run_phase1_audit() -> Phase1AuditResult:
    processed_reviews = _read_processed_reviews(PROCESSED_REVIEWS_PATH)
    input_audit = audit_json_csv_inputs()
    return Phase1AuditResult(
        raw_evidence=audit_raw_evidence_preservation(processed_reviews),
        unknown_app=audit_unknown_app_generalization(),
        mixed_language=audit_mixed_language_detection(),
        exact_duplicate=audit_exact_duplicate_detection(),
        lexical_near_duplicate=audit_lexical_near_duplicate_detection(),
        semantic_boundary=audit_semantic_similarity_boundary(),
        statistics=audit_statistics_consistency(),
        json_input=input_audit.json_input,
        csv_input=input_audit.csv_input,
    )


def audit_raw_evidence_preservation(processed_reviews: list[dict[str, Any]]) -> AuditCheck:
    details: list[str] = []
    samples = processed_reviews[:5]
    if len(samples) < 5:
        details.append(f"expected at least 5 processed reviews, found {len(samples)}")

    id_index = {
        str(review.get("raw_review", {}).get("id")): review
        for review in processed_reviews
        if isinstance(review.get("raw_review"), dict)
    }

    for review in samples:
        review_id = str(review.get("id") or "")
        raw_review = review.get("raw_review")
        if not review_id:
            details.append("processed review has empty id")
            continue
        if not isinstance(raw_review, dict):
            details.append(f"{review_id}: raw_review missing or not an object")
            continue
        if not raw_review.get("id"):
            details.append(f"{review_id}: original review id missing in raw_review")
        if review_id not in id_index:
            details.append(f"{review_id}: cannot find processed review by raw_review id")
        if "raw_title" not in review:
            details.append(f"{review_id}: raw_title field missing")
        if "raw_body" not in review:
            details.append(f"{review_id}: raw_body field missing")
        if review.get("raw_title") != raw_review.get("title"):
            details.append(f"{review_id}: raw_title does not match raw_review.title")
        if review.get("raw_body") != raw_review.get("body"):
            details.append(f"{review_id}: raw_body does not match raw_review.body")

    return AuditCheck(
        name="Raw Evidence Preservation",
        passed=not details,
        details=details,
        data={"sampled": len(samples)},
    )


def audit_unknown_app_generalization() -> AuditCheck:
    fixture = [
        _review(
            "calendar-1",
            app_id="calendar-pro-2026",
            title="Reliable shared calendar",
            body="The team calendar syncs quickly and reminders arrive on time.",
            rating=5,
            app_version="4.2",
        ),
        _review(
            "calendar-2",
            app_id="calendar-pro-2026",
            title="Reliable shared calendar",
            body="The team calendar syncs quickly and reminders arrive on time.",
            rating=4,
            app_version="4.2",
        ),
        _review(
            "calendar-3",
            app_id="calendar-pro-2026",
            title="Needs offline mode",
            body="I need to edit events on the train when the signal disappears.",
            rating=2,
            app_version="4.1",
        ),
    ]
    result = process_reviews(fixture)
    details: list[str] = []
    if result.statistics["total"] != 3:
        details.append("total statistics mismatch")
    if result.statistics["valid"] != 3:
        details.append("schema validation failed for valid unknown app fixture")
    if any(review.app_id == "839285684" for review in result.reviews):
        details.append("unexpected target app id leaked into unknown app processing")
    if any("Workout for Women" in (review.raw_body or "") for review in result.reviews):
        details.append("unexpected target app text leaked into unknown app processing")
    if not all(review.clean_body for review in result.reviews):
        details.append("cleaning did not produce clean_body for all reviews")
    if not all(review.language for review in result.reviews):
        details.append("language detection missing for at least one review")
    if result.report.exact_duplicate_count < 2:
        details.append("deduplication did not mark duplicated unknown app reviews")
    if result.statistics["average_rating"] != round((5 + 4 + 2) / 3, 4):
        details.append("statistics average rating mismatch")
    return AuditCheck(
        name="Unknown App Generalization",
        passed=not details,
        details=details,
        data={"statistics": result.statistics},
    )


def audit_mixed_language_detection() -> AuditCheck:
    fixture = [
        _review("lang-en", title="Useful app", body="The reminders are clear and easy to manage."),
        _review("lang-zh", title="很好用", body="这个应用的提醒很及时，界面也很清楚。"),
        _review("lang-es", title="Muy útil", body="La aplicación es excelente para organizar mis tareas."),
        _review("lang-fr", title="Très pratique", body="Cette application est très utile pour suivre mes rendez-vous."),
    ]
    result = process_reviews(fixture)
    distribution = result.statistics["language_distribution"]
    languages = [review.language for review in result.reviews]
    details: list[str] = []
    if any(not review.language for review in result.reviews):
        details.append("one or more reviews are missing language")
    if any(review.language_confidence is None for review in result.reviews):
        details.append("one or more reviews are missing language_confidence")
    if languages.count("en") == len(languages):
        details.append("all mixed-language reviews were classified as en")
    if len(distribution) < 2:
        details.append("language distribution does not include at least two languages")
    return AuditCheck(
        name="Mixed Language Detection",
        passed=not details,
        details=details,
        data={"language_distribution": distribution, "languages": languages},
    )


def audit_exact_duplicate_detection() -> AuditCheck:
    fixture = [
        _review("exact-a", title="", body="The subscription is too expensive."),
        _review("exact-b", title="", body="The subscription is too expensive."),
    ]
    result = process_reviews(fixture)
    reviews = {review.id: review for review in result.reviews}
    details: list[str] = []
    if not reviews["exact-a"].is_duplicate or not reviews["exact-b"].is_duplicate:
        details.append("exact duplicates were not marked is_duplicate")
    if not reviews["exact-a"].is_representative:
        details.append("first exact duplicate was not retained as representative")
    if reviews["exact-b"].is_representative:
        details.append("second exact duplicate was incorrectly retained as representative")
    return AuditCheck(
        name="Exact Duplicate Detection",
        passed=not details,
        details=details,
        data={
            "duplicate_group_ids": {
                review.id: review.duplicate_group_id for review in result.reviews
            },
            "exact_duplicate_count": result.report.exact_duplicate_count,
            "retained_count": result.report.retained_count,
        },
    )


def audit_lexical_near_duplicate_detection() -> AuditCheck:
    left = "The subscription is too expensive."
    right = "The subscription is too expensive now."
    unrelated = "This app crashes when I open it."
    fixture = [
        _review("lexical-a", title="", body=left),
        _review("lexical-b", title="", body=right),
        _review("lexical-c", title="", body=unrelated),
    ]
    result = process_reviews(fixture)
    reviews = {review.id: review for review in result.reviews}
    pairs = _near_duplicate_pairs(result.reviews)
    lexical_similarity = _pair_similarity(left, right)
    unrelated_similarity = _pair_similarity(left, unrelated)
    details: list[str] = []
    if not reviews["lexical-a"].near_duplicate_candidate or not reviews["lexical-b"].near_duplicate_candidate:
        details.append(
            "lexical A/B were not marked as near_duplicate_candidate "
            f"at threshold {DEFAULT_NEAR_DUPLICATE_THRESHOLD}; actual_similarity={lexical_similarity:.4f}"
        )
    if reviews["lexical-c"].near_duplicate_candidate:
        details.append("unrelated C was incorrectly marked as near_duplicate_candidate")
    if len(result.reviews) != 3:
        details.append("lexical near duplicate audit deleted reviews unexpectedly")
    return AuditCheck(
        name="Lexical Near Duplicate Detection",
        passed=not details,
        details=details,
        data={
            "left": left,
            "right": right,
            "unrelated": unrelated,
            "near_duplicate_pairs": pairs,
            "threshold": DEFAULT_NEAR_DUPLICATE_THRESHOLD,
            "lexical_similarity": lexical_similarity,
            "unrelated_similarity": unrelated_similarity,
            "candidate_flags": {
                review.id: review.near_duplicate_candidate for review in result.reviews
            },
        },
    )


def audit_semantic_similarity_boundary() -> AuditCheck:
    left = "The subscription is too expensive."
    right = "Subscription price is way too high."
    result = process_reviews(
        [
            _review("semantic-a", title="", body=left),
            _review("semantic-b", title="", body=right),
        ]
    )
    reviews = {review.id: review for review in result.reviews}
    similarity = _pair_similarity(left, right)
    details: list[str] = []
    if reviews["semantic-a"].near_duplicate_candidate or reviews["semantic-b"].near_duplicate_candidate:
        details.append("semantic boundary pair was unexpectedly marked by lexical detector")
    message = (
        "not handled by Phase 1 lexical duplicate detector; "
        "delegated to Phase 2 semantic analysis"
    )
    return AuditCheck(
        name="Semantic Similarity Boundary",
        passed=not details,
        details=details,
        data={
            "left": left,
            "right": right,
            "threshold": DEFAULT_NEAR_DUPLICATE_THRESHOLD,
            "similarity": similarity,
            "phase_boundary": message,
            "candidate_flags": {
                review.id: review.near_duplicate_candidate for review in result.reviews
            },
        },
    )


def audit_near_duplicate_detection() -> AuditCheck:
    """Backward-compatible alias for the corrected lexical near duplicate audit."""

    return audit_lexical_near_duplicate_detection()


def audit_old_semantic_near_duplicate_failure() -> AuditCheck:
    """Diagnostic-only form of the pre-correction semantic test."""

    fixture = [
        _review("near-a", title="", body="The subscription is too expensive."),
        _review("near-b", title="", body="Subscription price is way too high."),
        _review("near-c", title="", body="This app crashes when I open it."),
    ]
    result = process_reviews(fixture)
    reviews = {review.id: review for review in result.reviews}
    pairs = _near_duplicate_pairs(result.reviews)
    similarity = _pair_similarity(
        "The subscription is too expensive.",
        "Subscription price is way too high.",
    )
    details: list[str] = []
    if not reviews["near-a"].near_duplicate_candidate or not reviews["near-b"].near_duplicate_candidate:
        details.append(
            "A/B were not marked as near_duplicate_candidate "
            f"at threshold {DEFAULT_NEAR_DUPLICATE_THRESHOLD}; actual_similarity={similarity:.4f}"
        )
    if reviews["near-c"].near_duplicate_candidate:
        details.append("C was incorrectly marked as near_duplicate_candidate")
    if len(result.reviews) != 3:
        details.append("near duplicate audit deleted reviews unexpectedly")
    return AuditCheck(
        name="Semantic Near Duplicate Diagnostic",
        passed=not details,
        details=details,
        data={
            "near_duplicate_pairs": pairs,
            "threshold": DEFAULT_NEAR_DUPLICATE_THRESHOLD,
            "ab_similarity": similarity,
            "candidate_flags": {
                review.id: review.near_duplicate_candidate for review in result.reviews
            },
        },
    )


def audit_statistics_consistency() -> AuditCheck:
    ratings = [1, 1, 2, 3, 5]
    result = process_reviews(
        [
            _review(f"stats-{index}", rating=rating, body=f"Natural review sentence number {index}.")
            for index, rating in enumerate(ratings)
        ]
    )
    expected_distribution = {1: 2, 2: 1, 3: 1, 5: 1}
    details: list[str] = []
    stats = result.statistics
    if stats["total"] != 5:
        details.append(f"total expected 5, got {stats['total']}")
    if stats["average_rating"] != 2.4:
        details.append(f"average expected 2.4, got {stats['average_rating']}")
    if stats["rating_distribution"] != expected_distribution:
        details.append(
            f"rating_distribution expected {expected_distribution}, got {stats['rating_distribution']}"
        )
    if stats["language_distribution"].get("en") != 5:
        details.append(f"language_distribution expected en=5, got {stats['language_distribution']}")
    return AuditCheck(
        name="Statistics Consistency",
        passed=not details,
        details=details,
        data={"statistics": stats},
    )


@dataclass(frozen=True)
class InputAuditPair:
    json_input: AuditCheck
    csv_input: AuditCheck


def audit_json_csv_inputs() -> InputAuditPair:
    fixture = [
        _review("io-1", rating=1, body="This workflow is slow but still usable."),
        _review("io-2", rating=5, body="The export option is fast and reliable."),
        _review("io-3", rating=3, body="The layout is acceptable on my tablet."),
    ]
    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        json_path = temp_dir / "reviews.json"
        csv_path = temp_dir / "reviews.csv"
        json_out = temp_dir / "json-output"
        csv_out = temp_dir / "csv-output"
        json_path.write_text(json.dumps({"reviews": fixture}, ensure_ascii=False), encoding="utf-8")
        _write_fixture_csv(fixture, csv_path)

        json_run = _run_process_reviews(json_path, json_out)
        csv_run = _run_process_reviews(csv_path, csv_out)
        json_stats = _read_statistics(json_out / "statistics.json")
        csv_stats = _read_statistics(csv_out / "statistics.json")

    json_details: list[str] = []
    csv_details: list[str] = []
    if json_run.returncode != 0:
        json_details.append(f"process_reviews JSON failed: {json_run.stderr or json_run.stdout}")
    if csv_run.returncode != 0:
        csv_details.append(f"process_reviews CSV failed: {csv_run.stderr or csv_run.stdout}")
    if json_stats.get("total") != len(fixture):
        json_details.append(f"JSON total mismatch: {json_stats.get('total')}")
    if csv_stats.get("total") != len(fixture):
        csv_details.append(f"CSV total mismatch: {csv_stats.get('total')}")
    comparable_keys = ["total", "valid", "invalid", "rating_distribution", "average_rating"]
    for key in comparable_keys:
        if json_stats.get(key) != csv_stats.get(key):
            json_details.append(f"JSON/CSV statistics mismatch for {key}")
            csv_details.append(f"JSON/CSV statistics mismatch for {key}")

    return InputAuditPair(
        json_input=AuditCheck(
            name="JSON Input",
            passed=not json_details,
            details=json_details,
            data={"statistics": json_stats},
        ),
        csv_input=AuditCheck(
            name="CSV Input",
            passed=not csv_details,
            details=csv_details,
            data={"statistics": csv_stats},
        ),
    )


def print_audit_result(result: Phase1AuditResult) -> None:
    print("Phase 1 Final Audit")
    print("===================")
    print(f"Raw Evidence Preservation: {_status(result.raw_evidence)}")
    print(f"Unknown App Generalization: {_status(result.unknown_app)}")
    print(f"Mixed Language Detection: {_status(result.mixed_language)}")
    print(f"Exact Duplicate Detection: {_status(result.exact_duplicate)}")
    print(f"Lexical Near Duplicate Detection: {_status(result.lexical_near_duplicate)}")
    print(f"Semantic Similarity Boundary: {_status(result.semantic_boundary)}")
    print(f"Statistics Consistency: {_status(result.statistics)}")
    print(f"JSON Input: {_status(result.json_input)}")
    print(f"CSV Input: {_status(result.csv_input)}")
    print()
    print("Details:")
    for check in result.checks:
        if check.data:
            print(f"{check.name}: {json.dumps(check.data, ensure_ascii=False, sort_keys=True)}")
        for detail in check.details:
            print(f"- {check.name}: {detail}")
    print()
    print(f"Overall: {'PASS' if result.passed else 'FAIL'}")
    if not result.passed:
        print("Failed checks:")
        for check in result.checks:
            if not check.passed:
                print(f"- {check.name}")


def _read_processed_reviews(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    reviews = payload.get("reviews") if isinstance(payload, dict) else None
    if not isinstance(reviews, list) or not all(isinstance(review, dict) for review in reviews):
        raise ValueError(f"Processed reviews file is invalid: {path}")
    return list(reviews)


def _near_duplicate_pairs(reviews: list[Any]) -> list[dict[str, Any]]:
    candidates = [review for review in reviews if review.near_duplicate_candidate]
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(candidates):
        for right in candidates[left_index + 1 :]:
            pairs.append({"left": left.id, "right": right.id})
    return pairs


def _pair_similarity(left: str, right: str) -> float:
    vectors = _tfidf_vectors([left, right])
    return round(_cosine_similarity(vectors[0], vectors[1]), 4)


def _run_process_reviews(input_path: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "app.process_reviews",
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ],
        cwd=Path(__file__).resolve().parent.parent,
        text=True,
        capture_output=True,
        check=False,
    )


def _read_statistics(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_fixture_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _review(
    review_id: str,
    *,
    app_id: str = "audit-app-2026",
    title: str = "Clear workflow",
    body: str = "The workflow is clear and useful for daily planning.",
    rating: int = 4,
    app_version: str | None = "2.0",
) -> dict[str, Any]:
    return {
        "id": review_id,
        "source": "audit_fixture",
        "app_id": app_id,
        "territory": "US",
        "rating": rating,
        "title": title,
        "body": body,
        "author": "Audit Reviewer",
        "created_at": "2026-08-15T00:00:00Z",
        "app_version": app_version,
        "source_url": "https://example.test/audit-review",
    }


def _status(check: AuditCheck) -> str:
    return "PASS" if check.passed else "FAIL"


if __name__ == "__main__":
    raise SystemExit(main())
