import unittest

from app.product_scope import extract_allowed_product_concepts, validate_product_scope


class ProductScopeTests(unittest.TestCase):
    def test_extract_allowed_product_concepts_from_upstream_text(self) -> None:
        concepts = extract_allowed_product_concepts(
            {
                "title": "Clarify coupon eligibility",
                "description": "Users need discount terms to be transparent.",
            }
        )

        self.assertEqual(concepts, ["coupon", "discount"])

    def test_supported_concept_passes(self) -> None:
        result = validate_product_scope(
            "Validate that the coupon code is accepted only when eligible.",
            {"acceptance_criteria": ["Coupon eligibility is clearly displayed."]},
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.unsupported_concepts, [])

    def test_unsupported_concept_fails(self) -> None:
        result = validate_product_scope(
            "Launch a coupon and loyalty program for returning users.",
            {"title": "Clarify subscription pricing"},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.unsupported_concepts, ["coupon", "loyalty_program"])

    def test_user_loyalty_language_is_not_a_loyalty_program(self) -> None:
        result = validate_product_scope(
            "Preserve the experiences that contribute to user loyalty and positive feedback.",
            {"title": "Preserve workout motivation and satisfaction."},
        )

        self.assertTrue(result.passed)

    def test_unknown_app_domain_terms_do_not_fail_without_high_risk_concepts(self) -> None:
        result = validate_product_scope(
            "Improve PDF export reliability and note sync recovery.",
            {"title": "PDF export is slow", "description": "Notes do not sync reliably."},
        )

        self.assertTrue(result.passed)

    def test_chinese_concept_detection(self) -> None:
        result = validate_product_scope(
            "测试优惠券是否自动应用。",
            {"acceptance_criteria": ["订阅价格必须清楚展示。"]},
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.unsupported_concepts, ["coupon"])


if __name__ == "__main__":
    unittest.main()
