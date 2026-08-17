import unittest
from datetime import datetime

from app.apify_provider import (
    APIFY_ACTOR_ID,
    ApifyReviewProvider,
    classify_apify_exception,
    normalize_apify_review,
)


class ApifyReviewProviderTests(unittest.TestCase):
    def test_token_missing(self) -> None:
        with self.assertRaises(ValueError):
            ApifyReviewProvider(api_token="")

    def test_actor_configuration(self) -> None:
        provider = ApifyReviewProvider(api_token="token", territory="US")

        self.assertEqual(provider.actor_id, APIFY_ACTOR_ID)
        self.assertEqual(
            provider.build_actor_input("839285684", max_reviews=50),
            {
                "appIds": ["839285684"],
                "country": "us",
                "maxReviews": 50,
                "sort": "recent",
            },
        )

    def test_response_normalization(self) -> None:
        review = normalize_apify_review(
            {
                "success": True,
                "review_id": "14282988831",
                "app_id": "839285684",
                "user_name": "Reviewer",
                "rating": 5,
                "title": "Great",
                "text": "Useful workouts.",
                "posted_at": "2026-07-09T18:01:47Z",
                "url": "https://apps.apple.com/us/app/id839285684?see-all=reviews",
            },
            app_id="839285684",
            territory="US",
        )

        self.assertEqual(review["source"], "apify")
        self.assertEqual(review["app_id"], "839285684")
        self.assertEqual(review["territory"], "US")
        self.assertEqual(review["rating"], 5)
        self.assertTrue(review["id"])
        self.assertTrue(review["title"] or review["body"])
        datetime.fromisoformat(review["created_at"].replace("Z", "+00:00"))

    def test_rating_validation(self) -> None:
        with self.assertRaises(ValueError):
            normalize_apify_review(
                {
                    "review_id": "bad-rating",
                    "rating": 6,
                    "title": "Bad",
                    "posted_at": "2026-07-09T18:01:47Z",
                },
                app_id="839285684",
                territory="US",
            )

    def test_us_territory_validation(self) -> None:
        with self.assertRaises(ValueError):
            normalize_apify_review(
                {
                    "review_id": "wrong-territory",
                    "rating": 4,
                    "title": "Ok",
                    "posted_at": "2026-07-09T18:01:47Z",
                },
                app_id="839285684",
                territory="CN",
            )

    def test_malformed_response(self) -> None:
        with self.assertRaises(ValueError):
            normalize_apify_review(
                {
                    "review_id": "",
                    "rating": 4,
                    "title": "",
                    "text": "",
                    "posted_at": "2026-07-09T18:01:47Z",
                },
                app_id="839285684",
                territory="US",
            )

    def test_empty_response_without_real_api(self) -> None:
        class EmptyDatasetProvider(ApifyReviewProvider):
            def _build_client(self):
                class ActorClient:
                    def call(self, run_input):
                        return {
                            "id": "run-1",
                            "status": "SUCCEEDED",
                            "defaultDatasetId": "dataset-1",
                        }

                class DatasetClient:
                    def iterate_items(self):
                        return iter([])

                class Client:
                    def actor(self, actor_id):
                        return ActorClient()

                    def dataset(self, dataset_id):
                        return DatasetClient()

                return Client()

        result = EmptyDatasetProvider(api_token="token").fetch_reviews("839285684", max_reviews=50)

        self.assertEqual(len(result.reviews), 0)
        self.assertTrue(result.errors)
        self.assertIn("Apify dataset returned no review rows.", result.errors[0].message)

    def test_error_mapping(self) -> None:
        self.assertEqual(classify_apify_exception(Exception("401 Unauthorized")), "authentication failure")
        self.assertEqual(classify_apify_exception(Exception("timeout")), "network failure")
        self.assertEqual(
            classify_apify_exception(Exception("dataset timeout"), dataset=True),
            "network failure",
        )


if __name__ == "__main__":
    unittest.main()

