# App Review Insights

App Review Insights 是一个可本地运行的 iOS App Store 评论分析工作台。它把真实或导入的用户评论转化为证据驱动的产品交付物，并在 UI 中展示每一步的来源、验证结果、错误、警告和追溯链。

核心链路：

```text
Review
↓
Topic
↓
Issue
↓
Finding
↓
Requirement
↓
Version
↓
PRD
↓
Acceptance Criteria
↓
Test Case
↓
Source Review
```

主要真实示例：

```text
App: Workout for Women: Home Gym
App Store URL: https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
App ID: 839285684
Review Territory: US
```

`839285684` 只是示例 App ID，不是业务硬编码。用户可以输入其他美国 App Store URL，例如 Phase 10c 中验证过的 Wikipedia App。

## 项目目标

本项目用于 LaienTech 最终考题验收，目标是证明系统可以：

- 从真实 US App Store 评论或 JSON / CSV 导入数据开始分析。
- 动态识别 Topic、Issue、Finding，而不是依赖固定关键词或固定 App 输出。
- 生成可追溯的 Requirement、Roadmap、PRD 和 Test Case。
- 保留 Evidence、Uncertainty、Conflict，并把模型输出交给确定性 Validator 审核。
- 在 UI 中展示完整 Workflow、运行状态、失败传播、验证结果和证据链。
- 提供 Cached Demo，供没有外部 Provider 凭据时离线查看，但不会用 Demo 冒充 Live 结果。

## 本地运行

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

该项目使用 Python、FastAPI、Uvicorn、python-dotenv、Apify client、multipart upload 支持，以及若干确定性校验模块。

### 2. 配置本地凭据

从 `.env.example` 复制一份本地 `.env`，或在系统环境变量中配置 Apify 与 DeepSeek 所需凭据。

规则：

- 系统环境变量优先于 `.env`。
- `.env` 已被 Git 忽略，不应提交。
- Provider 代码不会打印凭据内容。
- Cached Demo 不需要外部 Provider 凭据。

DeepSeek 运行参数默认值：

```text
Provider: DeepSeek
Model: deepseek-v4-flash
thinking: disabled
max_tokens: 3000
temperature: 0.2
stream: false
timeout: 60
response_format: {"type":"json_object"}
```

部分大输入生成阶段会在已验证配置范围内使用更高的 `max_tokens`，并在 Model Registry 中记录实际值。

### 3. 启动 Backend

```bash
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8000
```

这是当前代码的实际 Backend 启动方式。

### 4. 启动 Frontend

```bash
cd frontend
npm install
npm run dev
```

Vite dev server 会把 `/api` 代理到 `http://127.0.0.1:8000`。打开终端显示的本地 URL，通常是：

```text
http://127.0.0.1:5173/
```

### 5. 生产构建

```bash
cd frontend
npm run build
```

根目录没有 `package.json`，不要从根目录执行 `npm run build`。

## 快速体验

在 UI 中选择：

```text
Mode: Live Analysis
Data Source: App Store
App Store URL: https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684
Analysis Goal: 分析低评分用户对订阅和价格的主要问题
Analysis Focus: 产品问题
Rating Constraint: 全部评分
```

然后点击“开始分析”。

也可以把 Rating Constraint 设置为 `1-2 Stars`，系统会显示：

- Reviews Collected
- Reviews In Scope
- Excluded by Constraint
- Constraint

并保证 Topic / Finding / Requirement 使用的 evidence 不来自被排除的 Review。

## UI 工作流

UI 支持：

- App Store URL 输入
- Analysis Goal 输入
- Analysis Focus 选择
- Rating Constraint 选择
- Data Source 选择
- Start Analysis
- Workflow Progress
- Intermediate Results
- Errors / Warnings / Revisions
- Evidence Drill-down
- Traceability
- Runtime Validation
- Submission Validation

完整 Workflow：

```text
Scope
Collection
Processing
Topic Discovery
Issue Consolidation
Finding Generation
Requirement Generation
Roadmap
PRD
Test Case
Traceability
```

Dashboard 页面包括：

- Overview
- Reviews
- Processing
- Topics
- Issues
- Findings
- Requirements
- Roadmap
- PRDs
- Test Cases
- Traceability
- Validation
- Diagnostics

## Analysis Focus

系统支持三种分析目标类型：

- Product Problems：分析用户痛点、摩擦和产品问题。
- Positive Feedback：分析用户认可、满意、值得保留的体验。
- Problems + Positive Feedback：同时保留问题型 Finding 与正向反馈 Finding。

Positive Feedback 不会被强行改写成 Product Problem。进入 Requirement 时，正向反馈会生成保留型需求；如果证据不足，系统允许不生成无根据的后续交付物。

## 数据采集

