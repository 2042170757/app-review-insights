# LaienTech iOS App Review Analysis and Version Planning Assessment

## Background

This assessment uses the following real iOS app as the primary development and demonstration example:

https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684

If you have access to an overseas network environment, use the U.S. App Store link above. If not, and the U.S. link cannot be opened or redirects, use the China App Store link only to open the app detail page:

https://apps.apple.com/cn/app/workout-for-women-home-gym/id839285684

Regardless of which link is used to open the page, the review data used in this assessment must come from the U.S. App Store storefront.

You are expected to complete a full product analysis workflow around App Store user reviews, covering data collection, review cleaning, review classification, issue analysis, version planning, PRD writing, and test case design. The final results should be presented through a runnable UI.

This assessment focuses on the candidate's vibe coding ability. Candidates should use vibe coding to complete the full process: collecting data, cleaning and analyzing reviews, abstracting product requirements, planning versions, designing test cases, and productizing the analysis workflow into an interactive experience.

## Objective

Build a runnable tool or web application. In the UI, the user should be able to enter a valid U.S. App Store app link. Use the following link as the primary example:

```text
https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
```

The user should also be able to provide an analysis goal or constraint, such as focusing on subscription conversion, workout usability, a specific app version, or low-rating reviews. The system must not depend on app-specific hard-coded categories, findings, requirements, or test cases.

After the user clicks "Start", the system should automatically complete the following workflow and display the results in the UI:

1. Determine the analysis scope based on the user's goal and the available data.
2. Collect review data for the app.
3. Clean, deduplicate, and structure the review data.
4. Dynamically classify and analyze the reviews, rather than relying only on fixed keyword mappings or a predefined issue taxonomy.
5. Evaluate whether the available evidence is sufficient, and identify conflicting feedback, uncertainty, and data limitations.
6. Create an update plan based on the analysis, produce a PRD, and split the scope into multiple versions when necessary.
7. Generate test cases based on the PRD, with each test case linked to its requirement and source user reviews.
8. Validate the traceability chain from reviews to findings, requirements, and test cases. Unsupported conclusions must be removed, revised, or explicitly marked as assumptions.
9. Display the execution progress in the UI, including the stages, intermediate results, validation results, errors, and revisions.
10. Display the interim and final deliverables, including raw reviews, cleaned data, classification results, findings, PRD drafts, and test case drafts.

## AI Requirements

- At least one core semantic task must be model-driven. Suitable tasks include dynamic topic discovery, issue consolidation, evidence-grounded analysis, requirement generation, or test case generation. Implementing all semantic analysis only through fixed keywords, regular expressions, lookup tables, or manually predefined mappings does not meet this requirement.
- Deterministic rules are encouraged where they are appropriate, including data collection, deduplication, field normalization, validation, and safety checks. The submission should explain why rules, statistical methods, or language models were chosen for each stage.
- Every major finding must include its source review IDs or excerpts, supporting sample count, confidence or uncertainty, and any material conflicting evidence. Model-generated conclusions must remain distinguishable from deterministic statistics.
- The submission must document the model and provider used, the main prompts or tool definitions, model configuration, failure-handling strategy, and measures used to reduce hallucinations and unsupported conclusions.
- Hosted APIs, local models, or other model runtimes may be used. Secrets must be supplied through environment configuration and must not be committed to the repository.

## Deliverables

Submit a GitHub project link and ensure the project can run locally.

The GitHub project should include complete source code, dependency configuration, running instructions, an explanation of the data collection method, and any necessary sample output or cached data so that interviewers can review the results even when external network access is unavailable. Cached results must be clearly labeled and must not replace the ability to process a previously unseen input when the required network and model configuration are available.

The application must also support importing review data from a documented JSON or CSV format. During evaluation, interviewers may provide a different valid App Store link, a previously unseen compatible review dataset, or a new analysis goal. The submission will be evaluated on whether it can produce grounded results without app-specific hard coding.

The GitHub project should preserve a complete commit history to show the candidate's implementation process, iteration process, and use of vibe coding.

## Offline Cached Demo Mode

The UI provides two explicit modes:

