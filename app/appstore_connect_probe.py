"""App Store Connect API capability probe.

This is a diagnostic tool only. It does not implement a ReviewProvider and does
not modify the Phase 0 Apple RSS collection path.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ENV_ISSUER_ID = "APPSTORE_ISSUER_ID"
ENV_KEY_ID = "APPSTORE_KEY_ID"
ENV_PRIVATE_KEY_PATH = "APPSTORE_PRIVATE_KEY_PATH"
TARGET_APP_STORE_ID = "839285684"
PROBE_ARTIFACT_PATH = Path("artifacts/probes/appstore_connect_probe.json")
API_BASE_URL = "https://api.appstoreconnect.apple.com/v1/"


@dataclass(frozen=True)
class ProbeConfig:
    issuer_id: str
    key_id: str
    private_key_path: Path


@dataclass
class StepResult:
    status: str
    message: str
    http_status: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    diagnosis: str | None = None


@dataclass
class ProbeReport:
    generated_at: str
    target_app_store_id: str
    authentication: StepResult
    list_apps: StepResult
    target_app: StepResult
    customer_reviews: StepResult
    app_resource_id: str | None = None
    apps_checked: int = 0
    reviews_sample_count: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    payload: dict[str, Any] | None
    error_code: str | None = None
    error_message: str | None = None
    url: str | None = None


def main() -> int:
    report = run_probe()
    save_report(report, PROBE_ARTIFACT_PATH)
    print_report(report, PROBE_ARTIFACT_PATH)
    return 0 if _probe_passed(report) else 1


def run_probe(env: Mapping[str, str] | None = None) -> ProbeReport:
    env = os.environ if env is None else env
    report = _empty_report()

    config, config_error = load_config(env)
    if config_error:
        report.authentication = config_error
        return report

    jwt_token, jwt_error = generate_jwt(config)
    if jwt_error:
        report.authentication = jwt_error
        return report

    report.authentication = StepResult(
        status="PASS",
        message="Environment variables, private key file, and local JWT generation passed.",
        diagnosis="JWT_GENERATED_LOCALLY",
    )

    client = AppStoreConnectClient(jwt_token)
    apps_response, apps = client.list_apps()
    report.list_apps = step_from_api_response(apps_response, success_message="Visible apps listed.")
    if report.list_apps.status != "PASS":
        return report

    report.apps_checked = len(apps)
    app_resource = find_target_app(apps, TARGET_APP_STORE_ID)
    if app_resource is None:
        report.target_app = StepResult(
            status="NOT FOUND",
            message="Target App Store ID was not found in apps visible to this API key.",
            diagnosis="APP_NOT_IN_CURRENT_ACCOUNT_OR_NOT_VISIBLE",
        )
        report.customer_reviews = StepResult(
            status="FAIL",
            message="Customer reviews were not requested because the target app was not found.",
            diagnosis="TARGET_APP_NOT_FOUND",
        )
        return report

    report.app_resource_id = str(app_resource["id"])
    report.target_app = StepResult(
        status="FOUND",
        message="Target app is visible to this API key.",
        diagnosis="TARGET_APP_VISIBLE",
    )

    reviews_response = client.get_customer_reviews(report.app_resource_id)
    report.customer_reviews = step_from_api_response(
        reviews_response,
        success_message="Customer reviews endpoint returned a successful response.",
        forbidden_status="NOT AUTHORIZED",
    )
    if reviews_response.payload and isinstance(reviews_response.payload.get("data"), list):
        report.reviews_sample_count = len(reviews_response.payload["data"])

    return report


def load_config(env: Mapping[str, str]) -> tuple[ProbeConfig | None, StepResult | None]:
    missing = [
        name
        for name in (ENV_ISSUER_ID, ENV_KEY_ID, ENV_PRIVATE_KEY_PATH)
        if not env.get(name)
    ]
    if missing:
        return None, StepResult(
            status="FAIL",
            message="Missing required App Store Connect environment variables.",
            diagnosis="MISSING_ENVIRONMENT_VARIABLES",
            error_message=", ".join(missing),
        )

    private_key_path = Path(env[ENV_PRIVATE_KEY_PATH])
    if not private_key_path.is_file():
        return None, StepResult(
            status="FAIL",
            message="Private key file does not exist.",
            diagnosis="PRIVATE_KEY_FILE_NOT_FOUND",
            error_message=str(private_key_path),
        )

    return (
        ProbeConfig(
            issuer_id=env[ENV_ISSUER_ID],
            key_id=env[ENV_KEY_ID],
            private_key_path=private_key_path,
        ),
        None,
    )


def generate_jwt(
    config: ProbeConfig,
    *,
    now: datetime | None = None,
) -> tuple[str | None, StepResult | None]:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
    except ImportError as exc:
        return None, StepResult(
            status="FAIL",
            message="JWT generation requires the cryptography package.",
            diagnosis="JWT_DEPENDENCY_MISSING",
            error_message=repr(exc),
        )

    issued_at = now or datetime.now(UTC)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    expires_at = issued_at + timedelta(minutes=20)

    header = {"alg": "ES256", "kid": config.key_id, "typ": "JWT"}
    payload = {
        "iss": config.issuer_id,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "aud": "appstoreconnect-v1",
    }

    try:
        private_key_bytes = config.private_key_path.read_bytes()
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("Private key is not an elliptic curve private key")

        signing_input = (
            _b64url_json(header).encode("ascii")
            + b"."
            + _b64url_json(payload).encode("ascii")
        )
        der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r_value, s_value = utils.decode_dss_signature(der_signature)
        raw_signature = r_value.to_bytes(32, "big") + s_value.to_bytes(32, "big")
        token = signing_input.decode("ascii") + "." + _b64url(raw_signature)
    except (OSError, TypeError, ValueError) as exc:
        return None, StepResult(
            status="FAIL",
            message="JWT generation failed.",
            diagnosis="JWT_CONFIGURATION_ERROR",
            error_message=repr(exc),
        )

    return token, None


class AppStoreConnectClient:
    def __init__(self, jwt_token: str, *, base_url: str = API_BASE_URL) -> None:
        self.jwt_token = jwt_token
        self.base_url = base_url

    def list_apps(self) -> tuple[ApiResponse, list[dict[str, Any]]]:
        apps: list[dict[str, Any]] = []
        next_url: str | None = urljoin(self.base_url, "apps?limit=200")

        while next_url:
            response = self.request(next_url)
            if response.status_code < 200 or response.status_code >= 300:
                return response, apps

            payload = response.payload or {}
            data = payload.get("data")
            if isinstance(data, list):
                apps.extend(item for item in data if isinstance(item, dict))

            next_link = payload.get("links", {}).get("next")
            next_url = next_link if isinstance(next_link, str) and next_link else None

        return ApiResponse(status_code=200, payload={"data": apps}, url=urljoin(self.base_url, "apps")), apps

    def get_customer_reviews(self, app_resource_id: str) -> ApiResponse:
        path = f"apps/{app_resource_id}/customerReviews?limit=10"
        return self.request(urljoin(self.base_url, path))

    def request(self, url: str) -> ApiResponse:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.jwt_token}",
                "User-Agent": "app-review-insights-appstore-connect-probe/0.1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
                payload = json.loads(body) if body else {}
                return ApiResponse(status_code=response.status, payload=payload, url=url)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            payload = _safe_json(body)
            error_code, error_message = extract_apple_error(payload, fallback=body)
            return ApiResponse(
                status_code=exc.code,
                payload=payload,
                error_code=error_code,
                error_message=error_message,
                url=url,
            )
        except (URLError, TimeoutError, OSError) as exc:
            return ApiResponse(
                status_code=0,
                payload=None,
                error_code="NETWORK_ERROR",
                error_message=repr(exc),
                url=url,
            )


def step_from_api_response(
    response: ApiResponse,
    *,
    success_message: str,
    forbidden_status: str = "FAIL",
) -> StepResult:
    if 200 <= response.status_code < 300:
        return StepResult(status="PASS", message=success_message, http_status=response.status_code)

    diagnosis = classify_api_failure(
        response.status_code,
        response.error_code,
        response.error_message,
    )
    status = forbidden_status if response.status_code == 403 else "FAIL"
    return StepResult(
        status=status,
        message="App Store Connect API request failed.",
        http_status=response.status_code or None,
        error_code=response.error_code,
        error_message=response.error_message,
        diagnosis=diagnosis,
    )


def classify_api_failure(
    status_code: int,
    error_code: str | None,
    error_message: str | None,
) -> str:
    text = f"{error_code or ''} {error_message or ''}".lower()
    if status_code == 0:
        return "NETWORK_OR_TRANSPORT_ERROR"
    if status_code == 401:
        if "not enabled" in text or "api access" in text:
            return "API_ACCESS_NOT_ENABLED"
        return "401_UNAUTHORIZED_JWT_OR_API_KEY_REJECTED"
    if status_code == 403:
        if "not enabled" in text or "api access" in text:
            return "API_ACCESS_NOT_ENABLED"
        return "403_FORBIDDEN_INSUFFICIENT_PERMISSION"
    if status_code == 404:
        return "RESOURCE_NOT_FOUND_OR_APP_NOT_VISIBLE"
    if 400 <= status_code < 500:
        return "OTHER_CLIENT_HTTP_ERROR"
    if status_code >= 500:
        return "APPLE_SERVER_HTTP_ERROR"
    return "UNKNOWN_HTTP_ERROR"


def find_target_app(apps: list[dict[str, Any]], target_app_store_id: str) -> dict[str, Any] | None:
    for app in apps:
        if str(app.get("id")) == target_app_store_id:
            return app

        attributes = app.get("attributes")
        if not isinstance(attributes, dict):
            continue
        for key in ("appStoreId", "appleId", "adamId"):
            value = attributes.get(key)
            if value is not None and str(value) == target_app_store_id:
                return app
    return None


def extract_apple_error(
    payload: dict[str, Any] | None,
    *,
    fallback: str,
) -> tuple[str | None, str | None]:
    if isinstance(payload, dict):
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict):
                code = first.get("code") or first.get("status")
                title = first.get("title")
                detail = first.get("detail")
                message = " - ".join(str(part) for part in (title, detail) if part)
                return str(code) if code is not None else None, message or None
    return None, fallback[:1000] if fallback else None


def save_report(report: ProbeReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")


def print_report(report: ProbeReport, path: Path) -> None:
    print(f"Authentication: {report.authentication.status}")
    print(f"List Apps: {report.list_apps.status}")
    print(f"Target App: {report.target_app.status}")
    print(f"Customer Reviews: {report.customer_reviews.status}")
    print(f"App Resource ID: {report.app_resource_id or 'N/A'}")
    print(f"Apps Checked: {report.apps_checked}")
    if report.reviews_sample_count is not None:
        print(f"Customer Reviews Sample Count: {report.reviews_sample_count}")
    print(f"JSON Report: {path}")

    for label, step in (
        ("Authentication", report.authentication),
        ("List Apps", report.list_apps),
        ("Target App", report.target_app),
        ("Customer Reviews", report.customer_reviews),
    ):
        if step.status in {"FAIL", "NOT FOUND", "NOT AUTHORIZED"}:
            print(f"{label} Diagnosis: {step.diagnosis or 'UNKNOWN'}")
            if step.http_status:
                print(f"{label} HTTP Status: {step.http_status}")
            if step.error_code:
                print(f"{label} Error Code: {step.error_code}")
            if step.error_message:
                print(f"{label} Error Message: {step.error_message}")


def _empty_report() -> ProbeReport:
    pending = StepResult(status="SKIPPED", message="Skipped because an earlier step did not pass.")
    return ProbeReport(
        generated_at=datetime.now(UTC).isoformat(),
        target_app_store_id=TARGET_APP_STORE_ID,
        authentication=pending,
        list_apps=pending,
        target_app=pending,
        customer_reviews=pending,
        notes=[
            "App Store Connect API requires App Store Connect API key access.",
            "This API is not a public arbitrary App Store review API.",
            "App Store URL accessibility does not imply App Store Connect API access.",
        ],
    )


def _probe_passed(report: ProbeReport) -> bool:
    return (
        report.authentication.status == "PASS"
        and report.list_apps.status == "PASS"
        and report.target_app.status == "FOUND"
        and report.customer_reviews.status == "PASS"
    )


def _safe_json(body: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _b64url_json(value: dict[str, Any]) -> str:
    return _b64url(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


if __name__ == "__main__":
    raise SystemExit(main())

