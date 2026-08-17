"""JSON/CSV review import validation and artifact adapters."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.providers import CsvImportProvider, JsonImportProvider, ReviewFetchResult
from app.review_processing import validate_review
from app.workflow.models import now_utc


IMPORT_SOURCE_JSON = "json"
IMPORT_SOURCE_CSV = "csv"
IMPORT_SOURCE_TYPES = {IMPORT_SOURCE_JSON, IMPORT_SOURCE_CSV}
IMPORT_ROOT_ENV = "WORKFLOW_IMPORT_ROOT"
IMPORT_MAX_BYTES_ENV = "WORKFLOW_IMPORT_MAX_BYTES"
DEFAULT_MAX_IMPORT_BYTES = 5 * 1024 * 1024
UNKNOWN_TERRITORY = "UNKNOWN"
UNKNOWN_TERRITORY_LABEL = "Unknown / Not provided"


@dataclass(frozen=True)
class ImportedDataset:
    import_id: str
    source_type: str
    filename: str
    path: Path
    metadata: dict[str, Any]


class ImportValidationError(ValueError):
    def __init__(self, error_type: str, message: str) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def import_root() -> Path:
    configured = os.environ.get(IMPORT_ROOT_ENV)
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "app-review-insights-imports"


def max_import_bytes() -> int:
    configured = os.environ.get(IMPORT_MAX_BYTES_ENV)
    if not configured:
        return DEFAULT_MAX_IMPORT_BYTES
    try:
        value = int(configured)
    except ValueError:
        return DEFAULT_MAX_IMPORT_BYTES
    return max(1, value)


def create_import_dataset(
    *,
    source_type: str,
    filename: str,
    content: bytes,
    app_id: str = "",
    max_bytes: int | None = None,
) -> ImportedDataset:
    normalized_source = _validate_source_type(source_type)
    safe_name = _safe_filename(filename)
    _validate_extension(normalized_source, safe_name)
    limit = max_import_bytes() if max_bytes is None else max_bytes
    if not content:
        raise ImportValidationError("Empty Dataset", "Uploaded file is empty.")
    if len(content) > limit:
        raise ImportValidationError("File Too Large", f"Uploaded file exceeds {limit} bytes.")

    text = _decode_upload(content)
    rows = _load_rows(normalized_source, text)
    if not rows:
        raise ImportValidationError("Empty Dataset", "Uploaded file does not contain review records.")

    import_id = str(uuid4())
    directory = import_root() / import_id
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / safe_name
    path.write_bytes(content)

    result = fetch_imported_reviews(
        source_type=normalized_source,
        path=path,
        app_id=app_id,
        max_reviews=len(rows),
    )
    if result.errors:
        first_error = result.errors[0]
        raise ImportValidationError(
            _classify_provider_error(normalized_source, first_error.raw_error or first_error.message),
            first_error.raw_error or first_error.message,
        )
    if not result.reviews:
        raise ImportValidationError("Empty Dataset", "Import provider returned no normalized reviews.")

    validation_errors = _schema_errors(result.reviews)
    if validation_errors:
        raise ImportValidationError("Schema Validation Failed", "; ".join(validation_errors[:5]))

    metadata = build_import_metadata(
        source_type=normalized_source,
        filename=safe_name,
        record_count=len(rows),
        reviews=result.reviews,
        provider=result.provider,
        coverage=result.coverage,
    )
    return ImportedDataset(
        import_id=import_id,
        source_type=normalized_source,
        filename=safe_name,
        path=path,
        metadata=metadata,
    )


def fetch_imported_reviews(
    *,
    source_type: str,
    path: Path,
    app_id: str,
    max_reviews: int,
) -> ReviewFetchResult:
    normalized_source = _validate_source_type(source_type)
    provider = (
        JsonImportProvider(path, territory=UNKNOWN_TERRITORY)
        if normalized_source == IMPORT_SOURCE_JSON
        else CsvImportProvider(path, territory=UNKNOWN_TERRITORY)
    )
    return provider.fetch_reviews(app_id, max_reviews=max_reviews)


def build_import_metadata(
    *,
    source_type: str,
    filename: str,
    record_count: int,
    reviews: list[dict[str, Any]],
    provider: str,
    coverage: str,
) -> dict[str, Any]:
    territories = sorted({_text(review.get("territory")) for review in reviews if _text(review.get("territory"))})
    app_ids = sorted({_text(review.get("app_id")) for review in reviews if _text(review.get("app_id"))})
    territory = _dataset_territory(territories)
    app_id = app_ids[0] if len(app_ids) == 1 else ("Mixed" if len(app_ids) > 1 else None)
    limitations = ["Imported dataset; no live App Store collection was performed."]
    if territory == UNKNOWN_TERRITORY_LABEL:
        limitations.append("Review territory was not provided by the imported dataset.")
    return {
        "source_type": source_type,
        "display_source": f"Imported {source_type.upper()}",
        "provider": provider,
        "filename": filename,
        "record_count": record_count,
        "valid_count": len(reviews),
        "invalid_count": 0,
        "territory": territory,
        "app_id": app_id,
        "imported_at": now_utc(),
        "coverage": coverage,
        "limitations": limitations,
        "cached_label": None,
        "artifact_source": "Uploaded File",
    }


def save_import_artifacts(
    *,
    result: ReviewFetchResult,
    metadata: dict[str, Any],
    output_dir: Path = Path("artifacts/normalized/import"),
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = output_dir / "normalized_reviews.json"
    metadata_path = output_dir / "dataset_metadata.json"
    validation_path = output_dir / "import_validation.json"
    normalized_path.write_text(
        json.dumps({"reviews": result.reviews}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "errors": [],
                "warnings": metadata.get("limitations", []),
                "source_type": metadata.get("source_type"),
                "record_count": metadata.get("record_count"),
                "valid_count": metadata.get("valid_count"),
                "invalid_count": metadata.get("invalid_count"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return [normalized_path, metadata_path, validation_path]


def _validate_source_type(source_type: str) -> str:
    normalized = str(source_type or "").strip().lower()
    if normalized not in IMPORT_SOURCE_TYPES:
        raise ImportValidationError("Invalid Source Type", "source_type must be json or csv.")
    return normalized


def _safe_filename(filename: str) -> str:
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise ImportValidationError("Missing File", "Uploaded file must have a filename.")
    return safe_name


def _validate_extension(source_type: str, filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    expected = f".{source_type}"
    if suffix != expected:
        raise ImportValidationError("Invalid Extension", f"Expected a {expected} file.")


def _decode_upload(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportValidationError("Invalid Encoding", "Uploaded file must be UTF-8 text.") from exc


def _load_rows(source_type: str, text: str) -> list[dict[str, Any]]:
    if source_type == IMPORT_SOURCE_JSON:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ImportValidationError("Invalid JSON", f"JSON parse failed: {exc.msg}") from exc
        rows = payload.get("reviews", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ImportValidationError("Invalid JSON", "JSON import must contain a list or {'reviews': list}.")
        if not all(isinstance(row, dict) for row in rows):
            raise ImportValidationError("Invalid JSON", "JSON review records must be objects.")
        return list(rows)

    try:
        reader = csv.DictReader(text.splitlines())
        if not reader.fieldnames:
            raise ImportValidationError("Invalid CSV", "CSV file must include a header row.")
        rows = [dict(row) for row in reader]
    except csv.Error as exc:
        raise ImportValidationError("Invalid CSV", f"CSV parse failed: {exc}") from exc
    if rows and not {"rating", "created_at"}.issubset(set(reader.fieldnames or [])):
        raise ImportValidationError("Missing Columns", "CSV must include rating and created_at columns.")
    return rows


def _schema_errors(reviews: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, review in enumerate(reviews, start=1):
        review_errors = validate_review(review)
        if review_errors:
            errors.append(f"record {index}: {', '.join(review_errors)}")
    return errors


def _classify_provider_error(source_type: str, raw_error: str) -> str:
    normalized = raw_error.lower()
    if "rating" in normalized:
        return "Invalid Rating"
    if "created_at" in normalized or "datetime" in normalized or "isoformat" in normalized:
        return "Invalid Date"
    if "keyerror" in normalized or "missing" in normalized:
        return "Missing Required Field" if source_type == IMPORT_SOURCE_JSON else "Missing Columns"
    if "title or body" in normalized:
        return "Missing Required Field"
    return "Invalid JSON" if source_type == IMPORT_SOURCE_JSON else "Invalid CSV"


def _dataset_territory(territories: list[str]) -> str:
    real_territories = [territory for territory in territories if territory and territory != UNKNOWN_TERRITORY]
    if len(real_territories) == 1 and len(territories) == 1:
        return real_territories[0]
    if real_territories:
        return "Mixed"
    return UNKNOWN_TERRITORY_LABEL


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
