import unittest

from app.llm.json_recovery import extract_json_object, parse_json_response


class JSONRecoveryTests(unittest.TestCase):
    def test_valid_json(self) -> None:
        result = parse_json_response('{"requirements": []}')

        self.assertTrue(result.success)
        self.assertFalse(result.attempted)
        self.assertEqual(result.method, "direct_json")
        self.assertEqual(result.parsed, {"requirements": []})

    def test_fenced_json(self) -> None:
        result = parse_json_response('```json\n{"requirements": []}\n```')

        self.assertTrue(result.success)
        self.assertTrue(result.attempted)
        self.assertEqual(result.method, "fenced_json")
        self.assertEqual(result.extracted_response, '{"requirements": []}')

    def test_json_with_leading_text(self) -> None:
        result = parse_json_response('Here is the result: {"requirements": []}')

        self.assertTrue(result.success)
        self.assertEqual(result.method, "embedded_json_object")

    def test_json_with_trailing_text(self) -> None:
        result = parse_json_response('{"requirements": []}\nDone.')

        self.assertTrue(result.success)
        self.assertEqual(result.method, "embedded_json_object")

    def test_json_string_payload(self) -> None:
        result = parse_json_response('"{\\"requirements\\": []}"')

        self.assertTrue(result.success)
        self.assertEqual(result.method, "json_string")
        self.assertTrue(result.attempted)

    def test_multiple_json_objects_fail(self) -> None:
        result = parse_json_response('{"a": 1}\n{"b": 2}')

        self.assertFalse(result.success)
        self.assertEqual(result.method, "multiple_json_objects")

    def test_empty_response_fails(self) -> None:
        result = parse_json_response("   ")

        self.assertFalse(result.success)
        self.assertEqual(result.method, "empty_response")

    def test_malformed_json_fails(self) -> None:
        result = parse_json_response("{not json")

        self.assertFalse(result.success)
        self.assertEqual(result.method, "invalid_json")

    def test_extract_json_object_ignores_braces_inside_strings(self) -> None:
        candidates = extract_json_object('prefix {"text": "brace } inside", "value": 1} suffix')

        self.assertEqual(candidates, ['{"text": "brace } inside", "value": 1}'])


if __name__ == "__main__":
    unittest.main()
