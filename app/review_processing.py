"""Deterministic review processing pipeline for Unified Review Schema data."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.82
DEFAULT_INPUT_PATH = Path("artifacts/normalized/apify/normalized_reviews.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/processed")
REQUIRED_FIELDS = ("id", "app_id", "territory", "rating", "title", "body", "created_at", "source")
CSV_NULL = ""


@dataclass(frozen=True)
class ProcessingConfig:
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD


@dataclass
class ProcessedReview:
    original_index: int
    raw_review: dict[str, Any]
    id: str | None
    source: str | None
    app_id: str | None
    territory: str | None
    rating: int | None
    title: str | None
    body: str | None
    raw_title: str | None
    raw_body: str | None
    clean_title: str | None
    clean_body: str | None
    author: str | None
    created_at: str | None
    app_version: str | None
    source_url: str | None
    language: str
    language_confidence: float
    duplicate_group_id: str | None
    is_duplicate: bool
    is_representative: bool
    near_duplicate_candidate: bool
    is_valid: bool
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class ProcessingReport:
    input_count: int
    valid_count: int
    invalid_count: int
    exact_duplicate_count: int
    near_duplicate_count: int
    retained_count: int
    processing_timestamp: str
    exclusion_reasons: dict[str, int]
    near_duplicate_threshold: float


@dataclass
class ProcessingResult:
    reviews: list[ProcessedReview]
    statistics: dict[str, Any]
    report: ProcessingReport

    @property
    def passed(self) -> bool:
        return True


def load_reviews(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        return load_reviews_csv(path)
    return load_reviews_json(path)


def load_reviews_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("reviews", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("JSON input must be a list or an object with a reviews list")
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("JSON reviews must be objects")
    return list(rows)


def load_reviews_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def process_reviews(
    reviews: list[dict[str, Any]],
    *,
    config: ProcessingConfig | None = None,
) -> ProcessingResult:
    config = config or ProcessingConfig()
    processed = [_process_one(index, review) for index, review in enumerate(reviews)]
    _mark_exact_duplicates(processed)
    _mark_near_duplicates(processed, threshold=config.near_duplicate_threshold)
    statistics = build_statistics(processed)
    report = build_processing_report(
        processed,
        processing_timestamp=datetime.now(UTC).isoformat(),
        near_duplicate_threshold=config.near_duplicate_threshold,
    )
    return ProcessingResult(reviews=processed, statistics=statistics, report=report)


def write_processing_outputs(
    result: ProcessingResult,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    reviews_json_path = output_dir / "reviews.json"
    reviews_csv_path = output_dir / "reviews.csv"
    statistics_path = output_dir / "statistics.json"
    report_path = output_dir / "processing_report.json"

    review_dicts = [asdict(review) for review in result.reviews]
    reviews_json_path.write_text(
        json.dumps({"reviews": review_dicts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_reviews_csv(review_dicts, reviews_csv_path)
    statistics_path.write_text(
        json.dumps(result.statistics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(asdict(result.report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "reviews_json": reviews_json_path,
        "reviews_csv": reviews_csv_path,
        "statistics": statistics_path,
        "processing_report": report_path,
    }


def build_statistics(processed: list[ProcessedReview]) -> dict[str, Any]:
    valid_reviews = [review for review in processed if review.is_valid]
    retained_reviews = [review for review in valid_reviews if review.is_representative]
    duplicate_group_ids = {
        review.duplicate_group_id
        for review in valid_reviews
        if review.duplicate_group_id and review.is_duplicate
    }
    rating_values = [review.rating for review in valid_reviews if review.rating is not None]
    rating_distribution = Counter(rating_values)
    language_distribution = Counter(review.language for review in valid_reviews)
    reviews_by_date = Counter(
        review.created_at[:10] for review in valid_reviews if review.created_at
    )
    reviews_by_app_version = Counter(
        review.app_version or "unknown" for review in valid_reviews
    )

    return {
        "total": len(processed),
        "valid": len(valid_reviews),
        "invalid": len(processed) - len(valid_reviews),
        "retained": len(retained_reviews),
        "duplicate_groups": len(duplicate_group_ids),
        "exact_duplicates": sum(1 for review in valid_reviews if review.is_duplicate),
        "near_duplicate_candidates": sum(
            1 for review in valid_reviews if review.near_duplicate_candidate
        ),
        "rating_distribution": dict(sorted(rating_distribution.items())),
        "average_rating": round(sum(rating_values) / len(rating_values), 4)
        if rating_values
        else None,
        "language_distribution": dict(sorted(language_distribution.items())),
        "reviews_by_date": dict(sorted(reviews_by_date.items())),
        "reviews_by_app_version": dict(sorted(reviews_by_app_version.items())),
    }


def build_processing_report(
    processed: list[ProcessedReview],
    *,
    processing_timestamp: str,
    near_duplicate_threshold: float,
) -> ProcessingReport:
    exclusion_reasons: Counter[str] = Counter()
    for review in processed:
        for error in review.validation_errors:
            exclusion_reasons[error] += 1
        if review.is_valid and not review.is_representative:
            exclusion_reasons["exact_duplicate_non_representative"] += 1

    valid_count = sum(1 for review in processed if review.is_valid)
    exact_duplicate_count = sum(
        1 for review in processed if review.is_valid and review.is_duplicate
    )
    near_duplicate_count = sum(
        1 for review in processed if review.is_valid and review.near_duplicate_candidate
    )
    retained_count = sum(
        1 for review in processed if review.is_valid and review.is_representative
    )
    return ProcessingReport(
        input_count=len(processed),
        valid_count=valid_count,
        invalid_count=len(processed) - valid_count,
        exact_duplicate_count=exact_duplicate_count,
        near_duplicate_count=near_duplicate_count,
        retained_count=retained_count,
        processing_timestamp=processing_timestamp,
        exclusion_reasons=dict(sorted(exclusion_reasons.items())),
        near_duplicate_threshold=near_duplicate_threshold,
    )


def validate_review(review: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name in REQUIRED_FIELDS:
        if field_name not in review:
            errors.append(f"missing_{field_name}")

    if not _present(review.get("id")):
        errors.append("missing_id")
    if not _present(review.get("app_id")):
        errors.append("missing_app_id")
    if not _present(review.get("territory")):
        errors.append("missing_territory")
    if not _present(review.get("source")):
        errors.append("missing_source")

    try:
        rating = int(review.get("rating"))
    except (TypeError, ValueError):
        errors.append("invalid_rating")
    else:
        if rating < 1 or rating > 5:
            errors.append("invalid_rating")

    if not _present(review.get("title")) and not _present(review.get("body")):
        errors.append("missing_title_body")

    if not _parse_datetime(review.get("created_at")):
        errors.append("invalid_created_at")

    return sorted(set(errors))


def detect_language(text: str) -> tuple[str, float]:
    normalized = text.lower()
    if not normalized.strip():
        return "other", 0.0
    if re.search(r"[\u4e00-\u9fff]", normalized):
        return "zh", 0.95
    if re.search(r"[áéíóúñ¿¡]", normalized) or _contains_word(
        normalized,
        {"el", "la", "que", "para", "muy", "gracias", "excelente", "pero"},
    ):
        return "es", 0.78
    if re.search(r"[àâçéèêëîïôûùüÿœ]", normalized) or _contains_word(
        normalized,
        {"le", "la", "les", "des", "pour", "avec", "très", "merci", "mais"},
    ):
        return "fr", 0.78
    latin_letters = len(re.findall(r"[a-z]", normalized))
    all_letters = len(re.findall(r"[^\W\d_]", normalized, flags=re.UNICODE))
    if latin_letters and latin_letters / max(all_letters, 1) >= 0.75:
        return "en", 0.72
    return "other", 0.45


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def clean_text(value: Any) -> str | None:
    return normalize_text(value)


def stable_duplicate_hash(title: str | None, body: str | None) -> str:
    payload = f"{(title or '').casefold()}\n{(body or '').casefold()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _process_one(index: int, review: dict[str, Any]) -> ProcessedReview:
    validation_errors = validate_review(review)
    raw_title = review.get("title") if review.get("title") is not None else None
    raw_body = review.get("body") if review.get("body") is not None else None
    title = normalize_text(raw_title)
    body = normalize_text(raw_body)
    clean_title = clean_text(raw_title)
    clean_body = clean_text(raw_body)
    created_at = normalize_datetime_utc(review.get("created_at"))
    language, confidence = detect_language(" ".join(part for part in (clean_title, clean_body) if part))

    rating: int | None
    try:
        rating = int(review.get("rating"))
    except (TypeError, ValueError):
        rating = None

    return ProcessedReview(
        original_index=index,
        raw_review=dict(review),
        id=normalize_text(review.get("id")),
        source=normalize_text(review.get("source")),
        app_id=normalize_text(review.get("app_id")),
        territory=normalize_text(review.get("territory")),
        rating=rating,
        title=title,
        body=body,
        raw_title=str(raw_title) if raw_title is not None else None,
        raw_body=str(raw_body) if raw_body is not None else None,
        clean_title=clean_title,
        clean_body=clean_body,
        author=normalize_text(review.get("author")),
        created_at=created_at,
        app_version=normalize_text(review.get("app_version")),
        source_url=normalize_text(review.get("source_url")),
        language=language,
        language_confidence=confidence,
        duplicate_group_id=None,
        is_duplicate=False,
        is_representative=False,
        near_duplicate_candidate=False,
        is_valid=not validation_errors,
        validation_errors=validation_errors,
    )


def normalize_datetime_utc(value: Any) -> str | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC).replace(microsecond=0)
    return parsed.isoformat().replace("+00:00", "Z")


def _mark_exact_duplicates(processed: list[ProcessedReview]) -> None:
    groups: defaultdict[str, list[ProcessedReview]] = defaultdict(list)
    for review in processed:
        if not review.is_valid:
            review.is_representative = False
            continue
        group_id = stable_duplicate_hash(review.title, review.body)
        review.duplicate_group_id = group_id
        groups[group_id].append(review)

    for group in groups.values():
        for index, review in enumerate(group):
            review.is_duplicate = len(group) > 1
            review.is_representative = index == 0


def _mark_near_duplicates(processed: list[ProcessedReview], *, threshold: float) -> None:
    candidates = [review for review in processed if review.is_valid]
    documents = [
        " ".join(part for part in (review.clean_title, review.clean_body) if part)
        for review in candidates
    ]
    vectors = _tfidf_vectors(documents)
    for left_index in range(len(candidates)):
        for right_index in range(left_index + 1, len(candidates)):
            left = candidates[left_index]
            right = candidates[right_index]
            if left.duplicate_group_id and left.duplicate_group_id == right.duplicate_group_id:
                continue
            similarity = _cosine_similarity(vectors[left_index], vectors[right_index])
            if similarity >= threshold:
                left.near_duplicate_candidate = True
                right.near_duplicate_candidate = True


def _tfidf_vectors(documents: list[str]) -> list[dict[str, float]]:
    tokenized = [_tokenize(document) for document in documents]
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))

    total_documents = len(documents)
    vectors: list[dict[str, float]] = []
    for tokens in tokenized:
        counts = Counter(tokens)
        token_total = sum(counts.values()) or 1
        vector: dict[str, float] = {}
        for token, count in counts.items():
            term_frequency = count / token_total
            inverse_document_frequency = math.log(
                (1 + total_documents) / (1 + document_frequency[token])
            ) + 1
            vector[token] = term_frequency * inverse_document_frequency
        vectors.append(vector)
    return vectors


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    shared = set(left).intersection(right)
    numerator = sum(left[token] * right[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.casefold(), flags=re.UNICODE)


def _write_reviews_csv(review_dicts: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "original_index",
        "id",
        "source",
        "app_id",
        "territory",
        "rating",
        "title",
        "body",
        "raw_title",
        "raw_body",
        "clean_title",
        "clean_body",
        "author",
        "created_at",
        "app_version",
        "source_url",
        "language",
        "language_confidence",
        "duplicate_group_id",
        "is_duplicate",
        "is_representative",
        "near_duplicate_candidate",
        "is_valid",
        "validation_errors",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in review_dicts:
            writer.writerow(
                {
                    field: _csv_value(row.get(field))
                    for field in fieldnames
                }
            )


def _csv_value(value: Any) -> Any:
    if value is None:
        return CSV_NULL
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _contains_word(text: str, words: set[str]) -> bool:
    tokens = set(_tokenize(text))
    return bool(tokens.intersection(words))


def _present(value: Any) -> bool:
    return normalize_text(value) is not None

