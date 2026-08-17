# App Review Insights

App Review Insights is a runnable review analysis workbench for turning iOS App Store reviews into evidence-grounded product outputs:

```text
Review
-> Processing
-> Topic
-> Issue
-> Finding
-> Requirement
-> Roadmap
-> PRD
-> Test Case
-> Traceability
```

The primary example app is:

```text
Workout for Women: Home Gym
https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
App ID: 839285684
Review Territory: US
```

The project is designed for interview evaluation. It supports live analysis when provider credentials and external network access are available, and it also includes a clearly labeled offline cached demo so reviewers can inspect the output without calling external services.

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

Python dependencies include FastAPI, Uvicorn, dotenv loading, Apify client support, multipart upload support, and cryptography for App Store Connect probing.

### 2. Configure environment variables

Create a local `.env` from `.env.example` or export environment variables in your shell.

```bash
APIFY_API_TOKEN=
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_THINKING=disabled
DEEPSEEK_MAX_TOKENS=3000
DEEPSEEK_TEMPERATURE=0.2
DEEPSEEK_TIMEOUT=60
```

Rules:

- Do not commit `.env`.
- System environment variables have priority over `.env`.
- API keys are not printed by the provider code.
- Cached Demo mode does not require Apify or DeepSeek credentials.

### 3. Start the backend

