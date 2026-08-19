from pathlib import Path
import unittest


FRONTEND_APP = Path("frontend/src/App.jsx").read_text(encoding="utf-8")
FRONTEND_I18N = Path("frontend/src/i18n.js").read_text(encoding="utf-8")
FRONTEND_PRESENTATION = Path("frontend/src/presentation.js").read_text(encoding="utf-8")
FRONTEND_STYLES = Path("frontend/src/styles.css").read_text(encoding="utf-8")
FRONTEND_SOURCE = FRONTEND_APP + FRONTEND_I18N + FRONTEND_PRESENTATION + FRONTEND_STYLES


class BilingualPresentationTests(unittest.TestCase):
    def test_topic_bilingual_display(self) -> None:
        self.assertIn('text={topic.name} context="topic"', FRONTEND_APP)
        self.assertIn('text={topic.description} context="topic"', FRONTEND_APP)
        self.assertIn('text={topic.uncertainty} context="topic"', FRONTEND_APP)
        self.assertIn("该主题主要概括", FRONTEND_PRESENTATION)

    def test_issue_bilingual_display_and_type_labels(self) -> None:
        self.assertIn('text={issue.name} context="issue"', FRONTEND_APP)
        self.assertIn('text={issue.description} context="issue"', FRONTEND_APP)
        self.assertIn('text={issue.merge_rationale} context="issue"', FRONTEND_APP)
        for label in ["产品问题", "正向反馈", "混合类型", "中性观察"]:
            self.assertIn(label, FRONTEND_SOURCE)

    def test_finding_bilingual_display(self) -> None:
        self.assertIn('text={finding.title || finding.name} context="finding"', FRONTEND_APP)
        self.assertIn('text={finding.statement || finding.description} context="finding"', FRONTEND_APP)
        self.assertIn('text={finding.uncertainty} context="finding"', FRONTEND_APP)
        self.assertIn("该分析发现指出", FRONTEND_PRESENTATION)

    def test_requirement_bilingual_display_and_source_links(self) -> None:
        self.assertIn('text={requirement.title || requirement.name} context="requirement"', FRONTEND_APP)
        self.assertIn('text={requirement.description} context="requirement"', FRONTEND_APP)
        self.assertIn('title="Priority Rationale"', FRONTEND_APP)
        self.assertIn('title="Acceptance Criteria"', FRONTEND_APP)
        self.assertIn('title="Source Finding"', FRONTEND_APP)
        self.assertIn("requirement.source_review_ids", FRONTEND_APP)

    def test_roadmap_bilingual_display(self) -> None:
        self.assertIn('text={version.name} context="roadmap"', FRONTEND_APP)
        self.assertIn('text={version.goal} context="roadmap"', FRONTEND_APP)
        self.assertIn('title="Rationale"', FRONTEND_APP)
        self.assertIn('title="Risks"', FRONTEND_APP)
        self.assertIn('title="Success Metrics"', FRONTEND_APP)

    def test_prd_bilingual_display_and_empty_success_metrics(self) -> None:
        for title in ["Value Statement", "Problem Statement", "Evidence Summary", "Goals", "Non-Goals", "Risks"]:
            self.assertIn(f'title="{title}"', FRONTEND_APP)
        self.assertIn("No validated success metrics defined yet.", FRONTEND_APP)
        self.assertIn("暂无已验证的成功指标。", FRONTEND_APP)
        self.assertIn("需要产品决策：定义可衡量的成功指标。", FRONTEND_APP)

    def test_test_case_bilingual_display_and_source_reviews(self) -> None:
        self.assertIn('text={testCase.title} context="test_case"', FRONTEND_APP)
        self.assertIn('title="Preconditions"', FRONTEND_APP)
        self.assertIn('title="Steps"', FRONTEND_APP)
        self.assertIn('text={testCase.expected_result} context="test_case"', FRONTEND_APP)
        self.assertIn("testCase.source_review_ids", FRONTEND_APP)

    def test_warning_classification_labels_are_separate(self) -> None:
        for label in ["验证说明", "方法说明", "预期排除", "最终状态说明", "错误", "警告", "提示"]:
            self.assertIn(label, FRONTEND_PRESENTATION + FRONTEND_I18N)
        for css_class in [
            "validation-explanation",
            "method-explanation",
            "expected-exclusion",
            "final-status",
        ]:
            self.assertIn(css_class, FRONTEND_SOURCE)

    def test_expected_exclusion_has_specific_display(self) -> None:
        self.assertIn("positive\\/neutral issue excluded from finding", FRONTEND_PRESENTATION)
        self.assertIn("该问题被识别为正向反馈或中性观察", FRONTEND_PRESENTATION)
        self.assertIn("expected-exclusion-note", FRONTEND_SOURCE)

    def test_validation_explanation_for_unknown_goal(self) -> None:
        self.assertIn("unknown analysis goal generalization", FRONTEND_PRESENTATION)
        self.assertIn("未知分析目标的泛化能力已通过请求元信息与 CLI 测试验证", FRONTEND_PRESENTATION)

    def test_review_raw_text_is_preserved_and_chinese_explanation_is_separate(self) -> None:
        self.assertIn("review.raw_title || review.title || review.clean_title", FRONTEND_APP)
        self.assertIn("review.raw_body || review.body || review.clean_body", FRONTEND_APP)
        self.assertIn("reviewChineseExplanation", FRONTEND_APP)
        self.assertIn("中文释义仅用于展示层，不是原始用户评论", FRONTEND_PRESENTATION)
        self.assertNotIn("review.body =", FRONTEND_SOURCE)
        self.assertNotIn("review.title =", FRONTEND_SOURCE)

    def test_api_schema_unchanged_for_presentation_only_translation(self) -> None:
        for endpoint in ["/reviews", "/topics", "/issues", "/findings", "/requirements", "/roadmap", "/prd", "/test-cases"]:
            self.assertIn(endpoint, FRONTEND_APP)
        for forbidden in ["translated_topics", "translated_issues", "translated_findings", "chinese_translation"]:
            self.assertNotIn(forbidden, FRONTEND_APP)
        for identifier in ["topic_id", "issue_id", "finding_id", "requirement_id", "source_review_ids"]:
            self.assertIn(identifier, FRONTEND_APP)


if __name__ == "__main__":
    unittest.main()
