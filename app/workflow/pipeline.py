"""Adapters that connect workflow stages to existing Phase 1-8 modules."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.analysis_intent import (
    ANALYSIS_FOCUS_MIXED,
    ANALYSIS_FOCUS_POSITIVE_FEEDBACK,
    DEFAULT_ANALYSIS_FOCUS,
    normalize_analysis_focus,
)
from app.analysis_scope import (
    ScopeFilterResult,
    apply_analysis_scope,
    normalize_constraints,
    validate_constraints,
    write_scope_outputs,
)
from app.apify_provider import ApifyReviewProvider, save_apify_artifacts
from app.final_validation import run_final_validation
from app.imports import fetch_imported_reviews, save_import_artifacts
from app.review_processing import (
    ProcessingResult,
    build_processing_report,
    build_statistics,
    load_reviews,
    process_reviews,
    write_processing_outputs,
)
from app.workflow.stages import (
    ERROR_AUTH,
    ERROR_DATA,
    ERROR_PROVIDER,
    ERROR_TIMEOUT,
    ERROR_UNKNOWN,
    ERROR_VALIDATION,
    STAGE_COLLECTION,
    STAGE_FINDING_GENERATION,
    STAGE_ISSUE_CONSOLIDATION,
    STAGE_PRD,
    STAGE_PROCESSING,
    STAGE_REQUIREMENT_GENERATION,
    STAGE_ROADMAP,
    STAGE_SCOPE,
    STAGE_TEST_CASES,
    STAGE_TOPIC_DISCOVERY,
    STAGE_TRACEABILITY,
)
from app.workflow.validation import VALIDATION_PASS, split_final_validation_report


ANALYSIS_DIR = Path("artifacts/analysis")
ANALYSIS_SCOPE_DIR = Path("artifacts/analysis_scope")
NORMALIZED_REVIEWS = Path("artifacts/normalized/apify/normalized_reviews.json")
IMPORTED_NORMALIZED_REVIEWS = Path("artifacts/normalized/import/normalized_reviews.json")
PROCESSED_REVIEWS = Path("artifacts/processed/reviews.json")
US_TERRITORY = "US"
REQUESTED_REVIEW_LIMIT = 50
FINDING_STAGE_GOAL = (
    "基于 eligible Issues 和真实 Review Evidence 生成证据驱动 Findings；"
    "support review_ids 与 conflicting_review_ids 必须互不重叠。"
)
POSITIVE_FINDING_STAGE_GOAL = (
    "基于 eligible positive_feedback Issues 和真实 Review Evidence 生成证据驱动 Positive Findings；"
    "只描述用户认可、满意、愿意保留的体验，不要将正向反馈改写成产品问题。"
)
MIXED_FINDING_STAGE_GOAL = (
    "基于 eligible Issues 和真实 Review Evidence 同时生成 product_problem Findings 与 positive_feedback Findings；"
    "两类证据必须保持类型区分，support review_ids 与 conflicting_review_ids 必须互不重叠。"
)
REQUIREMENT_STAGE_GOAL = (
    "基于已验证 Findings 生成证据驱动的产品需求；只描述用户可感知的产品行为，"
    "不要描述技术实现、函数、接口、数据库、代码或框架。"
    "Use product behavior wording only; never use the words function, functions, functionality, API, endpoint, database, code, class, component, React, or Vue."
)
POSITIVE_REQUIREMENT_STAGE_GOAL = (
    "基于已验证 Positive Findings 生成证据驱动的保留型产品需求；"
    "只描述需要保留或强化的用户可感知产品行为，不要将用户满意体验写成待修复问题。"
    "Use product behavior wording only; never use the words function, functions, functionality, API, endpoint, database, code, class, component, React, or Vue."
)
MIXED_REQUIREMENT_STAGE_GOAL = (
    "基于已验证 Findings 生成证据驱动的产品需求；problem Findings 生成问题解决需求，"
    "positive_feedback Findings 生成保留型需求，并保持 requirement_type 区分。"
    "Use product behavior wording only; never use the words function, functions, functionality, API, endpoint, database, code, class, component, React, or Vue."
)
ROADMAP_STAGE_GOAL = "基于已验证 Requirements、优先级与证据报告生成版本路线图。"
PRD_STAGE_GOAL = "基于已验证 Roadmap Version、Requirements、Findings 与 Evidence 生成 PRD。"
TEST_CASE_STAGE_GOAL = "为已验证需求和验收标准生成可执行测试用例"


class WorkflowStageExecutionError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        error_type: str,
        message: str,
        artifacts: list[str] | None = None,
        warnings: list[str] | None = None,
        summary: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.error_type = error_type
        self.message = _sanitize(message)
        self.artifacts = artifacts or []
        self.warnings = warnings or []
        self.summary = summary or {}


@dataclass(frozen=True)
class WorkflowStageExecutionResult:
    stage: str
    message: str
    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


class BackendPipelineRunner:
    """Execute the real backend pipeline by reusing existing modules and CLIs."""

    def run_stage(self, *, stage: str, context: dict[str, Any]) -> WorkflowStageExecutionResult:
        started = time.perf_counter()
        result = self._run_stage(stage=stage, context=context)
        return WorkflowStageExecutionResult(
            stage=result.stage,
            message=result.message,
            artifacts=result.artifacts,
            warnings=result.warnings,
            summary=result.summary,
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )

    def _run_stage(self, *, stage: str, context: dict[str, Any]) -> WorkflowStageExecutionResult:
        if stage == STAGE_SCOPE:
            return self._scope(context)
        if stage == STAGE_COLLECTION:
            return self._collection(context)
        if stage == STAGE_PROCESSING:
            return self._processing(context)
        if stage == STAGE_TOPIC_DISCOVERY:
            return self._command_stage(
                stage=stage,
                command=[sys.executable, "-m", "app.discover_topics", "--goal", context["analysis_goal"]],
                artifacts=[
                    "artifacts/analysis/topic_discovery_raw.json",
                    "artifacts/analysis/topics.json",
                    "artifacts/analysis/topic_validation.json",
                ],
                summary_loader=_topic_summary,
            )
        if stage == STAGE_ISSUE_CONSOLIDATION:
            issue_result = self._command_stage(
                stage=stage,
                command=[
                    sys.executable,
                    "-m",
                    "app.consolidate_issues",
                    "--provider",
                    "deepseek",
                    "--goal",
                    context["analysis_goal"],
                    "--analysis-focus",
                    _analysis_focus(context),
                ],
                artifacts=[
                    "artifacts/analysis/issue_consolidation_raw.json",
                    "artifacts/analysis/issues.json",
                    "artifacts/analysis/issue_validation.json",
                ],
                summary_loader=_issue_summary,
            )
            classification = self._command_stage(
                stage=stage,
                    command=[
                        sys.executable,
                        "-m",
                        "app.classify_issues",
                        "--analysis-focus",
                        _analysis_focus(context),
                    ],
                artifacts=[
                    "artifacts/analysis/issue_classification.json",
                    "artifacts/analysis/finding_eligibility.json",
                ],
                summary_loader=_classification_summary,
            )
            return WorkflowStageExecutionResult(
                stage=stage,
                message="Issue consolidation and deterministic eligibility gate completed.",
                artifacts=issue_result.artifacts + classification.artifacts,
                warnings=issue_result.warnings + classification.warnings,
                summary={**issue_result.summary, **classification.summary},
            )
        if stage == STAGE_FINDING_GENERATION:
            return self._command_stage(
                stage=stage,
                command=[
                    sys.executable,
                    "-m",
                    "app.find_findings",
                    "--provider",
                    "deepseek",
                    "--goal",
                    _finding_stage_goal(context),
                    "--analysis-focus",
                    _analysis_focus(context),
                ],
                artifacts=[
                    "artifacts/analysis/finding_generation_raw.json",
                    "artifacts/analysis/findings.json",
                    "artifacts/analysis/finding_validation.json",
                    "artifacts/analysis/evidence_report.json",
                ],
                summary_loader=_finding_summary,
            )
        if stage == STAGE_REQUIREMENT_GENERATION:
            return self._command_stage(
                stage=stage,
                command=[
                    sys.executable,
                    "-m",
                    "app.generate_requirements",
                    "--provider",
                    "deepseek",
                    "--goal",
                    _requirement_stage_goal(context),
                    "--analysis-focus",
                    _analysis_focus(context),
                ],
                artifacts=[
                    "artifacts/analysis/requirement_generation_raw.json",
                    "artifacts/analysis/requirements.json",
                    "artifacts/analysis/requirement_validation.json",
                    "artifacts/analysis/priority_report.json",
                ],
                summary_loader=_requirement_summary,
            )
        if stage == STAGE_ROADMAP:
            return self._command_stage(
                stage=stage,
                command=[
                    sys.executable,
                    "-m",
                    "app.generate_roadmap",
                    "--provider",
                    "deepseek",
                    "--goal",
                    ROADMAP_STAGE_GOAL,
                ],
                artifacts=[
                    "artifacts/analysis/roadmap_generation_raw.json",
                    "artifacts/analysis/roadmap.json",
                    "artifacts/analysis/roadmap_validation.json",
                ],
                summary_loader=_roadmap_summary,
            )
        if stage == STAGE_PRD:
            return self._command_stage(
                stage=stage,
                command=[
                    sys.executable,
                    "-m",
                    "app.generate_prd",
                    "--provider",
                    "deepseek",
                    "--goal",
                    PRD_STAGE_GOAL,
                ],
                artifacts=[
                    "artifacts/analysis/prd_generation_raw.json",
                    "artifacts/analysis/prds.json",
                    "artifacts/analysis/prd_validation.json",
                ],
                summary_loader=_prd_summary,
            )
        if stage == STAGE_TEST_CASES:
            return self._command_stage(
                stage=stage,
                command=[
                    sys.executable,
                    "-m",
                    "app.generate_test_cases",
                    "--provider",
                    "deepseek",
                    "--goal",
                    TEST_CASE_STAGE_GOAL,
                ],
                artifacts=[
                    "artifacts/analysis/test_case_generation_raw.json",
                    "artifacts/analysis/test_cases.json",
                    "artifacts/analysis/test_case_validation.json",
                    "artifacts/analysis/test_coverage.json",
                ],
                summary_loader=_test_case_summary,
            )
        if stage == STAGE_TRACEABILITY:
            return self._traceability()
        raise WorkflowStageExecutionError(
            stage=stage,
            error_type=ERROR_UNKNOWN,
            message=f"Unsupported workflow stage: {stage}",
        )

    def _scope(self, context: dict[str, Any]) -> WorkflowStageExecutionResult:
        scope_validation = validate_constraints(context.get("constraints"))
        summary = {
            "storefront": context["storefront"],
            "app_id": context["app_id"],
            "analysis_goal": context["analysis_goal"],
            "analysis_focus": _analysis_focus(context),
            "constraints": scope_validation.constraints if scope_validation.passed else normalize_constraints(context.get("constraints")),
            "scope_validation": scope_validation.to_dict(),
            "review_source": _review_source_label(context),
            "review_territory": _review_territory_label(context),
        }
        if not scope_validation.passed:
            empty_scope_result = ScopeFilterResult(
                input_count=0,
                selected_count=0,
                excluded_count=0,
                constraints=normalize_constraints(context.get("constraints")),
                selected_reviews=[],
                excluded_review_ids=[],
                validation=scope_validation,
            )
            paths = write_scope_outputs(empty_scope_result, output_dir=ANALYSIS_SCOPE_DIR)
            raise WorkflowStageExecutionError(
                stage=STAGE_SCOPE,
                error_type=ERROR_VALIDATION,
                message="Scope Validation failed: " + "; ".join(scope_validation.errors),
                artifacts=[str(path) for path in paths.values()],
                summary=summary,
            )
        if context.get("source_type") in {"json", "csv"}:
            summary["app_context"] = context["app_url"]
            summary["import_metadata"] = context.get("import_metadata", {})
            return WorkflowStageExecutionResult(stage=STAGE_SCOPE, message="Import scope metadata created.", summary=summary)
        if context["storefront"] != US_TERRITORY:
            warning = "Input storefront differs from required review territory; collection will use US reviews."
            return WorkflowStageExecutionResult(
                stage=STAGE_SCOPE,
                message="Scope metadata created.",
                warnings=[warning],
                summary=summary,
            )
        return WorkflowStageExecutionResult(stage=STAGE_SCOPE, message="Scope metadata created.", summary=summary)

    def _collection(self, context: dict[str, Any]) -> WorkflowStageExecutionResult:
        if context.get("source_type") in {"json", "csv"}:
            return self._import_collection(context)

        load_dotenv(override=False)
        api_token = os.environ.get("APIFY_API_TOKEN", "")
        if not api_token:
            raise WorkflowStageExecutionError(
                stage=STAGE_COLLECTION,
                error_type=ERROR_AUTH,
                message="Missing API Key: APIFY_API_TOKEN is not configured.",
            )
        try:
            provider = ApifyReviewProvider(api_token=api_token, territory=US_TERRITORY)
            result = provider.fetch_reviews(context["app_id"], max_reviews=REQUESTED_REVIEW_LIMIT)
            paths = save_apify_artifacts(result)
        except Exception as exc:
            raise WorkflowStageExecutionError(
                stage=STAGE_COLLECTION,
                error_type=_classify_exception(exc),
                message=f"Collection failed: {exc!r}",
            ) from exc
        artifacts = [str(path) for path in paths]
        warnings = [error.message for error in result.errors]
        summary = {
            "provider": result.provider,
            "app_id": context["app_id"],
            "territory": US_TERRITORY,
            "requested_limit": REQUESTED_REVIEW_LIMIT,
            "actual_count": len(result.reviews),
            "limitations": result.dataset_metadata.limitations if result.dataset_metadata else [],
        }
        if not result.reviews:
            raise WorkflowStageExecutionError(
                stage=STAGE_COLLECTION,
                error_type=ERROR_DATA,
                message="Collection returned no normalized reviews.",
                artifacts=artifacts,
                warnings=warnings,
                summary=summary,
            )
        return WorkflowStageExecutionResult(
            stage=STAGE_COLLECTION,
            message="US App Store reviews collected through Apify.",
            artifacts=artifacts,
            warnings=warnings,
            summary=summary,
        )

    def _import_collection(self, context: dict[str, Any]) -> WorkflowStageExecutionResult:
        source_type = context.get("source_type", "")
        import_path = Path(context.get("import_path", ""))
        import_metadata = dict(context.get("import_metadata") or {})
        if not import_path.exists() or not import_path.is_file():
            raise WorkflowStageExecutionError(
                stage=STAGE_COLLECTION,
                error_type=ERROR_DATA,
                message="Import dataset file is unavailable.",
            )
        try:
            max_reviews = int(import_metadata.get("record_count") or REQUESTED_REVIEW_LIMIT)
            result = fetch_imported_reviews(
                source_type=source_type,
                path=import_path,
                app_id=context.get("app_id", ""),
                max_reviews=max_reviews,
            )
            if result.errors:
                first_error = result.errors[0]
                raise ValueError(first_error.raw_error or first_error.message)
            if not result.reviews:
                raise ValueError("Import provider returned no normalized reviews.")
            metadata = {
                **import_metadata,
                "provider": result.provider,
                "coverage": result.coverage,
                "actual_count": len(result.reviews),
            }
            paths = save_import_artifacts(result=result, metadata=metadata)
        except Exception as exc:
            raise WorkflowStageExecutionError(
                stage=STAGE_COLLECTION,
                error_type=ERROR_DATA,
                message=f"Import collection failed: {exc!r}",
            ) from exc
        return WorkflowStageExecutionResult(
            stage=STAGE_COLLECTION,
            message=f"{metadata.get('display_source', 'Imported dataset')} loaded into Unified Review Schema.",
            artifacts=[str(path) for path in paths],
            warnings=list(metadata.get("limitations", [])),
            summary={
                "provider": result.provider,
                "source_type": source_type,
                "display_source": metadata.get("display_source"),
                "app_id": metadata.get("app_id") or context.get("app_id"),
                "territory": metadata.get("territory"),
                "record_count": metadata.get("record_count"),
                "valid_count": metadata.get("valid_count"),
                "invalid_count": metadata.get("invalid_count"),
                "actual_count": len(result.reviews),
                "limitations": metadata.get("limitations", []),
                "filename": metadata.get("filename"),
            },
        )

    def _processing(self, context: dict[str, Any]) -> WorkflowStageExecutionResult:
        input_path = IMPORTED_NORMALIZED_REVIEWS if context.get("source_type") in {"json", "csv"} else NORMALIZED_REVIEWS
        try:
            reviews = load_reviews(input_path)
            result = process_reviews(reviews)
            full_paths = write_processing_outputs(result)
            all_paths = _copy_full_processing_outputs(full_paths)
            scope_result = apply_analysis_scope(
                [asdict(review) for review in result.reviews],
                context.get("constraints"),
            )
            scope_paths = write_scope_outputs(scope_result, output_dir=ANALYSIS_SCOPE_DIR)
            if not scope_result.validation.passed:
                raise WorkflowStageExecutionError(
                    stage=STAGE_PROCESSING,
                    error_type=ERROR_VALIDATION,
                    message="Scope Validation failed: " + "; ".join(scope_result.validation.errors),
                    artifacts=[str(path) for path in {**all_paths, **scope_paths}.values()],
                    summary=_scope_processing_summary(result, scope_result),
                )
            selected_result = _selected_processing_result(result, scope_result)
            selected_paths = write_processing_outputs(selected_result)
        except Exception as exc:
            if isinstance(exc, WorkflowStageExecutionError):
                raise exc
            raise WorkflowStageExecutionError(
                stage=STAGE_PROCESSING,
                error_type=ERROR_DATA,
                message=f"Review processing failed: {exc!r}",
            ) from exc
        paths = {**selected_paths, **all_paths, **scope_paths}
        return WorkflowStageExecutionResult(
            stage=STAGE_PROCESSING,
            message="Reviews processed with deterministic Phase 1 pipeline.",
            artifacts=[str(path) for path in paths.values()],
            summary=_scope_processing_summary(result, scope_result, selected_result),
        )

    def _traceability(self) -> WorkflowStageExecutionResult:
        try:
            result = run_final_validation(root=Path("."))
        except Exception as exc:
            raise WorkflowStageExecutionError(
                stage=STAGE_TRACEABILITY,
                error_type=ERROR_VALIDATION,
                message=f"Final traceability validation failed: {exc!r}",
            ) from exc
        report_path = ANALYSIS_DIR / "final_validation_report.json"
        ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
        report = result.to_dict()
        validation_split = split_final_validation_report(report)
        report["runtime_validation_status"] = validation_split.runtime_validation_status
        report["submission_validation_status"] = validation_split.submission_validation_status
        report["submission_blockers"] = validation_split.submission_blockers
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = _traceability_summary(report)
        artifacts = [str(report_path)]
        warnings = result.non_blocking_issues + validation_split.warnings
        if validation_split.runtime_validation_status != VALIDATION_PASS:
            raise WorkflowStageExecutionError(
                stage=STAGE_TRACEABILITY,
                error_type=ERROR_VALIDATION,
                message="Runtime traceability validation did not pass.\n"
                + "\n".join(f"- {item}" for item in validation_split.runtime_errors),
                artifacts=artifacts,
                warnings=warnings,
                summary=summary,
            )
        return WorkflowStageExecutionResult(
            stage=STAGE_TRACEABILITY,
            message="Final traceability validation completed.",
            artifacts=artifacts,
            warnings=warnings,
            summary=summary,
        )

    def _command_stage(
        self,
        *,
        stage: str,
        command: list[str],
        artifacts: list[str],
        summary_loader,
    ) -> WorkflowStageExecutionResult:
        load_dotenv(override=False)
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                timeout=_stage_timeout_seconds(stage),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkflowStageExecutionError(
                stage=stage,
                error_type=ERROR_TIMEOUT,
                message=f"Stage timed out after {exc.timeout} seconds.",
            ) from exc
        stdout = _sanitize(completed.stdout)
        stderr = _sanitize(completed.stderr)
        if completed.returncode != 0:
            raise WorkflowStageExecutionError(
                stage=stage,
                error_type=_classify_command_output(stdout + "\n" + stderr),
                message=_failure_message(stage, completed.returncode, stdout, stderr),
                artifacts=[path for path in artifacts if Path(path).exists()],
                summary={"stdout": stdout[-4000:], "stderr": stderr[-2000:]},
            )
        summary = summary_loader()
        summary["elapsed_command_seconds"] = round(time.perf_counter() - started, 3)
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} completed.",
            artifacts=[path for path in artifacts if Path(path).exists()],
            summary=summary,
        )


def _topic_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "topic_discovery_raw.json")
    topics = _load_json(ANALYSIS_DIR / "topics.json").get("topics", [])
    validation = _load_json(ANALYSIS_DIR / "topic_validation.json")
    return {
        "topic_count": len(topics),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
    }


def _issue_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "issue_consolidation_raw.json")
    issues_payload = _load_json(ANALYSIS_DIR / "issues.json")
    validation = _load_json(ANALYSIS_DIR / "issue_validation.json")
    return {
        "issue_count": len(issues_payload.get("issues", [])),
        "unmerged_topic_count": len(issues_payload.get("unmerged_topic_ids", [])),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
    }


def _classification_summary() -> dict[str, Any]:
    classification = _load_json(ANALYSIS_DIR / "issue_classification.json")
    eligibility = _load_json(ANALYSIS_DIR / "finding_eligibility.json")
    eligible = [item for item in eligibility.get("eligibility", []) if item.get("eligible_for_finding") is True]
    ineligible = [item for item in eligibility.get("eligibility", []) if item.get("eligible_for_finding") is False]
    return {
        "classification_count": len(classification.get("classifications", [])),
        "analysis_focus": eligibility.get("analysis_focus") or classification.get("analysis_focus"),
        "eligible_issue_count": len(eligible),
        "ineligible_issue_count": len(ineligible),
    }


def _finding_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "finding_generation_raw.json")
    findings = _load_json(ANALYSIS_DIR / "findings.json").get("findings", [])
    validation = _load_json(ANALYSIS_DIR / "finding_validation.json")
    evidence = _load_json(ANALYSIS_DIR / "evidence_report.json").get("evidence_reports", [])
    return {
        "finding_count": len(findings),
        "finding_type_counts": _count_by(findings, "finding_type"),
        "evidence_report_count": len(evidence),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
    }


def _requirement_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "requirement_generation_raw.json")
    requirements = _load_json(ANALYSIS_DIR / "requirements.json").get("requirements", [])
    validation = _load_json(ANALYSIS_DIR / "requirement_validation.json")
    priority = _load_json(ANALYSIS_DIR / "priority_report.json").get("priority_report", [])
    json_recovery = raw.get("json_recovery") if isinstance(raw.get("json_recovery"), dict) else {}
    return {
        "requirement_count": len(requirements),
        "requirement_type_counts": _count_by(requirements, "requirement_type"),
        "priority_count": len(priority),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
        "retry_attempted": json_recovery.get("retry_attempted", False),
        "retry_success": json_recovery.get("retry_success", False),
    }


def _roadmap_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "roadmap_generation_raw.json")
    roadmap = _load_json(ANALYSIS_DIR / "roadmap.json")
    validation = _load_json(ANALYSIS_DIR / "roadmap_validation.json")
    return {
        "version_count": len(roadmap.get("versions", [])),
        "roadmap_item_count": len(roadmap.get("roadmap_items", [])),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
    }


def _prd_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "prd_generation_raw.json")
    prds = _load_json(ANALYSIS_DIR / "prds.json").get("prds", [])
    validation = _load_json(ANALYSIS_DIR / "prd_validation.json")
    return {
        "prd_count": len(prds),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
    }


def _test_case_summary() -> dict[str, Any]:
    raw = _load_json(ANALYSIS_DIR / "test_case_generation_raw.json")
    test_cases = _load_json(ANALYSIS_DIR / "test_cases.json").get("test_cases", [])
    validation = _load_json(ANALYSIS_DIR / "test_case_validation.json")
    coverage = _load_json(ANALYSIS_DIR / "test_coverage.json")
    return {
        "test_case_count": len(test_cases),
        "validation": validation.get("status"),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
        "requirement_coverage": coverage.get("requirement_coverage"),
        "acceptance_criteria_coverage": coverage.get("acceptance_criteria_coverage"),
    }


def _analysis_focus(context: dict[str, Any]) -> str:
    return normalize_analysis_focus(context.get("analysis_focus") or DEFAULT_ANALYSIS_FOCUS)


def _finding_stage_goal(context: dict[str, Any]) -> str:
    focus = _analysis_focus(context)
    if focus == ANALYSIS_FOCUS_POSITIVE_FEEDBACK:
        return POSITIVE_FINDING_STAGE_GOAL
    if focus == ANALYSIS_FOCUS_MIXED:
        return MIXED_FINDING_STAGE_GOAL
    return FINDING_STAGE_GOAL


def _requirement_stage_goal(context: dict[str, Any]) -> str:
    focus = _analysis_focus(context)
    if focus == ANALYSIS_FOCUS_POSITIVE_FEEDBACK:
        return POSITIVE_REQUIREMENT_STAGE_GOAL
    if focus == ANALYSIS_FOCUS_MIXED:
        return MIXED_REQUIREMENT_STAGE_GOAL
    return REQUIREMENT_STAGE_GOAL


def _traceability_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "forward_traceability": report.get("forward_traceability"),
        "backward_traceability": report.get("backward_traceability"),
        "artifact_consistency": report.get("artifact_consistency"),
        "evidence_traceability": report.get("evidence_traceability"),
        "explicit_test_case_review_link": report.get("explicit_test_case_review_link"),
        "statistics_model_separation": report.get("statistics_model_separation"),
        "failure_state_audit": report.get("failure_state_audit"),
        "uncertainty_conflict_audit": report.get("uncertainty_conflict_audit"),
        "ai_deterministic_boundary": report.get("ai_deterministic_boundary"),
        "generalization": report.get("generalization"),
        "exam_requirement_coverage": report.get("exam_requirement_coverage"),
        "downstream_safety": report.get("downstream_safety"),
        "runtime_validation_status": report.get("runtime_validation_status"),
        "submission_validation_status": report.get("submission_validation_status"),
        "submission_blockers": report.get("submission_blockers", []),
        "critical_issue_count": len(report.get("critical_issues", [])),
        "missing_final_deliverable_count": len(report.get("missing_final_deliverables", [])),
        "counts": report.get("counts", {}),
    }


def _copy_full_processing_outputs(paths: dict[str, Path]) -> dict[str, Path]:
    suffixes = {
        "reviews_json": "reviews_all.json",
        "reviews_csv": "reviews_all.csv",
        "statistics": "statistics_all.json",
        "processing_report": "processing_report_all.json",
    }
    copied: dict[str, Path] = {}
    for key, filename in suffixes.items():
        source = paths.get(key)
        if not source or not source.exists():
            continue
        target = source.with_name(filename)
        shutil.copy2(source, target)
        copied[f"{key}_all"] = target
    return copied


def _selected_processing_result(result: ProcessingResult, scope_result: ScopeFilterResult) -> ProcessingResult:
    selected_indexes = {
        review.get("original_index")
        for review in scope_result.selected_reviews
        if isinstance(review.get("original_index"), int)
    }
    selected_reviews = [review for review in result.reviews if review.original_index in selected_indexes]
    statistics = build_statistics(selected_reviews)
    report = build_processing_report(
        selected_reviews,
        processing_timestamp=result.report.processing_timestamp,
        near_duplicate_threshold=result.report.near_duplicate_threshold,
    )
    return ProcessingResult(reviews=selected_reviews, statistics=statistics, report=report)


def _scope_processing_summary(
    full_result: ProcessingResult,
    scope_result: ScopeFilterResult,
    selected_result: ProcessingResult | None = None,
) -> dict[str, Any]:
    stats_source = selected_result or full_result
    return {
        "input_count": full_result.report.input_count,
        "selected_count": scope_result.selected_count,
        "excluded_count": scope_result.excluded_count,
        "constraints": scope_result.constraints,
        "scope_validation": scope_result.validation.to_dict(),
        "valid_count": stats_source.report.valid_count,
        "retained_count": stats_source.report.retained_count,
        "duplicate_count": stats_source.report.exact_duplicate_count,
        "language_distribution": stats_source.statistics.get("language_distribution", {}),
        "statistics": {
            "total": stats_source.statistics.get("total"),
            "average_rating": stats_source.statistics.get("average_rating"),
            "rating_distribution": stats_source.statistics.get("rating_distribution"),
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(key) or "unspecified"
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _review_source_label(context: dict[str, Any]) -> str:
    source_type = context.get("source_type")
    if source_type == "json":
        return "imported_json"
    if source_type == "csv":
        return "imported_csv"
    return "apify"


def _review_territory_label(context: dict[str, Any]) -> str:
    if context.get("source_type") in {"json", "csv"}:
        metadata = context.get("import_metadata") or {}
        return str(metadata.get("territory") or "Unknown / Not provided")
    return US_TERRITORY


def _stage_timeout_seconds(stage: str) -> int:
    if stage in {STAGE_TOPIC_DISCOVERY, STAGE_ISSUE_CONSOLIDATION, STAGE_FINDING_GENERATION}:
        return 180
    if stage in {STAGE_REQUIREMENT_GENERATION, STAGE_ROADMAP, STAGE_PRD, STAGE_TEST_CASES}:
        return 240
    return 120


def _classify_exception(exc: Exception) -> str:
    text = repr(exc).lower()
    if "api key" in text or "authentication" in text or "unauthorized" in text:
        return ERROR_AUTH
    if "timeout" in text or "timed out" in text:
        return ERROR_TIMEOUT
    if "validation" in text:
        return ERROR_VALIDATION
    if "provider" in text or "apify" in text:
        return ERROR_PROVIDER
    return ERROR_UNKNOWN


def _classify_command_output(output: str) -> str:
    normalized = output.lower()
    if "missing api key" in normalized or "authentication error" in normalized:
        return ERROR_AUTH
    if "timeout" in normalized:
        return ERROR_TIMEOUT
    if "validation" in normalized:
        return ERROR_VALIDATION
    if "model request error" in normalized or "provider" in normalized or "rate limit" in normalized:
        return ERROR_PROVIDER
    return ERROR_UNKNOWN


def _failure_message(stage: str, returncode: int, stdout: str, stderr: str) -> str:
    details = "\n".join(part for part in (stdout[-3000:], stderr[-1000:]) if part.strip())
    return f"{stage} failed with exit code {returncode}.\n{details}".strip()


def _sanitize(value: str) -> str:
    sanitized = value
    for key in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "APIFY_API_TOKEN", "APPSTORE_PRIVATE_KEY"):
        sanitized = sanitized.replace(os.environ.get(key, ""), "[REDACTED_SECRET]") if os.environ.get(key) else sanitized
        sanitized = sanitized.replace(key, f"{key}=<redacted>")
    return sanitized