### Apple RSS

`AppleRSSProvider` 使用 Apple public customer review RSS JSON feed：

```text
https://itunes.apple.com/{storefront}/rss/customerreviews/page={page}/id={apple_store_app_id}/sortby=mostrecent/json
```

说明：

- Apple RSS 是公开数据源。
- 数据受 Apple storefront、可用页数和字段结构限制。
- 不保证完整历史覆盖。
- 通过统一 `ReviewProvider` 接口接入。

### Apify

`ApifyReviewProvider` 使用第三方 Apify actor：

```text
apihq/app-store-reviews-scraper
```

当前 live smoke path 对主要示例请求最多 50 条近期 US 评论。

说明：

- Apify 是第三方采集 Provider，不是 Apple 官方 App Store Connect。
- 评论来源仍是 Apple App Store US storefront。
- 可用性、字段、频率和准确性受 Apify 与 Apple storefront 共同影响。
- Live Analysis 不会在失败时自动 fallback 到 Cached Demo。

### Raw Evidence Preservation

采集、模型生成和验证阶段都会保存原始或中间输出到 `artifacts/` 下的 run 目录。`artifacts/` 被 Git 忽略，不进入提交。

## JSON / CSV Import

UI 支持上传 JSON 或 CSV 评论数据。

操作：

1. 选择 `Live Analysis`。
2. 选择 `JSON` 或 `CSV`。
3. 上传文件。
4. 查看 Preview。
5. 确认 Record Count、Valid Count、Invalid Count、Warnings。
6. 点击“开始分析”。

导入数据会标记为：

- Imported JSON
- Imported CSV

Imported Dataset 不等于 App Store Live Collection。如果导入数据没有 territory，UI 显示：

```text
Unknown / Not provided
```

系统不会伪造 `US`。

### JSON 格式

JSON 可以是 Review 列表，也可以是包含 `reviews` 的对象：

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

### CSV 格式

CSV 必须包含 header，至少提供：

```text
rating,created_at,title,body
```

示例：

```csv
id,app_id,territory,rating,title,body,created_at
review-001,example-app,US,2,Too expensive,The subscription price feels too high.,2026-01-01T00:00:00Z
```

如果 `id` 缺失，Import Provider 会根据内容生成稳定 ID。如果 `app_id` 缺失，可以由 App Context URL 补充。

## Review 清洗与处理

`app/review_processing.py` 负责确定性处理：

- Schema Validation
- Normalization
- Text Cleaning
- Language Detection baseline
- Exact Deduplication
- Near Duplicate Candidate
- Statistics
- Scope Filtering

Exact Duplicate 会被确定性去重。Near Duplicate 只做候选标记，语义相近但含义不同的 Review 不会因为相似就被删除。

## 动态语义分析

DeepSeek 用于以下模型驱动任务：

- Dynamic Topic Discovery
- Issue Semantic Analysis
- Finding Generation
- Requirement Generation
- Roadmap Planning
- PRD Generation
- Test Case Generation

为什么使用 LLM：

- Topic 结构需要从陌生评论中动态发现，不能只靠固定关键词。
- Issue Consolidation 需要判断 underlying user problem、causal relationship、user intent 和 evidence overlap。
- Finding 需要在保留 Review Evidence 的前提下做自然语言归纳。
- Requirement、Roadmap、PRD 和 Test Case 需要从已验证上游证据生成产品语言交付物。

所有 LLM 输出都视为不可信，只有通过确定性 Validator 后才进入下一阶段。

## Provider 架构

LLM 访问统一在 `app/llm/` 中封装：

```text
LLMProvider
↓
DeepSeekProvider / MockLLMProvider
↓
Topic / Issue / Finding / Requirement / Roadmap / PRD / Test Case
↓
Validator
```

业务模块不直接调用前端或浏览器中的 DeepSeek 能力。Frontend 不持有 Provider 凭据，Browser 不直接访问 DeepSeek。

## Evidence / Uncertainty / Conflict

Finding 必须包含：

- `review_ids`
- `support_count`
- `confidence`
- `uncertainty`
- `conflicting_review_ids`

确定性 Evidence Engine 会重新计算：

- support_count
- unique support count
- evidence strength
- evidence limitations

Model Confidence 与 Deterministic Evidence Strength 分离展示。单条 evidence 不会被扩张成“多数用户”或“所有用户”的群体确定性。

Conflict Evidence 不会被自动删除。正反两类 Review 会保留在 Finding 与 Evidence Report 中。

## Requirement / Roadmap / PRD

### Requirement

Requirement 必须：

- 追溯到 Finding
- 追溯到 Review
- 有 Priority
- 有 Priority Rationale
- Acceptance Criteria 非空
- 不泄漏技术实现
- 不把 Positive Feedback 伪造成 Product Problem

