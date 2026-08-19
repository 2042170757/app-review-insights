from pathlib import Path
import unittest

from app.cli_i18n import line, stage_result, value


FRONTEND_I18N = Path("frontend/src/i18n.js").read_text(encoding="utf-8")
FRONTEND_APP = Path("frontend/src/App.jsx").read_text(encoding="utf-8")


class LocalizationTests(unittest.TestCase):
    def test_workflow_stage_labels_are_chinese(self) -> None:
        expected = {
            "scope": "分析范围",
            "collection": "评论采集",
            "processing": "评论清洗与处理",
            "topic_discovery": "动态主题发现",
            "issue_consolidation": "问题归并",
            "finding_generation": "证据驱动分析",
            "requirement_generation": "产品需求生成",
            "roadmap": "版本规划",
            "prd": "PRD 生成",
            "test_cases": "测试用例生成",
            "traceability": "全链路追溯",
        }
        for key, label in expected.items():
            self.assertIn(f"{key}: '{label}'", FRONTEND_I18N)

    def test_status_focus_and_source_labels_are_chinese(self) -> None:
        for label in [
            "排队中",
            "执行中",
            "已完成",
            "执行失败",
            "待完成",
            "已跳过",
            "产品问题",
            "正向反馈",
            "问题 + 正向反馈",
            "App Store 实时数据",
            "JSON 导入",
            "CSV 导入",
            "缓存演示数据",
        ]:
            self.assertIn(label, FRONTEND_I18N)

    def test_error_warning_evidence_requirement_prd_test_case_and_traceability_labels(self) -> None:
        for label in [
            "数据验证失败",
            "请求超时",
            "身份认证失败",
            "警告",
            "证据",
            "支持性评论 ID [证据]",
            "冲突证据",
            "产品需求",
            "验收标准",
            "产品需求文档",
            "测试用例",
            "前置条件",
            "预期结果",
            "可追溯性",
            "正向追溯",
            "反向追溯",
            "证据追溯",
            "测试用例 → 来源评论关联",
        ]:
            self.assertIn(label, FRONTEND_I18N)

    def test_live_demo_import_and_rating_constraint_text_is_chinese(self) -> None:
        for text in [
            "实时分析",
            "缓存演示数据",
            "当前结果来自项目内置缓存，仅用于离线演示，不代表实时 App Store 数据。",
            "系统将使用当前配置的数据源和模型实时执行分析",
            "JSON 文件",
            "CSV 文件",
            "正在验证导入文件",
            "导入失败",
            "全部评分",
            "1-2 星",
            "1-3 星",
            "4-5 星",
        ]:
            self.assertIn(text, FRONTEND_APP + FRONTEND_I18N)

    def test_cli_display_helpers_translate_user_visible_summary(self) -> None:
        self.assertEqual(stage_result("Topic Discovery", "PASS"), "主题发现：通过")
        self.assertEqual(stage_result("Test Case Generation", "FAIL"), "测试用例生成：失败")
        self.assertEqual(line("Failure Type", "Timeout"), "失败类型：请求超时")
        self.assertEqual(line("Analysis Focus", "positive_feedback_analysis"), "分析方向：正向反馈")
        self.assertEqual(value("DeepSeek"), "DeepSeek")

    def test_internal_json_and_api_identifiers_remain_english(self) -> None:
        for identifier in [
            "review_id",
            "topic_id",
            "issue_id",
            "finding_id",
            "requirement_id",
            "source_review_ids",
            "analysis_goal",
            "analysis_focus",
            "/api/runs",
            "/api/demo/run",
        ]:
            self.assertIn(identifier, FRONTEND_APP + FRONTEND_I18N)


if __name__ == "__main__":
    unittest.main()