```bash
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

### 5. Open the UI

Open the Vite URL shown in the terminal, usually:

```text
http://127.0.0.1:5173/
```

If that port is busy, Vite may choose another local port.

## Running Live Analysis

In the UI:

1. Select `Live Analysis`.
2. Select `App Store`.
3. Enter a valid App Store URL.
4. Enter an analysis goal.
5. Click `开始分析`.

The default example is:

```text
https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
```

For live App Store collection, the workflow uses the configured review provider and then executes the full backend pipeline. Live analysis does not silently fall back to cached demo data. If Apify, DeepSeek, the network, or validation fails, the run is marked failed and downstream stages are skipped.

## Running Cached Demo

In the UI:

1. Select `Cached Demo`.
2. Click `Load Cached Demo`.
3. Review the dashboard tabs.

The dashboard shows a visible `Cached / Demo Data` warning. Demo data is:

- built into `app/demo_cache/`
- static
- not current App Store data
- not a live Apify collection
- not a live DeepSeek call
- not a fallback for live failures

The demo endpoints are:

```text
GET /api/demo/run
GET /api/demo/metadata
```

The metadata file is:

```text
app/demo_cache/demo_metadata.json
```

It records:

- `is_demo: true`
- `mode: cached_demo`
- `source_provider: apify`
- `territory: US`
- `app_id: 839285684`
- `review_count: 50`
- `model_provider: deepseek`
- `model: deepseek-v4-flash`

## JSON / CSV Import

The UI supports importing previously collected reviews.

In the UI:

1. Select `Live Analysis`.
2. Select `JSON` or `CSV`.
3. Provide an App Context URL.
4. Upload the file.
5. Confirm the preview metadata.
6. Start the run.

Imported data is not a live App Store collection. It is labeled as `Imported JSON` or `Imported CSV`.

If the imported dataset does not provide territory, the UI displays:

```text
Unknown / Not provided
```

The system must not fabricate `US` for imported reviews whose territory is missing.

### JSON Format

JSON can be either a list or an object containing `reviews`.

```json
{
  "reviews": [
    {
      "id": "review-001",
      "app_id": "example-app",
      "territory": "US",
      "rating": 2,
      "title": "Too expensive",
      "body": "The subscription price feels too high.",
      "created_at": "2026-01-01T00:00:00Z",
      "source": "json_import"
    }
  ]
}
```

Required fields after normalization:

- `rating` in `1..5`
- `created_at` parseable as a date/time
- at least one of `title` or `body`

If `id` is missing, the import provider generates a stable ID from the review content. If `app_id` is missing, the App Context URL can provide it.

### CSV Format

CSV must include a header row and at least:

```text
rating,created_at,title,body
```

Example:

```csv
id,app_id,territory,rating,title,body,created_at
review-001,example-app,US,2,Too expensive,The subscription price feels too high.,2026-01-01T00:00:00Z
```

## Review Data Sources

### Apple RSS Provider

`AppleRSSProvider` reads Apple's public customer review RSS JSON feed:

```text
https://itunes.apple.com/{storefront}/rss/customerreviews/page={page}/id={apple_store_app_id}/sortby=mostrecent/json
```

Notes:

- Apple RSS is a public data source.
- RSS availability and shape are controlled by Apple.
- Results are storefront-scoped.
- It does not guarantee complete historical coverage.
- It is used through the shared ReviewProvider interface.

### Apify Provider

`ApifyReviewProvider` uses the third-party Apify actor:

```text
apihq/app-store-reviews-scraper
```

Default smoke/live settings for the primary example:

```text
appIds = ["839285684"]
country = "us"
maxReviews = 50
sort = "recent"
```

Notes:

- Apify is a third-party review collection provider.
- The review source is the Apple App Store US storefront through the third-party collection service.
- Apify requires `APIFY_API_TOKEN`.
- Actor behavior, available fields, request frequency, and accuracy depend on the provider and Apple's storefront behavior.
- The current smoke path requests at most 50 recent reviews.
- Apify is not Apple official App Store Connect API.
- It does not guarantee complete historical coverage.

### App Store Connect Probe

The repository includes a diagnostic App Store Connect capability probe. It is not the primary public review source. App Store Connect access depends on the Apple account and API key permissions for the target app.

## LLM Provider and Model

Production semantic generation uses:

```text
Provider: DeepSeek
Model: deepseek-v4-flash
Base URL: https://api.deepseek.com
```

Default runtime configuration:

```text
thinking=disabled
max_tokens=3000
temperature=0.2
stream=false
timeout=60
response_format={"type":"json_object"}
```

The provider reads configuration from environment variables:

```text
DEEPSEEK_API_KEY
DEEPSEEK_MODEL
DEEPSEEK_THINKING
DEEPSEEK_MAX_TOKENS
DEEPSEEK_TEMPERATURE
DEEPSEEK_TIMEOUT
```

The model is called by provider classes behind the `LLMProvider` abstraction. Topic discovery, issue consolidation, finding generation, requirement generation, roadmap planning, PRD generation, and test case generation do not call the DeepSeek SDK directly from UI code.

## AI Tasks

LLM-driven tasks:

- Dynamic Topic Discovery
- Issue Consolidation
- Finding Generation
- Requirement Generation
- Roadmap Planning
- PRD Generation
- Test Case Generation

Why use AI here:

- Keyword or regex rules cannot reliably discover new topic structures from unseen review data.
- Semantic issue consolidation requires judging underlying user problems, not just shared words.
- Evidence-grounded findings require natural-language synthesis while keeping review evidence attached.
- Requirements, roadmap, PRD, and test case drafts need product-language generation from validated upstream evidence.

All LLM output is treated as untrusted until deterministic validators accept it.

## Deterministic Tasks

Deterministic logic is used where stability, reproducibility, and testability matter:

- URL parsing
- Review normalization
- Text cleaning
- Language detection baseline
- Exact deduplication
- Lexical near duplicate marking
- Statistics
- Evidence counting
- Evidence strength calculation
- Schema validation
- Topic/review ID validation
- Issue/review/topic evidence validation
- Finding support count re-computation
- Priority validation
- Coverage validation
- Traceability validation
- Failure propagation

This split keeps model-generated semantic output flexible while preserving a deterministic safety boundary around IDs, counts, evidence, and downstream eligibility.

## Hallucination Mitigation

The pipeline reduces unsupported model output through:

1. Schema validation at each generated layer.
2. Review ID validation against the processed review dataset.
3. Topic, issue, finding, requirement, roadmap, PRD, and test case reference validation.
4. Rejecting unknown review IDs instead of auto-creating evidence.
5. Re-computing `support_count` from actual evidence.
6. Deterministic evidence strength calculation.
7. Keeping model confidence separate from deterministic evidence strength.
8. Scope overclaim detection for broad unsupported statements.
9. Requirement traceability to findings.
10. Test case traceability to requirements and review evidence.
11. Validator failure causing downstream stages to be skipped.
12. Positive feedback exclusion from product-problem finding generation.
13. Open questions for product parameters not proven by evidence.

## Failure Handling

Failure states are explicit and do not become success states.

Examples:

- Missing API Key
- Authentication Error
- Timeout
- Rate Limit
- Invalid JSON
- Validation Failure
- Empty Dataset
- Missing Demo Cache
- Invalid Demo Cache

Workflow behavior:

```text
Current stage: FAIL
Downstream stages: SKIPPED
Live run: no automatic demo fallback
```

This applies to review providers, model requests, JSON parsing, schema validation, and final traceability validation.

## Evidence, Conflict, and Uncertainty

Evidence is carried forward by IDs:

```text
Test Case
-> Requirement
-> Finding
-> Issue
-> Topic
-> Review
```

The dashboard can drill into review evidence from higher-level entities.

Data limits are not hidden:

- Small samples reduce statistical confidence.
- Conflicting review evidence is retained and reported.
- Model confidence is not treated as a deterministic fact.
- Uncertainty fields are required in model-generated structures.
- Unsupported product parameters are captured as open questions rather than asserted as facts.

## Local Commands

### Backend API

```bash
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Apify Smoke Test