- `Live Analysis`: runs the configured live providers and model pipeline for the selected App Store source or uploaded JSON/CSV reviews.
- `Cached Demo`: loads a built-in cache for offline interview presentation without calling Apify or DeepSeek.

The cached demo is clearly labeled as `Cached / Demo Data` in the dashboard. It is not a fallback for live failures and must not be treated as a fresh analysis of a new app, new review file, or new analysis goal.

The backend exposes the cached demo through:

```bash
GET /api/demo/run
GET /api/demo/metadata
```

The cache metadata is stored in `app/demo_cache/demo_metadata.json` and contains no API keys or provider tokens.

## Technical Requirements and Notes

- There is no restriction on the tech stack.
- You may use frontend frameworks, backend frameworks, data analysis libraries, visualization libraries, natural language processing models, or large language model APIs.
- You may use public APIs or third-party data collection libraries, but you must clearly explain the data source and its limitations.
- Pay attention to request rate limits and avoid placing abnormal load on the target site.
- Provide a sample environment file or equivalent configuration instructions, but do not include API keys or other secrets.
- A non-runnable document-only submission is not acceptable.

## Evaluation Criteria

This assessment focuses on whether the candidate can turn real user reviews into an executable product plan. The evaluation will mainly consider:

- Whether the data is authentic and reproducible, with a clear explanation of its source and limitations.
- Whether review cleaning, classification, and analysis are reasonable, and whether they surface concrete user problems.
- Whether model-driven semantic analysis adds capability beyond fixed rules and generalizes to previously unseen reviews, apps, and analysis goals.
- Whether findings distinguish evidence, deterministic statistics, model-generated conclusions, uncertainty, and conflicting feedback.
- Whether the PRD is grounded in user problems, with clear requirement boundaries, priorities, and version planning.
- Whether the test cases cover the PRD and can be traced back to the corresponding user reviews.
- Whether the UI clearly presents the workflow and results, and whether the project can run locally with clear delivery instructions.

## Important Notes

- This is not merely a web scraping task, nor is it merely a UI presentation task.
- The core challenge is to identify problems from real user reviews and turn them into executable product requirements and test plans.
- Review data should not be collected by scraping only the visible content of the page. There are more appropriate ways to retrieve App Store review data; candidates are expected to explore them independently and explain their implementation.
- Requirements in the PRD must be traceable to specific user reviews.
- Test cases must be able to verify whether the corresponding requirements solve the problems raised in those reviews.
- The use of an AI coding assistant during implementation does not by itself satisfy the AI requirements. The submitted application must demonstrate model-driven semantic analysis at runtime.
- Interviewers may test the application with previously unseen data, mixed languages, duplicate or conflicting reviews, insufficient evidence, or temporary collection/model failures.
- If the amount of available data is limited or data collection is constrained, state this transparently in the results. Do not fabricate data.

## Phase 0 Review Collector Smoke Test

The current implementation only covers Phase 0: validating the review collection path. It intentionally does not implement the React frontend, full AI pipeline, PRD generation, requirement generation, test case generation, or database integration.

### Requirements

- Python 3.11+
- No third-party Python package is required for Phase 0.

### Run The Smoke Test

```bash
python -m app.collector_smoke_test
```

The command:

1. Parses the target US App Store URL.
2. Prints `app_id` and `storefront`.
3. Requests Apple's public US customer review RSS JSON feed.
4. Fetches real reviews with pagination and a maximum review limit.
5. Prints the first 3 normalized reviews when Apple RSS returns usable review entries.
6. Saves raw Apple RSS responses under `artifacts/raw/`.
7. Saves normalized reviews under `artifacts/normalized/`.
8. Reports structured errors and exits with failure when Apple RSS is unavailable or returns no usable review entries.

### Run Unit Tests

```bash
python -m unittest discover -s tests
```

The unit tests cover App Store URL parsing, invalid URLs, missing app ids, normalized review constraints, and offline JSON/CSV import providers.

### Data Source

The live collector uses Apple's public customer review RSS JSON endpoint:

```text
https://itunes.apple.com/{storefront}/rss/customerreviews/page={page}/id={apple_store_app_id}/sortby=mostrecent/json
```

