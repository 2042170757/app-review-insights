"""Chinese display labels for CLI output.

This module only translates user-facing text. It must not be used for JSON keys,
API paths, schema fields, validator constants, or persisted artifact structure.
"""

from __future__ import annotations


STATUS_LABELS = {
    "PASS": "通过",
    "FAIL": "失败",
    "Success": "通过",
    "SKIPPED": "已跳过",
    "Timeout": "请求超时",
    "Missing API Key": "缺少 API Key",
    "Authentication Error": "身份认证失败",
    "Rate Limit": "请求限流",
    "Model Request Error": "模型请求错误",
    "Invalid JSON": "JSON 格式错误",
    "Invalid Analysis Focus": "分析方向无效",
}

FOCUS_LABELS = {
    "problem_analysis": "产品问题",
    "positive_feedback_analysis": "正向反馈",
    "mixed_analysis": "问题 + 正向反馈",
}

TERM_LABELS = {
    "Topic Discovery": "主题发现",
    "Issue Consolidation": "问题归并",
    "Finding Generation": "分析发现生成",
    "Requirement Generation": "产品需求生成",
    "Roadmap Planning": "版本规划",
    "PRD Generation": "PRD 生成",
    "Test Case Generation": "测试用例生成",
    "Pipeline": "评论处理流水线",
    "Issue Classification": "问题类型分类",
    "Finding Eligibility": "分析发现准入",
    "Phase 8 Final Validation": "Phase 8 最终验证",
    "Roadmap Generation": "版本规划生成",
    "Provider": "模型提供方",
    "Model": "模型",
    "Analysis Focus": "分析方向",
    "Input": "输入数量",
    "Valid": "有效数量",
    "Retained": "保留数量",
    "Duplicates": "重复数量",
    "Statistics": "统计信息",
    "Topic Count": "主题数量",
    "Issue Count": "问题数量",
    "Unmerged Topic Count": "未归并主题数量",
    "Finding Count": "分析发现数量",
    "Requirement Count": "产品需求数量",
    "PRD Count": "PRD 数量",
    "Version Count": "版本数量",
    "Roadmap Item Count": "规划项数量",
    "Deferred Count": "延期需求数量",
    "Test Case Count": "测试用例数量",
    "Total Requirements": "产品需求总数",
    "Covered Requirements": "已覆盖产品需求数",
    "Requirement Coverage": "产品需求覆盖率",
    "Total Acceptance Criteria": "验收标准总数",
    "Covered Acceptance Criteria": "已覆盖验收标准数",
    "Acceptance Criteria Coverage": "验收标准覆盖率",
    "Input Findings": "输入分析发现数量",
    "Eligibility Checked": "准入检查数量",
    "Validation": "验证",
    "Validation Status": "验证状态",
    "Failure Type": "失败类型",
    "Error": "错误",
    "Message": "消息",
    "Output files": "输出文件",
    "Retry Attempted": "是否尝试重试",
    "Retry Success": "重试是否成功",
    "Eligible": "可进入 Finding",
    "Ineligible": "不可进入 Finding",
    "Issue Type Distribution": "问题类型分布",
    "Forward Traceability": "正向追溯",
    "Backward Traceability": "反向追溯",
    "Artifact Consistency": "输出文件一致性",
    "Evidence Traceability": "证据追溯",
    "Explicit Test Case -> Review Link": "测试用例 → 来源评论关联",
    "Statistics / Model Separation": "统计 / 模型分离",
    "Failure State Audit": "失败状态审计",
    "Uncertainty / Conflict Audit": "不确定性 / 冲突证据审计",
    "AI / Deterministic Boundary": "AI / 确定性边界",
    "Generalization": "泛化验证",
    "Exam Requirement Coverage": "考题覆盖率",
    "Downstream Safety": "下游安全性",
    "Counts": "数量统计",
    "Critical Issues": "阻断问题",
    "Non-blocking Issues": "非阻断问题",
    "Missing Final Deliverables": "缺失最终交付项",
    "Failure State Audit": "失败状态审计",
    "Uncertainty / Conflict Audit": "不确定性 / 冲突证据审计",
}


def label(text: str) -> str:
    return TERM_LABELS.get(text, text)


def value(text: object) -> str:
    if text is None:
        return "无"
    raw = str(text)
    return STATUS_LABELS.get(raw) or FOCUS_LABELS.get(raw) or raw


def line(term: str, item: object) -> str:
    return f"{label(term)}：{value(item)}"


def stage_result(stage: str, status: str) -> str:
    return f"{label(stage)}：{value(status)}"
