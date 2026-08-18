"""Deterministic validation for PRD output and traceability."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.product_scope import validate_product_scope
from app.prd_schema import PRD


STATUS_SUCCESS = "Success"
STATUS_INVALID_JSON = "Invalid JSON"
STATUS_SCHEMA_VALIDATION_FAILED = "Schema Validation Failed"
STATUS_INPUT_VALIDATION_FAILED = "Input Validation Failed"
STATUS_UNKNOWN_VERSION_ID = "Unknown Version ID"
STATUS_UNKNOWN_REQUIREMENT_ID = "Unknown Requirement ID"
STATUS_REQUIREMENT_VERSION_MISMATCH = "Requirement Version Mismatch"
STATUS_UNKNOWN_FINDING_ID = "Unknown Finding ID"
STATUS_TRACEABILITY_MISMATCH = "Traceability Mismatch"
STATUS_GOAL_INCOHERENCE = "Goal Incoherence"
STATUS_EVIDENCE_SUMMARY_INVALID = "Evidence Summary Invalid"
STATUS_SUCCESS_METRIC_INVALID = "Success Metric Invalid"
STATUS_PROHIBITED_IMPLEMENTATION_DETAIL = "Prohibited Implementation Detail"
STATUS_DUPLICATE_PRD_ID = "Duplicate PRD ID"
STATUS_EMPTY_PRDS = "Empty PRDs"
STATUS_UNSUPPORTED_PRODUCT_DIRECTION = "Unsupported Product Direction"
STATUS_MISSING_OPEN_QUESTION = "Missing Open Question"

TECHNICAL_TERMS = {
    "react",
    "vue",
    "angular",
    "postgresql",
    "redis",
    "sql",
    "database",
    "api",
    "endpoint",
    "component",
    "class",
    "function",
    ".py",
    ".js",
    ".tsx",
    "code",
}

GENERIC_METRICS = {
    "better user experience",
    "improve user experience",
    "make the experience better",
    "increase engagement",
    "improve engagement",
    "enhance engagement",
    "increase user engagement",
    "improve user satisfaction",
    "increase user satisfaction",
    "enhance user satisfaction",
    "improve satisfaction",
    "improved trust",
    "improve trust",
    "用户体验更好",
    "提高用户体验",
    "改善用户体验",
    "用户更满意",
    "提升参与度",
    "增强用户满意度",
}


@dataclass
class PRDValidationResult:
    status: str
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    prds: list[PRD] = field(default_factory=list)
    unknown_version_ids: list[str] = field(default_factory=list)
    unknown_requirement_ids: list[str] = field(default_factory=list)
    unknown_finding_ids: list[str] = field(default_factory=list)
    traceability_errors: list[str] = field(default_factory=list)
    evidence_summary_errors: list[str] = field(default_factory=list)
    goal_errors: list[str] = field(default_factory=list)
    success_metric_errors: list[str] = field(default_factory=list)
    implementation_detail_errors: list[str] = field(default_factory=list)
    duplicate_prd_ids: list[str] = field(default_factory=list)
    unsupported_scope_errors: list[str] = field(default_factory=list)
    missing_open_question_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["prds"] = [asdict(prd) for prd in self.prds]
        return payload


def validate_prd_output(
    raw_text: str,
    *,
    requirements_by_id: dict[str, dict[str, Any]],
    versions_by_id: dict[str, dict[str, Any]],
    findings_by_id: dict[str, dict[str, Any]],
    issues_by_id: dict[str, dict[str, Any]],
    topics_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
    requirement_validation_passed: bool,
    roadmap_validation_passed: bool,
    finding_validation_passed: bool,
) -> PRDValidationResult:
    if not (requirement_validation_passed and roadmap_validation_passed and finding_validation_passed):
        return PRDValidationResult(
            status=STATUS_INPUT_VALIDATION_FAILED,
            passed=False,
            errors=["Requirement, Roadmap, and Finding validation must all be PASS before PRD validation."],
        )
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return PRDValidationResult(
            status=STATUS_INVALID_JSON,
            passed=False,
            errors=[f"Invalid JSON: {exc.msg}"],
        )
    return validate_prd_payload(
        payload,
        requirements_by_id=requirements_by_id,
        versions_by_id=versions_by_id,
        findings_by_id=findings_by_id,
        issues_by_id=issues_by_id,
        topics_by_id=topics_by_id,
        valid_review_ids=valid_review_ids,
    )


def validate_prd_payload(
    payload: Any,
    *,
    requirements_by_id: dict[str, dict[str, Any]],
    versions_by_id: dict[str, dict[str, Any]],
    findings_by_id: dict[str, dict[str, Any]],
    issues_by_id: dict[str, dict[str, Any]],
    topics_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
) -> PRDValidationResult:
    if not isinstance(payload, dict):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: root must be an object"])
    raw_prds = payload.get("prds")
    if raw_prds is None:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: missing prds"])
    if not isinstance(raw_prds, list):
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, ["schema: prds must be a list"])
    if not raw_prds:
        return PRDValidationResult(
            status=STATUS_EMPTY_PRDS,
            passed=True,
            warnings=["empty_prds"],
        )

    errors: list[str] = []
    prds: list[PRD] = []
    seen_prd_ids: set[str] = set()
    duplicate_prd_ids: set[str] = set()
    unknown_version_ids: set[str] = set()
    unknown_requirement_ids: set[str] = set()
    unknown_finding_ids: set[str] = set()
    version_mismatch_errors: list[str] = []
    traceability_errors: list[str] = []
    evidence_summary_errors: list[str] = []
    goal_errors: list[str] = []
    metric_errors: list[str] = []
    implementation_errors: list[str] = []
    unsupported_scope_errors: list[str] = []
    missing_open_question_errors: list[str] = []

    for index, raw_prd in enumerate(raw_prds):
        prefix = f"prds[{index}]"
        if not isinstance(raw_prd, dict):
            errors.append(f"{prefix}: must be an object")
            continue

        prd_id = _text(raw_prd.get("prd_id"))
        version_id = _text(raw_prd.get("version_id"))
        title = _text(raw_prd.get("title"))
        overview = _text(raw_prd.get("overview"))
        problem_statement = _text(raw_prd.get("problem_statement"))
        evidence_summary = _text(raw_prd.get("evidence_summary"))
        goals = _text_list(raw_prd.get("goals"), f"{prefix}.goals", errors, min_items=1)
        non_goals = _text_list(raw_prd.get("non_goals"), f"{prefix}.non_goals", errors, min_items=0)
        requirement_ids = _text_list(raw_prd.get("requirement_ids"), f"{prefix}.requirement_ids", errors, min_items=1)
        risks = _text_list(raw_prd.get("risks"), f"{prefix}.risks", errors, min_items=0)
        success_metrics = _text_list(raw_prd.get("success_metrics"), f"{prefix}.success_metrics", errors, min_items=0)
        open_questions = _text_list(raw_prd.get("open_questions"), f"{prefix}.open_questions", errors, min_items=0)

        if not prd_id:
            errors.append(f"{prefix}.prd_id: required")
        elif prd_id in seen_prd_ids:
            duplicate_prd_ids.add(prd_id)
        else:
            seen_prd_ids.add(prd_id)
        if not version_id:
            errors.append(f"{prefix}.version_id: required")
        elif version_id not in versions_by_id:
            unknown_version_ids.add(version_id)
        if not title:
            errors.append(f"{prefix}.title: required")
        if not overview:
            errors.append(f"{prefix}.overview: required")
        if not problem_statement:
            errors.append(f"{prefix}.problem_statement: required")
        if not evidence_summary:
            errors.append(f"{prefix}.evidence_summary: required")

        version = versions_by_id.get(version_id)
        if version:
            expected_requirement_ids = _list_text(version.get("requirement_ids"))
            if requirement_ids and set(requirement_ids) != set(expected_requirement_ids):
                version_mismatch_errors.append(
                    f"{prefix}.requirement_ids: expected {expected_requirement_ids}, got {requirement_ids}"
                )
            if goals and not _goal_matches_version_goal(goals[0], _text(version.get("goal"))):
                goal_errors.append(f"{prefix}.goals[0]: must exactly match version goal {version_id}")

        finding_ids_for_prd: set[str] = set()
        for requirement_id in requirement_ids:
            requirement = requirements_by_id.get(requirement_id)
            if not requirement:
                unknown_requirement_ids.add(requirement_id)
                continue
            _validate_unsupported_scope(
                prefix=f"{prefix}.{requirement_id}",
                prd_text=" ".join([title, overview, problem_statement, *goals]),
                requirement=requirement,
                unsupported_scope_errors=unsupported_scope_errors,
            )
            requirement_finding_ids = _list_text(requirement.get("finding_ids"))
            if not requirement_finding_ids:
                traceability_errors.append(f"{prefix}.{requirement_id}: no finding_ids")
            for finding_id in requirement_finding_ids:
                finding_ids_for_prd.add(finding_id)
                finding = findings_by_id.get(finding_id)
                if not finding:
                    unknown_finding_ids.add(finding_id)
                    continue
                _validate_finding_chain(
                    prefix=f"{prefix}.{requirement_id}.{finding_id}",
                    finding=finding,
                    issues_by_id=issues_by_id,
                    topics_by_id=topics_by_id,
                    valid_review_ids=valid_review_ids,
                    traceability_errors=traceability_errors,
                )

        if evidence_summary:
            evidence_ids = set(requirement_ids).union(finding_ids_for_prd)
            if not _mentions_any_id(evidence_summary, evidence_ids):
                evidence_summary_errors.append(
                    f"{prefix}.evidence_summary: must cite at least one related requirement_id or finding_id"
                )

        for non_goal_index, non_goal in enumerate(non_goals):
            if _contains_technical_detail(non_goal):
                implementation_errors.append(
                    f"{prefix}.non_goals[{non_goal_index}]: contains implementation detail"
                )
        implementation_text = " ".join(
            [title, overview, problem_statement, evidence_summary, *goals, *risks, *success_metrics]
        )
        if _contains_technical_detail(implementation_text):
            implementation_errors.append(f"{prefix}: contains implementation detail")
        if not success_metrics and not _has_metric_definition_open_question(open_questions):
            metric_errors.append(
                f"{prefix}.success_metrics: empty metrics require an open question for measurable success definition"
            )

        metric_evidence_text = _success_metric_evidence_text(
            version=version or {},
            requirements=[requirements_by_id[requirement_id] for requirement_id in requirement_ids if requirement_id in requirements_by_id],
            findings=[findings_by_id[finding_id] for finding_id in finding_ids_for_prd if finding_id in findings_by_id],
        )
        seen_metrics: set[str] = set()
        for metric_index, metric in enumerate(success_metrics):
            metric_key = _metric_key(metric)
            if metric_key in seen_metrics:
                metric_errors.append(f"{prefix}.success_metrics[{metric_index}]: duplicate metric")
            seen_metrics.add(metric_key)
            if not _is_measurable_metric(metric):
                metric_errors.append(f"{prefix}.success_metrics[{metric_index}]: not measurable")
            if _has_unsupported_numeric_target(metric, metric_evidence_text):
                metric_errors.append(
                    f"{prefix}.success_metrics[{metric_index}]: contains unsupported numeric target"
                )
        _validate_required_open_questions(
            prefix=prefix,
            requirements=[requirements_by_id[requirement_id] for requirement_id in requirement_ids if requirement_id in requirements_by_id],
            version=version or {},
            open_questions=open_questions,
            errors=missing_open_question_errors,
        )

        if (
            prd_id
            and version_id
            and title
            and overview
            and problem_statement
            and evidence_summary
            and goals
            and requirement_ids
        ):
            prds.append(
                PRD(
                    prd_id=prd_id,
                    version_id=version_id,
                    title=title,
                    overview=overview,
                    problem_statement=problem_statement,
                    evidence_summary=evidence_summary,
                    goals=goals,
                    non_goals=non_goals,
                    requirement_ids=requirement_ids,
                    risks=risks,
                    success_metrics=success_metrics,
                    open_questions=open_questions,
                )
            )

    if duplicate_prd_ids:
        return _fail(
            STATUS_DUPLICATE_PRD_ID,
            [f"duplicate prd id {prd_id}" for prd_id in sorted(duplicate_prd_ids)],
            duplicate_prd_ids=sorted(duplicate_prd_ids),
        )
    if unknown_version_ids:
        return _fail(
            STATUS_UNKNOWN_VERSION_ID,
            [f"unknown version id {version_id}" for version_id in sorted(unknown_version_ids)],
            unknown_version_ids=sorted(unknown_version_ids),
        )
    if unknown_requirement_ids:
        return _fail(
            STATUS_UNKNOWN_REQUIREMENT_ID,
            [f"unknown requirement id {requirement_id}" for requirement_id in sorted(unknown_requirement_ids)],
            unknown_requirement_ids=sorted(unknown_requirement_ids),
        )
    if version_mismatch_errors:
        return _fail(STATUS_REQUIREMENT_VERSION_MISMATCH, version_mismatch_errors)
    if unknown_finding_ids:
        return _fail(
            STATUS_UNKNOWN_FINDING_ID,
            [f"unknown finding id {finding_id}" for finding_id in sorted(unknown_finding_ids)],
            unknown_finding_ids=sorted(unknown_finding_ids),
        )
    if traceability_errors:
        return _fail(
            STATUS_TRACEABILITY_MISMATCH,
            traceability_errors,
            traceability_errors=traceability_errors,
        )
    if errors:
        return _fail(STATUS_SCHEMA_VALIDATION_FAILED, errors)
    if goal_errors:
        return _fail(STATUS_GOAL_INCOHERENCE, goal_errors, goal_errors=goal_errors)
    if evidence_summary_errors:
        return _fail(
            STATUS_EVIDENCE_SUMMARY_INVALID,
            evidence_summary_errors,
            evidence_summary_errors=evidence_summary_errors,
        )
    if metric_errors:
        return _fail(
            STATUS_SUCCESS_METRIC_INVALID,
            metric_errors,
            success_metric_errors=metric_errors,
        )
    if implementation_errors:
        return _fail(
            STATUS_PROHIBITED_IMPLEMENTATION_DETAIL,
            implementation_errors,
            implementation_detail_errors=implementation_errors,
        )
    if unsupported_scope_errors:
        return _fail(
            STATUS_UNSUPPORTED_PRODUCT_DIRECTION,
            unsupported_scope_errors,
            unsupported_scope_errors=unsupported_scope_errors,
        )
    if missing_open_question_errors:
        return _fail(
            STATUS_MISSING_OPEN_QUESTION,
            missing_open_question_errors,
            missing_open_question_errors=missing_open_question_errors,
        )
    return PRDValidationResult(status=STATUS_SUCCESS, passed=True, prds=prds)


def _validate_finding_chain(
    *,
    prefix: str,
    finding: dict[str, Any],
    issues_by_id: dict[str, dict[str, Any]],
    topics_by_id: dict[str, dict[str, Any]],
    valid_review_ids: set[str],
    traceability_errors: list[str],
) -> None:
    finding_review_ids = set(_list_text(finding.get("review_ids")))
    if not finding_review_ids:
        traceability_errors.append(f"{prefix}: no finding review evidence")
    for review_id in finding_review_ids:
        if review_id not in valid_review_ids:
            traceability_errors.append(f"{prefix}: finding review id {review_id} is unknown")
    issue_review_ids: set[str] = set()
    for issue_id in _list_text(finding.get("issue_ids")):
        issue = issues_by_id.get(issue_id)
        if not issue:
            traceability_errors.append(f"{prefix}: unknown issue id {issue_id}")
            continue
        issue_review_ids.update(_list_text(issue.get("review_ids")))
        topic_review_ids: set[str] = set()
        for topic_id in _list_text(issue.get("topic_ids")):
            topic = topics_by_id.get(topic_id)
            if not topic:
                traceability_errors.append(f"{prefix}: unknown topic id {topic_id}")
                continue
            topic_review_ids.update(_list_text(topic.get("review_ids")))
        if topic_review_ids and not topic_review_ids.intersection(issue_review_ids):
            traceability_errors.append(f"{prefix}: issue/topic review evidence has no overlap")
    if issue_review_ids and finding_review_ids and not finding_review_ids.intersection(issue_review_ids):
        traceability_errors.append(f"{prefix}: finding/issue review evidence has no overlap")


def _validate_unsupported_scope(
    *,
    prefix: str,
    prd_text: str,
    requirement: dict[str, Any],
    unsupported_scope_errors: list[str],
) -> None:
    scope = validate_product_scope(prd_text, requirement)
    for concept in scope.unsupported_concepts:
        unsupported_scope_errors.append(f"{prefix}: unsupported product direction {concept}")


def _validate_required_open_questions(
    *,
    prefix: str,
    requirements: list[dict[str, Any]],
    version: dict[str, Any],
    open_questions: list[str],
    errors: list[str],
) -> None:
    question_text = " ".join(open_questions).lower()
    version_text = " ".join(
        [
            _text(version.get("name")),
            _text(version.get("goal")),
            _text(version.get("rationale")),
            " ".join(_list_text(version.get("success_metrics"))),
        ]
    )
    for requirement in requirements:
        for decision in _required_open_question_decisions(requirement, version_text=version_text):
            if not any(term in question_text for term in decision["terms"]):
                errors.append(
                    f"{prefix}.open_questions: missing product decision question for "
                    f"{decision['requirement_id']} ({decision['decision']})"
                )


def _required_open_question_decisions(requirement: dict[str, Any], *, version_text: str = "") -> list[dict[str, Any]]:
    requirement_id = _text(requirement.get("requirement_id"))
    text = " ".join(
        [
            _text(requirement.get("title")),
            _text(requirement.get("description")),
            " ".join(_list_text(requirement.get("acceptance_criteria"))),
            " ".join(_list_text(requirement.get("risks"))),
            " ".join(_list_text(requirement.get("success_metrics"))),
            _text(requirement.get("uncertainty")),
            version_text,
        ]
    ).lower()
    decisions: list[dict[str, Any]] = []
    if "free" in text and ("threshold" in text or "proportion" in text or "library" in text or "access" in text):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "decision": "free access threshold or scope",
                "terms": ["free", "threshold", "proportion", "library", "access"],
            }
        )
    if _contains_any_term(text, ["refresh", "cadence", "frequency", "monthly", "update cadence", "content update"]):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "decision": "content refresh cadence or frequency",
                "terms": ["refresh", "cadence", "frequency", "monthly", "update"],
            }
        )
    if _contains_any_term(text, ["support"]) and _contains_any_term(text, ["channel", "channels", "email", "chat", "contact"]):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "decision": "support channel selection",
                "terms": ["support", "channel", "email", "chat", "contact"],
            }
        )
    if _contains_any_term(text, ["large file", "large files"]) and _contains_any_term(text, ["crash", "crashes", "opening", "open"]):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "decision": "large file stability threshold or definition",
                "terms": ["large file", "large files", "crash", "threshold", "size"],
            }
        )
    if "export" in text and "format" in text:
        decisions.append(
            {
                "requirement_id": requirement_id,
                "decision": "export format selection",
                "terms": ["export", "format"],
            }
        )
    if _contains_any_term(text, ["notification", "notifications", "reminder", "reminders"]) and _contains_any_term(
        text, ["late", "duplicate", "on time", "timing", "delivery"]
    ):
        decisions.append(
            {
                "requirement_id": requirement_id,
                "decision": "notification timing and duplication threshold",
                "terms": ["notification", "reminder", "on time", "duplicate", "timing", "delivery"],
            }
        )
    return decisions


def _contains_any_term(text: str, terms: list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if " " in term:
        return term in text
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _fail(
    status: str,
    errors: list[str],
    *,
    unknown_version_ids: list[str] | None = None,
    unknown_requirement_ids: list[str] | None = None,
    unknown_finding_ids: list[str] | None = None,
    traceability_errors: list[str] | None = None,
    evidence_summary_errors: list[str] | None = None,
    goal_errors: list[str] | None = None,
    success_metric_errors: list[str] | None = None,
    implementation_detail_errors: list[str] | None = None,
    duplicate_prd_ids: list[str] | None = None,
    unsupported_scope_errors: list[str] | None = None,
    missing_open_question_errors: list[str] | None = None,
) -> PRDValidationResult:
    return PRDValidationResult(
        status=status,
        passed=False,
        errors=errors,
        unknown_version_ids=unknown_version_ids or [],
        unknown_requirement_ids=unknown_requirement_ids or [],
        unknown_finding_ids=unknown_finding_ids or [],
        traceability_errors=traceability_errors or [],
        evidence_summary_errors=evidence_summary_errors or [],
        goal_errors=goal_errors or [],
        success_metric_errors=success_metric_errors or [],
        implementation_detail_errors=implementation_detail_errors or [],
        duplicate_prd_ids=duplicate_prd_ids or [],
        unsupported_scope_errors=unsupported_scope_errors or [],
        missing_open_question_errors=missing_open_question_errors or [],
    )


def _text_list(value: Any, field_name: str, errors: list[str], *, min_items: int) -> list[str]:
    if not isinstance(value, list) or len(value) < min_items:
        errors.append(f"{field_name}: must contain at least {min_items} item(s)")
        return []
    normalized = [_text(item) for item in value]
    for item in normalized:
        if not item:
            errors.append(f"{field_name}: empty item")
    return normalized


def _text_coherent(left: str, right: str) -> bool:
    left_tokens = _domain_tokens(left)
    right_tokens = _domain_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return bool(left_tokens.intersection(right_tokens))


def _goal_matches_version_goal(prd_goal: str, version_goal: str) -> bool:
    return _normalize_goal_contract(prd_goal) == _normalize_goal_contract(version_goal)


def _normalize_goal_contract(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip())
    return normalized.rstrip(".。!！?？").casefold()


def _domain_tokens(value: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", value.lower()))
    domains = {
        "subscription": {"subscription", "billing", "paywall", "free", "premium", "cancellation", "price"},
        "content": {
            "workout",
            "workouts",
            "exercise",
            "exercises",
            "content",
            "imagery",
            "customization",
            "freshness",
            "library",
            "health",
            "fitness",
            "effective",
            "effectiveness",
            "motivation",
            "motivated",
            "results",
            "routine",
            "instructions",
            "variety",
        },
        "support": {"support", "ads", "advertising", "redirects", "trust"},
    }
    matched: set[str] = set()
    for domain, terms in domains.items():
        if words.intersection(terms):
            matched.add(domain)
    return matched or words


def _mentions_any_id(text: str, ids: set[str]) -> bool:
    return any(identifier in text for identifier in ids)


def _contains_technical_detail(value: str) -> bool:
    normalized = value.lower()
    for term in TECHNICAL_TERMS:
        if term.startswith("."):
            if term in normalized:
                return True
            continue
        for match in re.finditer(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", normalized):
            if _is_product_context_for_technical_term(normalized, term, match.start(), match.end()):
                continue
            return True
    return False


def _is_product_context_for_technical_term(value: str, term: str, start: int, end: int) -> bool:
    if term != "code":
        return False
    context = value[max(0, start - 40) : min(len(value), end + 40)]
    return bool(
        re.search(
            r"\b(email|verification|login|account|recovery|one-time|otp|2fa|two-factor)\s+code(s)?\b",
            context,
        )
        or re.search(
            r"\bcode(s)?\s+(delivery|arrive|arrives|sent|received|expires|expired)\b",
            context,
        )
    )


def _is_measurable_metric(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in GENERIC_METRICS:
        return False
    if re.fullmatch(
        r"(improve|increase|decrease|enhance|boost|raise|reduce)\s+(user\s+)?(experience|satisfaction|engagement|trust|retention)\.?",
        normalized,
    ):
        return False
    if re.fullmatch(r"(提高|提升|改善|增强)(用户体验|用户满意度|满意度|参与度|留存)\。?", normalized):
        return False
    if re.search(
        r"\b(user\s+)?(adoption|usage|engagement)\s+(of|with|for|among)\s+[\w -]+",
        normalized,
    ):
        return True
    return bool(
        re.search(
            r"\d|%|percentage|ratio|rate|count|number|score|rating|survey|user-reported|time|duration|average|median|completion|retention|conversion|increase|decrease|reduction|complaints|reports|incidents|reviews",
            normalized,
        )
    )


def _has_unsupported_numeric_target(value: str, evidence_text: str = "") -> bool:
    metric_percentages = _percentage_values(value)
    if not metric_percentages:
        return False
    evidence_percentages = _percentage_values(evidence_text)
    return any(percentage not in evidence_percentages for percentage in metric_percentages)


def _percentage_values(value: str) -> set[str]:
    values: set[str] = set()
    for match in re.finditer(r"\b(\d+(?:\.\d+)?)\s*%", value.lower()):
        value_text = match.group(1)
        if "." in value_text:
            value_text = value_text.rstrip("0").rstrip(".")
        values.add(value_text)
    return values


def _has_metric_definition_open_question(open_questions: list[str]) -> bool:
    normalized = " ".join(open_questions).lower()
    return bool(
        re.search(
            r"metric|measure|measurement|measurable|success|target|kpi|outcome|指标|衡量|度量|成功标准|目标",
            normalized,
        )
    )


def _success_metric_evidence_text(
    *,
    version: dict[str, Any],
    requirements: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> str:
    parts: list[str] = [
        _text(version.get("name")),
        _text(version.get("goal")),
        _text(version.get("rationale")),
        " ".join(_list_text(version.get("risks"))),
        " ".join(_list_text(version.get("success_metrics"))),
    ]
    for requirement in requirements:
        parts.extend(
            [
                _text(requirement.get("title")),
                _text(requirement.get("description")),
                " ".join(_list_text(requirement.get("acceptance_criteria"))),
                " ".join(_list_text(requirement.get("risks"))),
                " ".join(_list_text(requirement.get("success_metrics"))),
                _text(requirement.get("uncertainty")),
            ]
        )
    for finding in findings:
        parts.extend(
            [
                _text(finding.get("title")),
                _text(finding.get("statement")),
                _text(finding.get("summary")),
                _text(finding.get("uncertainty")),
            ]
        )
    return " ".join(parts)


def _metric_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())


def _list_text(value: Any) -> list[str]:
    return [_text(item) for item in value] if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