For the Phase 0 smoke test, the storefront is explicitly resolved from the App Store URL and passed to `AppleRSSProvider`. The target run uses `US`.

### Data Limits

- Apple RSS is a public feed and may be unavailable, rate limited, incomplete, or changed by Apple without notice.
- Results are scoped to a storefront, such as `US`.
- Pagination is limited by Apple's RSS behavior and by this smoke test's configured `max_pages` and `max_reviews`.
- Phase 0 does not claim complete historical coverage.
- If Apple RSS fails or returns an empty feed, the smoke test reports structured errors and does not fabricate review data.

## Phase 0.5 App Store Connect API Capability Probe

Phase 0.5 adds a diagnostic command only. It does not add a full App Store Connect review provider, frontend, AI pipeline, or database integration.

### Required Environment Variables

Install the Phase 0.5 JWT dependency first:

```bash
pip install -r requirements.txt
```

```bash
APPSTORE_ISSUER_ID=...
APPSTORE_KEY_ID=...
APPSTORE_PRIVATE_KEY_PATH=/path/to/AuthKey_XXXXXXXXXX.p8
```

Do not commit Apple private keys or API secrets to this repository.

### Run The Probe

```bash
python -m app.appstore_connect_probe
```

The probe:

1. Checks that all required environment variables are present.
2. Checks that the private key file exists.
3. Generates a local ES256 JWT for App Store Connect API authentication.
4. Calls App Store Connect `GET /v1/apps` to list apps visible to the current API key.
5. Looks for the target App Store ID `839285684`.
6. If the target app is visible, calls `GET /v1/apps/{app_resource_id}/customerReviews`.
7. Saves a sanitized diagnostic report to `artifacts/probes/appstore_connect_probe.json`.

The output distinguishes local JWT/configuration failures, HTTP 401, HTTP 403, API access not enabled, target app not visible in the current account, insufficient app permissions, and other HTTP or network errors.

### App Store Connect API Limits

- App Store Connect API requires an Apple Developer/App Store Connect account with API key access.
- The current account and API key must be allowed to see the target app.
- This API is not a public arbitrary App Store review API.
- Do not confuse App Store URL accessibility with App Store Connect API access. A public app page can be reachable while the API key has no access to that app's private App Store Connect resources.
- This probe never prints or stores the JWT, private key contents, or other secrets.

## Phase 0.75 Apify Provider

Phase 0.75 adds a pluggable third-party Review Provider for validating a real US App Store review collection path. It does not implement AI, LLM workflows, database storage, React frontend, PRD generation, requirement generation, test case generation, roadmap generation, or the full analysis pipeline.

### Configuration

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a local `.env` or otherwise export:

```bash
APIFY_API_TOKEN=
```

The smoke test loads the project-root `.env` file with `python-dotenv` at startup. Existing system environment variables have priority over `.env` values. The repository includes `.env.example` with the required variable name only. Do not commit real Apify tokens.

### Run The Smoke Test

```bash
python -m app.apify_smoke_test
```

The smoke test:

1. Checks `APIFY_API_TOKEN`.
2. Parses the target App Store URL.
3. Calls the Apify actor `apihq/app-store-reviews-scraper`.
4. Requests US reviews for App Store app ID `839285684`.
5. Requests at most 50 recent reviews.
6. Converts results to the same Unified Review Schema used by the rest of the project.
7. Saves raw and normalized outputs.

### Artifacts

```text
artifacts/raw/apify/raw_response.json
artifacts/normalized/apify/normalized_reviews.json
artifacts/normalized/apify/dataset_metadata.json
```

### Provider Limits

- Apify is a third-party review collection provider.
- The review source is the Apple App Store US storefront through the third-party collection service.
- Apify requires an API token.
- Data volume, available fields, request frequency, and accuracy depend on the third-party provider and Apple's storefront behavior.
- The current smoke test requests at most 50 recent reviews.
- This provider is not Apple official App Store Connect API.
- It does not guarantee complete historical coverage.
- The project core analysis engine should not depend on Apify specifically. Any provider that emits the Unified Review Schema can feed later stages.
