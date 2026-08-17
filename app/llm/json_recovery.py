"""Deterministic JSON response recovery for LLM outputs.

This module only extracts an existing JSON object from model text. It never
adds, removes, or rewrites fields inside the JSON payload.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class JSONRecoveryResult:
    raw_response: str
    extracted_response: str
    parsed: Any
    attempted: bool
    success: bool
    method: str
    error: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "method": self.method,
            "success": self.success,
            "error": self.error,
        }

    def evidence(self) -> dict[str, Any]:
        return {
            **self.metadata(),
            "raw_response": self.raw_response,
            "extracted_response": self.extracted_response,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_json_response(text: str) -> JSONRecoveryResult:
    raw_response = text if isinstance(text, str) else ""
    stripped = raw_response.strip()
    if not stripped:
        return _failure(raw_response, "empty_response", attempted=False, error="empty response")

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(parsed, str):
            inner = _parse_json_string_payload(raw_response, parsed)
            if inner.success:
                return inner
        return JSONRecoveryResult(
            raw_response=raw_response,
            extracted_response=stripped,
            parsed=parsed,
            attempted=False,
            success=True,
            method="direct_json",
        )

    fenced = _fenced_json_candidates(raw_response)
    fenced_valid = _valid_json_candidates(fenced)
    if len(fenced_valid) == 1:
        candidate, parsed = fenced_valid[0]
        return JSONRecoveryResult(
            raw_response=raw_response,
            extracted_response=candidate,
            parsed=parsed,
            attempted=True,
            success=True,
            method="fenced_json",
        )
    if len(fenced_valid) > 1:
        return _failure(
            raw_response,
            "multiple_json_objects",
            attempted=True,
            error="multiple JSON objects found in fenced blocks",
        )

    object_candidates = extract_json_object(raw_response)
    object_valid = _valid_json_candidates(object_candidates)
    if len(object_valid) == 1:
        candidate, parsed = object_valid[0]
        return JSONRecoveryResult(
            raw_response=raw_response,
            extracted_response=candidate,
            parsed=parsed,
            attempted=True,
            success=True,
            method="embedded_json_object",
        )
    if len(object_valid) > 1:
        return _failure(
            raw_response,
            "multiple_json_objects",
            attempted=True,
            error="multiple JSON objects found",
        )
    return _failure(raw_response, "invalid_json", attempted=True, error="no recoverable JSON object found")


def extract_json_object(text: str) -> list[str]:
    """Return complete JSON object substrings found in text.

    The extraction is brace-balanced and string-aware. It does not modify the
    extracted object text.
    """

    if not isinstance(text, str) or "{" not in text:
        return []
    candidates: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
            continue
        if char == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start : index + 1].strip())
                start = None
    return candidates


def _parse_json_string_payload(raw_response: str, parsed: str) -> JSONRecoveryResult:
    inner = parsed.strip()
    if not inner:
        return _failure(raw_response, "json_string_empty", attempted=True, error="JSON string payload is empty")
    try:
        inner_parsed = json.loads(inner)
    except json.JSONDecodeError:
        return _failure(raw_response, "json_string_invalid", attempted=True, error="JSON string payload is not JSON")
    return JSONRecoveryResult(
        raw_response=raw_response,
        extracted_response=inner,
        parsed=inner_parsed,
        attempted=True,
        success=True,
        method="json_string",
    )


def _fenced_json_candidates(text: str) -> list[str]:
    return [
        block.strip()
        for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if block.strip()
    ]


def _valid_json_candidates(candidates: list[str]) -> list[tuple[str, Any]]:
    valid: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        valid.append((candidate, parsed))
    return valid


def _failure(raw_response: str, method: str, *, attempted: bool, error: str) -> JSONRecoveryResult:
    return JSONRecoveryResult(
        raw_response=raw_response,
        extracted_response="",
        parsed=None,
        attempted=attempted,
        success=False,
        method=method,
        error=error,
    )