### Roadmap

Roadmap 版本 ID 合同：

```text
Scheduled Versions: V1, V2, V3
Deferred: Deferred
```

禁止生成 `V4`、`V5`、`Future` 或任意自造 version ID。Validator 会确定性拦截。

Roadmap 必须产品导向，不能只是机械的 P1/P2 分桶；Version Goal 应概括内部 Requirement，并保留风险与 success metrics。

### PRD

PRD 必须包含：

- Goal
- Problem / Value Statement
- Requirements
- Non-Goals
- Success Metrics
- Risks
- Open Questions
- Evidence Summary

如果没有可靠的可衡量指标，允许 `success_metrics = []`，UI 显示：

```text
No validated success metrics defined yet.
```

未由 evidence 支持的目标数值必须进入 Open Questions，不能编造无依据百分比目标。

## Test Case / Traceability

每个 Test Case 必须包含：

- `requirement_id`
- `acceptance_criteria_ids`
- `source_review_ids`
- `title`
- `preconditions`
- `steps`
- `expected_result`
- `test_type`
- `priority`

`source_review_ids` 不是新 evidence，而是 Requirement → Finding → Review 的显式下游追溯。

完整链路：

```text
Review
↓
Topic
↓
Issue
↓
Finding
↓
Requirement
↓
Version
↓
PRD
↓
Acceptance Criteria
↓
Test Case
↓
Source Review
```

最终验证包括：

- Forward Traceability
- Backward Traceability
- Evidence Traceability
- Explicit Test Case → Review Link
- Artifact Consistency

Expected Exclusion 会被明确标记，不会显示为 Broken Traceability。

## AI / Deterministic Boundary

模型驱动：

- Topic
- Issue
- Finding
- Requirement
- Roadmap
- PRD
- Test Case

确定性逻辑：

- URL Parsing
- Review Normalization
- Cleaning
- Exact Deduplication
- Statistics
- Scope Filter
- Evidence Counting
- Evidence Strength
- Validation
- Priority Validation
- Coverage
- Traceability
- Failure Propagation
- Security Checks

Model Registry 记录：

- Provider
- Model
- Thinking
- Max Tokens
- Temperature
- Timeout
- Stream
- Response Format

## 防幻觉策略

系统通过以下机制降低模型幻觉风险：

- Schema Validation
- Review ID Validation
- Topic / Issue / Finding / Requirement 引用校验
- Evidence Traceability
- `support_count` 重算
- Evidence Strength
- Scope Validation
- Requirement Validation
- Roadmap Version ID Guard
- PRD Validation
- Test Case Validation
- Positive Feedback Exclusion
- Uncertainty 必填
- Conflict Evidence 保留
- Downstream Skip
- Invalid JSON Recovery
- 有限 Retry

模型或 Provider 失败时不会伪造结果，也不会用 Cached Demo 冒充 Live 成功。

## Cached Demo

Cached Demo 用于离线演示：

- 明确显示 Cached / Demo Data。
- 显示 Built-in Demo Cache。
- 不调用 Apify。
- 不调用 DeepSeek。
- 使用独立 Demo Run。
- 不污染 Live Run。
- 不是 Live Failure 的 fallback。

Demo 数据位于：

```text
app/demo_cache/
```

Demo 入口：

```text
GET /api/demo/run
GET /api/demo/metadata
```

## Error / Failure Handling

失败语义：

```text
Current Stage: failed
Downstream Stages: skipped
Runtime Validation: fail
```

覆盖场景：

- Missing credential
- Authentication Error
- Timeout
- Rate Limit
- Invalid JSON
- Schema Failure
- Evidence Failure
- Provider Failure
- Empty Dataset
- Invalid Demo Cache

Insufficient Evidence 会明确标记为 Evidence Insufficient 或 Low Evidence Strength，不能伪造成高确定性成功。

## 数据限制

项目明确保留以下限制：

- Apple RSS coverage 受 Apple public feed 限制。
- Apify 是第三方依赖。
- Storefront / Territory 会影响 Review 范围。
- Provider 可用性会影响 Live Analysis。
- DeepSeek 可用性、认证、限流和超时会影响模型阶段。
- LLM 输出有不确定性，Validator 只能拦截结构、引用和证据问题，不能保证每次语义完全一致。
- 小样本不能代表全部用户。
- Mixed Language 质量依赖确定性预处理与模型能力。
- 网络失败会导致当前 stage failed、后续 skipped。
- Cached Demo 是静态展示数据，不是实时数据。
- 当前实现不使用生产数据库，Workflow state 是本地进程内状态。

## 测试

运行 Python unit tests：

```bash
python -m unittest discover -s tests
```

