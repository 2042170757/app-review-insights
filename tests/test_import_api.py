import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.imports import IMPORT_MAX_BYTES_ENV, IMPORT_ROOT_ENV
from app.workflow.artifacts import RUN_ARTIFACT_ROOT_ENV
from app.workflow.orchestrator import WorkflowOrchestrator
from app.workflow.pipeline import WorkflowStageExecutionResult


VALID_URL = "https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684"


class ImportAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_import_root = os.environ.get(IMPORT_ROOT_ENV)
        self.previous_run_root = os.environ.get(RUN_ARTIFACT_ROOT_ENV)
        self.previous_max_bytes = os.environ.get(IMPORT_MAX_BYTES_ENV)
        os.environ[IMPORT_ROOT_ENV] = str(Path(self.tempdir.name) / "imports")
        os.environ[RUN_ARTIFACT_ROOT_ENV] = str(Path(self.tempdir.name) / "runs")
        os.environ.pop(IMPORT_MAX_BYTES_ENV, None)
        self.runner = _RecordingRunner()
        self.orchestrator = WorkflowOrchestrator(pipeline_runner=self.runner)
        self.client = TestClient(create_app(self.orchestrator))

    def tearDown(self) -> None:
        _restore_env(IMPORT_ROOT_ENV, self.previous_import_root)
        _restore_env(RUN_ARTIFACT_ROOT_ENV, self.previous_run_root)
        _restore_env(IMPORT_MAX_BYTES_ENV, self.previous_max_bytes)
        self.tempdir.cleanup()

    def test_json_upload_returns_preview_metadata(self) -> None:
        response = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", json.dumps({"reviews": [_review("json-1")]}), "application/json")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_type"], "json")
        self.assertEqual(payload["metadata"]["display_source"], "Imported JSON")
        self.assertEqual(payload["metadata"]["record_count"], 1)
        self.assertEqual(payload["metadata"]["valid_count"], 1)
        self.assertEqual(payload["metadata"]["invalid_count"], 0)
        self.assertEqual(payload["metadata"]["territory"], "Unknown / Not provided")
        self.assertNotIn("path", json.dumps(payload))

    def test_csv_upload_returns_preview_metadata(self) -> None:
        response = self.client.post(
            "/api/import/csv",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.csv", "id,rating,title,body,created_at\ncsv-1,4,Title,,2026-08-17T00:00:00Z\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_type"], "csv")
        self.assertEqual(payload["metadata"]["display_source"], "Imported CSV")
        self.assertEqual(payload["metadata"]["record_count"], 1)

    def test_invalid_json_returns_import_error(self) -> None:
        response = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", "{bad", "application/json")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["type"], "Invalid JSON")

    def test_invalid_csv_missing_columns_returns_import_error(self) -> None:
        response = self.client.post(
            "/api/import/csv",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.csv", "id,title\ncsv-1,Title\n", "text/csv")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["type"], "Missing Columns")

    def test_missing_required_field_returns_schema_error(self) -> None:
        response = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", json.dumps({"reviews": [{"id": "x", "rating": 4, "created_at": "2026-08-17T00:00:00Z"}]}), "application/json")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["type"], "Missing Required Field")

    def test_invalid_rating_returns_import_error(self) -> None:
        bad = _review("bad-rating", rating=7)
        response = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", json.dumps({"reviews": [bad]}), "application/json")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["type"], "Invalid Rating")

    def test_empty_dataset_returns_import_error(self) -> None:
        response = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", json.dumps({"reviews": []}), "application/json")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["type"], "Empty Dataset")

    def test_file_too_large_returns_import_error(self) -> None:
        os.environ[IMPORT_MAX_BYTES_ENV] = "12"
        response = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", json.dumps({"reviews": [_review("large")]}), "application/json")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["type"], "File Too Large")

    def test_import_run_uses_import_source_and_metadata(self) -> None:
        imported = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("reviews.json", json.dumps({"reviews": [_review("json-run")]}), "application/json")},
        ).json()

        created = self.client.post(
            "/api/runs/import",
            json={"import_id": imported["import_id"], "app_url": VALID_URL, "analysis_goal": "Goal"},
        )

        self.assertEqual(created.status_code, 200)
        run_id = created.json()["run_id"]
        self._wait_for_terminal_run(run_id)
        run_payload = self.client.get(f"/api/runs/{run_id}").json()
        metadata = self.client.get(f"/api/runs/{run_id}/metadata").json()
        self.assertEqual(run_payload["source_type"], "json")
        self.assertEqual(run_payload["data_source"], "json")
        self.assertEqual(run_payload["import_metadata"]["display_source"], "Imported JSON")
        self.assertEqual(metadata["data"]["display_source"], "Imported JSON")
        self.assertEqual(metadata["data"]["artifact_source"], "Uploaded File")
        self.assertEqual(metadata["data"]["territory"], "Unknown / Not provided")
        self.assertNotIn("path", json.dumps(metadata))
        self.assertEqual(self.runner.contexts[0]["source_type"], "json")
        self.assertTrue(self.runner.contexts[0]["import_path"])

    def test_run_isolation_between_imports(self) -> None:
        first = self.client.post(
            "/api/import/json",
            data={"app_url": VALID_URL},
            files={"file": ("first.json", json.dumps({"reviews": [_review("first")]}), "application/json")},
        ).json()
        second = self.client.post(
            "/api/import/csv",
            data={"app_url": VALID_URL},
            files={"file": ("second.csv", "id,rating,title,body,created_at\nsecond,5,Title,,2026-08-17T00:00:00Z\n", "text/csv")},
        ).json()

        self.assertNotEqual(first["import_id"], second["import_id"])
        self.assertEqual(first["metadata"]["filename"], "first.json")
        self.assertEqual(second["metadata"]["filename"], "second.csv")

    def _wait_for_terminal_run(self, run_id: str) -> None:
        for _ in range(50):
            payload = self.client.get(f"/api/runs/{run_id}").json()
            if payload["status"] in {"completed", "failed"}:
                return
            time.sleep(0.01)
        self.fail("run did not reach a terminal state")


class _RecordingRunner:
    def __init__(self) -> None:
        self.contexts: list[dict] = []

    def run_stage(self, *, stage: str, context: dict):
        self.contexts.append(dict(context))
        return WorkflowStageExecutionResult(
            stage=stage,
            message=f"{stage} done",
            artifacts=[f"artifacts/{stage}.json"],
            summary={
                "run_id": context["run_id"],
                "source_type": context.get("source_type"),
                "display_source": context.get("import_metadata", {}).get("display_source"),
            },
            elapsed_seconds=0.001,
        )


def _review(review_id: str, *, rating: int = 4) -> dict[str, object]:
    return {
        "id": review_id,
        "rating": rating,
        "title": "Title",
        "body": "",
        "created_at": "2026-08-17T00:00:00Z",
    }


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