```bash
python -m app.apify_smoke_test
```

Requires `APIFY_API_TOKEN`.

### Apify Data Audit

```bash
python -m app.apify_data_audit
```

Reads existing Apify artifacts and does not call the network.

### Review Processing

```bash
python -m app.process_reviews
```

### Topic Discovery CLI

```bash
python -m app.discover_topics --goal "分析低评分用户对订阅和价格的主要问题"
```

Requires `DEEPSEEK_API_KEY` for production runs.

## Testing

Run all Python unit tests:

```bash
python -m unittest discover -s tests
```

Compile Python files:

```bash
python -m compileall app tests
```

Build the frontend:

```bash
cd frontend
npm run build
```

The exact number of tests is not a documentation contract. Use the local test output or CI output as the current source of truth.

## Project Structure

```text
app/
  providers.py                  ReviewProvider interface and Apple RSS / JSON / CSV providers
  apify_provider.py             Apify review provider
  imports.py                    JSON / CSV import validation and metadata
  review_processing.py          Phase 1 processing pipeline
  topic_discovery.py            Dynamic topic discovery orchestration
  topic_validator.py            Topic schema and evidence validation
  issue_consolidation.py        Issue consolidation orchestration
  issue_validator.py            Issue schema and evidence validation
  issue_type.py                 Deterministic issue type classification
  finding_eligibility.py        Deterministic finding eligibility gate
  finding_generation.py         Evidence-grounded finding generation
  requirement_generation.py     Requirement generation
  roadmap_generation.py         Roadmap planning
  prd_generation.py             PRD generation
  test_case_generation.py       Test case generation
  traceability.py               Full chain validation
  final_validation.py           Runtime and submission validation
  demo.py                       Offline cached demo loader and validator
  demo_cache/                   Built-in offline demo artifacts
  api/                          FastAPI result and workflow APIs
  workflow/                     Backend workflow orchestration and stage adapters
  llm/                          LLMProvider abstraction, mock provider, DeepSeek provider

frontend/
  src/App.jsx                   Workflow UI and dashboard
  src/styles.css                UI styling
  vite.config.js                API proxy configuration

tests/
  Unit tests for providers, processing, validators, generation orchestration, workflow,
  API endpoints, import mode, demo mode, and traceability.
```

## Limitations

- Review coverage is limited by Apple RSS, Apify, and storefront availability.
- The third-party Apify actor can change behavior or availability.
- The App Store may rate limit or change public feeds.
- DeepSeek API availability, authentication, rate limits, and timeout behavior affect live semantic stages.
- LLM output can vary between runs; validators limit but do not eliminate semantic variability.
- Small or narrow review samples reduce statistical confidence.
- Unknown apps may have few or no accessible reviews.
- Mixed-language quality depends on both deterministic preprocessing and model capability.
- Cached Demo is a static presentation artifact, not current live App Store data.
- This project does not use a production database; workflow state is process-local in the current implementation.

## Git History

The project is implemented through phase-based incremental commits. Each major capability is committed separately so reviewers can inspect how the system evolved from review collection through processing, model-driven analysis, traceability, UI, import mode, and cached demo delivery.

## Security Notes

- `.env` is ignored by Git.
- `artifacts/`, `frontend/node_modules/`, `frontend/dist/`, and Python cache files are ignored.
- Provider tokens and model API keys must stay outside the repository.
- Demo cache files are checked in intentionally and are validated for secret-like markers.
