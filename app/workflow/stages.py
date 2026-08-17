"""Workflow stage definitions for the analysis pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass


STAGE_SCOPE = "scope"
STAGE_COLLECTION = "collection"
STAGE_PROCESSING = "processing"
STAGE_TOPIC_DISCOVERY = "topic_discovery"
STAGE_ISSUE_CONSOLIDATION = "issue_consolidation"
STAGE_FINDING_GENERATION = "finding_generation"
STAGE_REQUIREMENT_GENERATION = "requirement_generation"
STAGE_ROADMAP = "roadmap"
STAGE_PRD = "prd"
STAGE_TEST_CASES = "test_cases"
STAGE_TRACEABILITY = "traceability"

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"

REVISION_PROPOSED = "proposed"
REVISION_APPLIED = "applied"
REVISION_REJECTED = "rejected"

ERROR_VALIDATION = "validation_error"
ERROR_PROVIDER = "provider_error"
ERROR_TIMEOUT = "timeout"
ERROR_AUTH = "auth_error"
ERROR_INPUT = "input_error"
ERROR_DATA = "data_error"
ERROR_UNKNOWN = "unknown_error"

VALID_STAGE_STATUSES = {
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_SKIPPED,
}
VALID_RUN_STATUSES = {RUN_QUEUED, RUN_RUNNING, RUN_COMPLETED, RUN_FAILED}
VALID_REVISION_STATUSES = {REVISION_PROPOSED, REVISION_APPLIED, REVISION_REJECTED}
VALID_ERROR_TYPES = {
    ERROR_VALIDATION,
    ERROR_PROVIDER,
    ERROR_TIMEOUT,
    ERROR_AUTH,
    ERROR_INPUT,
    ERROR_DATA,
    ERROR_UNKNOWN,
}


@dataclass(frozen=True)
class WorkflowStageDefinition:
    stage: str
    label_zh: str
    label_en: str
    order: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


WORKFLOW_STAGES: tuple[WorkflowStageDefinition, ...] = (
    WorkflowStageDefinition(STAGE_SCOPE, "分析范围确定", "Scope", 1),
    WorkflowStageDefinition(STAGE_COLLECTION, "评论采集", "Review Collection", 2),
    WorkflowStageDefinition(STAGE_PROCESSING, "评论清洗与处理", "Review Processing", 3),
    WorkflowStageDefinition(STAGE_TOPIC_DISCOVERY, "动态主题发现", "Topic Discovery", 4),
    WorkflowStageDefinition(STAGE_ISSUE_CONSOLIDATION, "问题整合", "Issue Consolidation", 5),
    WorkflowStageDefinition(STAGE_FINDING_GENERATION, "证据驱动 Finding", "Finding Generation", 6),
    WorkflowStageDefinition(STAGE_REQUIREMENT_GENERATION, "产品需求生成", "Requirement Generation", 7),
    WorkflowStageDefinition(STAGE_ROADMAP, "版本规划", "Roadmap", 8),
    WorkflowStageDefinition(STAGE_PRD, "PRD 生成", "PRD Generation", 9),
    WorkflowStageDefinition(STAGE_TEST_CASES, "测试用例生成", "Test Case Generation", 10),
    WorkflowStageDefinition(STAGE_TRACEABILITY, "最终追溯验证", "Traceability", 11),
)

WORKFLOW_STAGE_IDS = tuple(stage.stage for stage in WORKFLOW_STAGES)


def get_stage_definition(stage_id: str) -> WorkflowStageDefinition:
    for stage in WORKFLOW_STAGES:
        if stage.stage == stage_id:
            return stage
    raise ValueError(f"Unknown workflow stage: {stage_id}")