编译 Python 文件：

```bash
python -m compileall app tests
```

构建 Frontend：

```bash
cd frontend
npm run build
```

测试数量以本地命令输出为准，不把具体数量作为 README 合同。

## 项目结构

```text
app/
  providers.py                  ReviewProvider interface and Apple RSS / JSON / CSV providers
  apify_provider.py             Apify review provider
  imports.py                    JSON / CSV import validation and metadata
  review_processing.py          Review processing pipeline
  topic_discovery.py            Dynamic topic discovery orchestration
  topic_schema.py               Topic schema
  topic_validator.py            Topic validation
  issue_consolidation.py        Issue consolidation orchestration
  issue_schema.py               Issue schema
  issue_validator.py            Issue validation
  issue_type.py                 Deterministic issue type classification
  finding_eligibility.py        Deterministic finding eligibility gate
  finding_generation.py         Evidence-grounded finding generation
  finding_schema.py             Finding schema
  finding_validator.py          Finding validation
  requirement_generation.py     Requirement generation
  requirement_schema.py         Requirement schema
  requirement_validator.py      Requirement validation
  roadmap_planner.py            Roadmap planning
  roadmap_schema.py             Roadmap schema
  roadmap_validator.py          Roadmap validation
  prd_generator.py              PRD generation
  prd_schema.py                 PRD schema
  prd_validator.py              PRD validation
  test_case_generator.py        Test case generation
  test_case_schema.py           Test case schema
  test_case_validator.py        Test case validation
  traceability.py               Full chain validation
  final_validation.py           Runtime and submission validation
  model_registry.py             Model metadata registry
  demo.py                       Offline cached demo loader and validator
  demo_cache/                   Built-in offline demo artifacts
  api/                          FastAPI result and workflow API
  workflow/                     Backend workflow orchestration and stage adapters
  llm/                          LLMProvider abstraction, mock provider, DeepSeek provider, JSON recovery

frontend/
  src/App.jsx                   Workflow UI and dashboard
  src/styles.css                UI styling
  vite.config.js                API proxy configuration

tests/
  Unit tests for providers, processing, validators, generation orchestration,
  workflow, API endpoints, import mode, demo mode, traceability, and UI-adjacent adapters.

artifacts/
  Local generated outputs. This directory is ignored by Git.
```

## 最终泛化验证

Phase 10c final matrix 位于：

```text
artifacts/final_validation/generalization_matrix_final_v3.json
```

最终结果：

```text
14 PASS
0 FAIL
0 UNSUPPORTED
```

覆盖：

- Unknown Goal
- Unknown Constraint
- JSON Import
- CSV Import
- Mixed Language
- Unknown App
- Duplicate Handling
- Conflict Handling
- Insufficient Evidence
- Provider Failure
- Positive Focus
- Mixed Focus
- Problem Focus Regression
- Hardcoding Audit

Unknown App Wikipedia 已完成完整链路：

```text
Collection
Processing
Topic
Issue
Finding
Requirement
Roadmap
PRD
Test Cases
Traceability
```

## UI 最终验收

Phase 10d UI Final Acceptance 已通过。已验证：

- Live Analysis
- Cached Demo
- JSON Upload
- CSV Upload
- Rating Constraint
- Positive Focus
- Mixed Focus
- Evidence Drill-down
- Source Review
- Traceability
- Validation
- Warning
- Revision panel
- Error state
- Run Isolation

## Git 开发历史

项目采用 Phase-based Git Commit。每个阶段独立提交，便于审查从 Review Collection、Processing、Dynamic Semantic Analysis、Traceability 到 UI、Import、Cached Demo、Generalization Fix 的演进过程。

不要为了展示历史在文档中硬编码大量 commit hash；以 `git log` 为当前事实来源。

## 安全说明

- `.env` 已被 Git 忽略。
- `artifacts/` 已被 Git 忽略。
- `frontend/node_modules/` 已被 Git 忽略。
- `frontend/dist/` 已被 Git 忽略。
- Python cache 文件已被 Git 忽略。
- Provider 凭据只应存在于本地环境或本地 `.env`。
- Frontend 不持有 Provider 凭据。
- Browser 不直接调用 DeepSeek。
- Demo cache 会检查疑似敏感内容。

## 最终交付状态

当前项目已进入最终交付状态：

- Phase 10c Live Generalization Validation: COMPLETE
- Phase 10d UI Final Acceptance: PASS
- Phase 10e Final Exam Acceptance: 通过最终验收 artifact 记录

最终验收 artifact：

```text
artifacts/final_validation/final_exam_acceptance.json
artifacts/final_validation/final_exam_summary.json
```

这些 artifact 是本地生成结果，位于 ignored 的 `artifacts/` 中，不进入 Git。
