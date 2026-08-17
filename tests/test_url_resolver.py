import unittest

from app.url_resolver import AppStoreUrlError, parse_app_store_url


class ParseAppStoreUrlTests(unittest.TestCase):
    def test_correct_us_app_store_url(self) -> None:
        parsed = parse_app_store_url(
            "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"
        )

        self.assertEqual(parsed.storefront, "US")
        self.assertEqual(parsed.apple_store_app_id, "839285684")

    def test_non_app_store_url(self) -> None:
        with self.assertRaises(AppStoreUrlError):
            parse_app_store_url("https://example.com/us/app/example/id123")

    def test_missing_app_id(self) -> None:
        with self.assertRaises(AppStoreUrlError):
            parse_app_store_url("https://apps.apple.com/us/app/example")


if __name__ == "__main__":
    unittest.main()

