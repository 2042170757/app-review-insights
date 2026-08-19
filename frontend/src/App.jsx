import { useEffect, useMemo, useState } from 'react'
import { STAGE_LABELS, UI_LABELS, t, tErrorType, tFocus, tSource, tStage, tStatus } from './i18n'

const DEFAULT_APP_URL = 'https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684'
const DEFAULT_GOAL = '分析低评分用户对订阅和价格的主要问题'
const DEFAULT_ANALYSIS_FOCUS = 'problem_analysis'
const DEMO_APP_URL = DEFAULT_APP_URL
const DEMO_GOAL = DEFAULT_GOAL
const DEMO_ANALYSIS_FOCUS = DEFAULT_ANALYSIS_FOCUS
const analysisFocusOptions = [
  { value: 'problem_analysis', label: tFocus('problem_analysis') },
  { value: 'positive_feedback_analysis', label: tFocus('positive_feedback_analysis') },
  { value: 'mixed_analysis', label: tFocus('mixed_analysis') },
]
const ratingConstraintOptions = [
  { value: 'all', label: '全部评分', constraints: {} },
  { value: '1-2', label: '1-2 星', constraints: { rating: { min: 1, max: 2 } } },
  { value: '1-3', label: '1-3 星', constraints: { rating: { min: 1, max: 3 } } },
  { value: '4-5', label: '4-5 星', constraints: { rating: { min: 4, max: 5 } } },
]

const statusMeta = {
  pending: { symbol: '○', label: tStatus('pending') },
  running: { symbol: '●', label: tStatus('running') },
  completed: { symbol: '✓', label: tStatus('completed') },
  failed: { symbol: '✕', label: tStatus('failed') },
  skipped: { symbol: '⊘', label: tStatus('skipped') },
}

const resultEndpoints = {
  reviews: '/reviews',
  topics: '/topics',
  issues: '/issues',
  findings: '/findings',
  requirements: '/requirements',
  roadmap: '/roadmap',
  prd: '/prd',
  testCases: '/test-cases',
  traceability: '/traceability',
  validation: '/validation',
  diagnostics: '/errors',
  warnings: '/warnings',
  revisions: '/revisions',
  metadata: '/metadata',
}

const tabs = [
  { id: 'overview', label: t('Overview') },
  { id: 'reviews', label: t('Reviews') },
  { id: 'processing', label: t('Processing') },
  { id: 'topics', label: t('Topics') },
  { id: 'issues', label: t('Issues') },
  { id: 'findings', label: t('Findings') },
  { id: 'requirements', label: t('Requirements') },
  { id: 'roadmap', label: t('Roadmap') },
  { id: 'prd', label: t('PRDs') },
  { id: 'testCases', label: t('Test Cases') },
  { id: 'traceability', label: t('Traceability') },
  { id: 'validation', label: t('Validation') },
  { id: 'diagnostics', label: t('Diagnostics') },
]

function App() {
  const [appUrl, setAppUrl] = useState(DEFAULT_APP_URL)
  const [analysisGoal, setAnalysisGoal] = useState(DEFAULT_GOAL)
  const [analysisFocus, setAnalysisFocus] = useState(DEFAULT_ANALYSIS_FOCUS)
  const [ratingConstraint, setRatingConstraint] = useState('all')
  const [runMode, setRunMode] = useState('live')
  const [sourceType, setSourceType] = useState('app_store')
  const [importFile, setImportFile] = useState(null)
  const [importPreview, setImportPreview] = useState(null)
  const [importError, setImportError] = useState(null)
  const [isImporting, setIsImporting] = useState(false)
  const [runId, setRunId] = useState(null)
  const [runState, setRunState] = useState(null)
  const [results, setResults] = useState({})
  const [requestError, setRequestError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedTab, setSelectedTab] = useState('overview')
  const [selectedStageId, setSelectedStageId] = useState(null)
  const [selectedEntity, setSelectedEntity] = useState(null)
  const [reviewFilters, setReviewFilters] = useState({ rating: 'all', language: 'all', search: '', page: 1 })

  const progressValue = useMemo(() => {
    if (!runState) return 0
    return Math.max(0, Math.min(100, Number(runState.progress || 0)))
  }, [runState])

  const selectedStage = useMemo(() => {
    if (!runState?.stages?.length) return null
    return runState.stages.find((stage) => stage.stage === selectedStageId) || runState.stages[0]
  }, [runState, selectedStageId])

  const lookup = useMemo(() => buildLookup(results), [results])

  useEffect(() => {
    if (!runId || !runState || !['queued', 'running'].includes(runState.status)) return undefined
    const timer = window.setInterval(() => {
      refreshRun(runId)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [runId, runState?.status])

  useEffect(() => {
    if (!runId) return
    refreshResults(runId)
  }, [runId, runState?.status, runState?.updated_at])

  async function startRun(event) {
    event.preventDefault()
    setRequestError(null)
    setIsSubmitting(true)
    setResults({})
    setSelectedEntity(null)
    try {
      if (runMode === 'demo') {
        const payload = await createDemoRun()
        setRunId(payload.run_id)
        setRunState(payload)
        if (payload.stages?.length) {
          setSelectedStageId(payload.stages[0].stage)
        }
        await refreshResults(payload.run_id)
        return
      }
      const response = sourceType === 'app_store' ? await createAppStoreRun() : await createImportRun()
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(formatApiError(payload.detail || '无法创建运行'))
      }
      setRunId(payload.run_id)
      await refreshRun(payload.run_id)
    } catch (error) {
      setRequestError(error.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function createDemoRun() {
    const response = await fetch('/api/demo/run')
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(formatApiError(payload.detail || '无法加载缓存演示运行'))
    }
    return payload
  }

  async function createAppStoreRun() {
    const constraints = constraintsForRating(ratingConstraint)
    return fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        app_url: appUrl,
        analysis_goal: analysisGoal,
        analysis_focus: analysisFocus,
        ...(Object.keys(constraints).length ? { constraints } : {}),
      }),
    })
  }

  async function createImportRun() {
    if (!importPreview?.import_id) {
      throw new Error('开始分析前必须先完成导入文件预览。')
    }
    const constraints = constraintsForRating(ratingConstraint)
    return fetch('/api/runs/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        import_id: importPreview.import_id,
        app_url: appUrl,
        analysis_goal: analysisGoal,
        analysis_focus: analysisFocus,
        ...(Object.keys(constraints).length ? { constraints } : {}),
      }),
    })
  }

  async function handleSourceChange(nextSource) {
    setSourceType(nextSource)
    setImportFile(null)
    setImportPreview(null)
    setImportError(null)
  }

  function handleRunModeChange(nextMode) {
    setRunMode(nextMode)
    setImportFile(null)
    setImportPreview(null)
    setImportError(null)
    if (nextMode === 'demo') {
      setSourceType('app_store')
      setAppUrl(DEMO_APP_URL)
      setAnalysisGoal(DEMO_GOAL)
      setAnalysisFocus(DEMO_ANALYSIS_FOCUS)
      setRatingConstraint('all')
    }
  }

  function handleAppUrlChange(value) {
    setAppUrl(value)
    if (sourceType !== 'app_store') {
      setImportPreview(null)
      setImportError(null)
    }
  }

  async function handleImportFileChange(event) {
    const file = event.target.files?.[0] || null
    setImportFile(file)
    setImportPreview(null)
    setImportError(null)
    if (!file) return
    const expectedExtension = sourceType === 'json' ? '.json' : '.csv'
    if (!file.name.toLowerCase().endsWith(expectedExtension)) {
      setImportError({ type: 'Invalid Extension', message: `请上传 ${expectedExtension} 文件。` })
      return
    }
    setIsImporting(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('app_url', appUrl)
      const response = await fetch(`/api/import/${sourceType}`, {
        method: 'POST',
        body: formData,
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(formatApiError(payload.detail || '导入失败'))
      }
      setImportPreview(payload)
    } catch (error) {
      setImportError({ type: 'Import Error', message: error.message })
    } finally {
      setIsImporting(false)
    }
  }

  async function refreshRun(targetRunId = runId) {
    if (!targetRunId) return
    setRequestError(null)
    try {
      const response = await fetch(`/api/runs/${targetRunId}`)
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || '无法加载运行')
      }
      setRunState(payload)
      if (!selectedStageId && payload.stages?.length) {
        setSelectedStageId(payload.stages[0].stage)
      }
    } catch (error) {
      setRequestError(error.message)
    }
  }

  async function refreshResults(targetRunId = runId) {
    if (!targetRunId) return
    const entries = await Promise.all(
      Object.entries(resultEndpoints).map(async ([key, suffix]) => {
        try {
          const response = await fetch(`/api/runs/${targetRunId}${suffix}`)
          const payload = await response.json()
          return [key, response.ok ? payload : { available: false, error: payload.detail || 'Unavailable' }]
        } catch (error) {
          return [key, { available: false, error: error.message }]
        }
      }),
    )
    setResults(Object.fromEntries(entries))
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>{UI_LABELS.appTitle}</h1>
          <p>{UI_LABELS.appSubtitle}</p>
        </div>
        <div className="top-status">
          <StatusPill value={runState?.runtime_validation_status || 'pending'} label="Backend Analysis" />
          <StatusPill value={runState?.submission_validation_status || 'pending'} label="Final Submission" />
        </div>
      </header>

      <section className="control-strip">
        <form onSubmit={startRun} className="run-form">
          <label className="field app-url">
            <span>{runMode === 'demo' ? UI_LABELS.demoAppUrl : sourceType === 'app_store' ? UI_LABELS.appStoreUrl : UI_LABELS.appContextUrl}</span>
            <input
              value={appUrl}
              onChange={(event) => handleAppUrlChange(event.target.value)}
              placeholder="https://apps.apple.com/us/app/example/id123"
              disabled={runMode === 'demo'}
            />
          </label>
          <label className="field goal">
            <span>{UI_LABELS.analysisGoal}</span>
            <textarea
              value={analysisGoal}
              onChange={(event) => setAnalysisGoal(event.target.value)}
              rows={2}
              placeholder="分析用户评论中的主要产品问题、用户体验问题和改进机会。"
              disabled={runMode === 'demo'}
            />
          </label>
          <label className="field focus-field">
            <span>{UI_LABELS.analysisFocus}</span>
            <select
              value={analysisFocus}
              onChange={(event) => setAnalysisFocus(event.target.value)}
              disabled={runMode === 'demo'}
            >
              {analysisFocusOptions.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field constraint-field">
            <span>{UI_LABELS.analysisConstraints}</span>
            <select
              value={ratingConstraint}
              onChange={(event) => setRatingConstraint(event.target.value)}
              disabled={runMode === 'demo'}
            >
              {ratingConstraintOptions.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <fieldset className="source-group">
            <legend>{UI_LABELS.mode}</legend>
            <label>
              <input
                type="radio"
                name="mode"
                value="live"
                checked={runMode === 'live'}
                onChange={(event) => handleRunModeChange(event.target.value)}
              />
              <span>{UI_LABELS.liveAnalysis}</span>
            </label>
            <label>
              <input
                type="radio"
                name="mode"
                value="demo"
                checked={runMode === 'demo'}
                onChange={(event) => handleRunModeChange(event.target.value)}
              />
              <span>{UI_LABELS.cachedDemo}</span>
            </label>
          </fieldset>
          <fieldset className="source-group">
            <legend>{UI_LABELS.dataSource}</legend>
            <label>
              <input
                type="radio"
                name="source"
                value="app_store"
                checked={sourceType === 'app_store'}
                onChange={(event) => handleSourceChange(event.target.value)}
                disabled={runMode === 'demo'}
              />
              <span>App Store 实时数据</span>
            </label>
            <label>
              <input
                type="radio"
                name="source"
                value="json"
                checked={sourceType === 'json'}
                onChange={(event) => handleSourceChange(event.target.value)}
                disabled={runMode === 'demo'}
              />
              <span>JSON 导入</span>
            </label>
            <label>
              <input
                type="radio"
                name="source"
                value="csv"
                checked={sourceType === 'csv'}
                onChange={(event) => handleSourceChange(event.target.value)}
                disabled={runMode === 'demo'}
              />
              <span>CSV 导入</span>
            </label>
          </fieldset>
          <div className="actions">
            <button type="submit" disabled={isSubmitting || isImporting || (runMode === 'live' && sourceType !== 'app_store' && !importPreview?.import_id)}>
              {isSubmitting ? UI_LABELS.creatingRun : runMode === 'demo' ? UI_LABELS.loadCachedDemo : UI_LABELS.startAnalysis}
            </button>
            <button type="button" className="secondary" onClick={() => refreshRun()} disabled={!runId}>
              {UI_LABELS.refresh}
            </button>
          </div>
          {runMode === 'demo' ? <DemoModeNotice compact /> : null}
          {runMode === 'live' && sourceType !== 'app_store' ? (
            <ImportPanel
              sourceType={sourceType}
              importFile={importFile}
              importPreview={importPreview}
              importError={importError}
              isImporting={isImporting}
              onFileChange={handleImportFileChange}
            />
          ) : null}
        </form>
        {requestError ? <div className="message error-message">{requestError}</div> : null}
      </section>

      <ModeBanner runState={runState} results={results} runMode={runMode} />

      <section className="run-header">
        <Metric label="Run Status" value={runState?.status || 'not_started'} />
        <Metric label="Mode" value={results.metadata?.data?.display_source || (runMode === 'demo' ? 'Cached / Demo Data' : 'Live Analysis')} />
        <Metric label="Current Stage" value={runState?.current_stage || 'none'} valueFormatter={tStage} />
        <Metric label="Run ID" value={runState?.run_id || 'none'} mono />
        <Metric label="App ID" value={runState?.app_id || 'unknown'} />
        <Metric label="Review Territory" value={results.metadata?.data?.territory || results.reviews?.dataset_metadata?.territory || runState?.storefront || 'US'} />
        <div className="progress-block">
          <div className="progress-label">
            <span>{t('Overall Progress')}</span>
            <strong>{progressValue.toFixed(1)}%</strong>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${progressValue}%` }} />
          </div>
        </div>
      </section>
      <FailurePropagationNotice diagnostics={results.diagnostics} runState={runState} />

      <section className="dashboard-grid">
        <aside className="workflow-pane">
          <h2>{t('Workflow Timeline')}</h2>
          <StageList
            stages={runState?.stages || []}
            selectedStageId={selectedStage?.stage}
            onSelect={(stageId) => setSelectedStageId(stageId)}
          />
          <StageDetail stage={selectedStage} revisions={runState?.revisions || []} />
        </aside>

        <section className="results-pane">
          <nav className="tabs" aria-label="结果分区">
            {tabs.map((tab) => (
              <button
                type="button"
                key={tab.id}
                className={selectedTab === tab.id ? 'active' : ''}
                onClick={() => setSelectedTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
          <DashboardTab
            tab={selectedTab}
            runState={runState}
            results={results}
            lookup={lookup}
            filters={reviewFilters}
            setFilters={setReviewFilters}
            setSelectedEntity={setSelectedEntity}
            setSelectedTab={setSelectedTab}
          />
        </section>

        <aside className="evidence-pane">
          <EvidencePanel
            runState={runState}
            results={results}
            lookup={lookup}
            selectedEntity={selectedEntity}
            setSelectedEntity={setSelectedEntity}
            setSelectedTab={setSelectedTab}
          />
        </aside>
      </section>

      <section className="diagnostics-panel">
        <Diagnostics title="Errors" items={results.diagnostics?.errors || runState?.errors || []} emptyText="暂无错误" />
        <Diagnostics title="Warnings" items={results.warnings?.warnings || runState?.warnings || []} emptyText="暂无警告" />
        <Diagnostics title="Revisions" items={results.revisions?.revisions || runState?.revisions || []} emptyText="暂无修订记录" />
      </section>
    </main>
  )
}

function ImportPanel({ sourceType, importFile, importPreview, importError, isImporting, onFileChange }) {
  const metadata = importPreview?.metadata || {}
  const sourceLabel = sourceType === 'json' ? 'JSON 导入' : 'CSV 导入'
  return (
    <section className="import-panel">
      <label className="field">
        <span>{sourceType === 'json' ? UI_LABELS.jsonFile : UI_LABELS.csvFile}</span>
        <input type="file" accept={sourceType === 'json' ? '.json,application/json' : '.csv,text/csv'} onChange={onFileChange} />
      </label>
      <div className="import-preview">
        <strong>{sourceLabel}</strong>
        <dl className="definition-grid compact-grid">
          <FragmentPair term="Filename" description={importFile?.name || metadata.filename || 'none'} />
          <FragmentPair term="Size" description={importFile ? formatBytes(importFile.size) : 'none'} />
          <FragmentPair term="Record Count" description={formatValue(metadata.record_count)} />
          <FragmentPair term="Valid Count" description={formatValue(metadata.valid_count)} />
          <FragmentPair term="Invalid Count" description={formatValue(metadata.invalid_count)} />
          <FragmentPair term="Territory" description={metadata.territory || UI_LABELS.unknownNotProvided} />
          <FragmentPair term="App ID" description={metadata.app_id || 'none'} />
        </dl>
        {isImporting ? <div className="message">{UI_LABELS.importPreviewRunning}</div> : null}
        {importError ? (
          <div className="message error-message">
            <strong>{UI_LABELS.importError}</strong>
            <span>{tErrorType(importError.type)}: {importError.message}</span>
          </div>
        ) : null}
        {importPreview ? <ListBlock title="Warnings" items={importPreview.warnings} emphasized /> : null}
      </div>
    </section>
  )
}

function DemoModeNotice({ compact = false }) {
  return (
    <section className={compact ? 'demo-notice compact' : 'demo-notice'}>
      <strong>缓存演示数据</strong>
      <span>当前结果来自项目内置缓存，仅用于离线演示，不代表实时 App Store 数据。</span>
      <span>缓存演示不会调用 Apify 或 DeepSeek，也不会作为实时分析失败后的自动回退。</span>
    </section>
  )
}

function ModeBanner({ runState, results, runMode }) {
  const metadata = results.metadata?.data || {}
  const isDemo = Boolean(runState?.is_demo || metadata.is_demo || runMode === 'demo')
  if (isDemo) {
    return (
      <section className="mode-banner demo-banner">
        <div>
          <strong>缓存演示数据</strong>
          <span>当前结果来自项目内置缓存，仅用于离线演示，不代表实时 App Store 数据。</span>
        </div>
        <dl className="banner-facts">
          <FragmentPair term="Data Source" description={metadata.provider || 'apify'} />
          <FragmentPair term="Territory" description={metadata.territory || 'US'} />
          <FragmentPair term="App ID" description={metadata.app_id || runState?.app_id || '839285684'} />
        </dl>
      </section>
    )
  }
  return (
    <section className="mode-banner live-banner">
      <strong>实时分析</strong>
      <span>系统将使用当前配置的数据源和模型实时执行分析；失败时不会自动回退到缓存演示数据。</span>
    </section>
  )
}

function DashboardTab({ tab, runState, results, lookup, filters, setFilters, setSelectedEntity, setSelectedTab }) {
  if (!runState) {
    return <EmptyState text="开始一次分析运行后，将在这里显示结果。" />
  }
  if (tab === 'overview') return <Overview results={results} runState={runState} />
  if (tab === 'reviews') {
    return <Reviews results={results} filters={filters} setFilters={setFilters} setSelectedEntity={setSelectedEntity} />
  }
  if (tab === 'processing') return <Processing results={results} />
  if (tab === 'topics') return <Topics results={results} lookup={lookup} setSelectedEntity={setSelectedEntity} />
  if (tab === 'issues') return <Issues results={results} setSelectedEntity={setSelectedEntity} />
  if (tab === 'findings') return <Findings results={results} lookup={lookup} setSelectedEntity={setSelectedEntity} />
  if (tab === 'requirements') return <Requirements results={results} setSelectedEntity={setSelectedEntity} />
  if (tab === 'roadmap') return <Roadmap results={results} setSelectedEntity={setSelectedEntity} />
  if (tab === 'prd') return <Prds results={results} setSelectedEntity={setSelectedEntity} />
  if (tab === 'testCases') return <TestCases results={results} setSelectedEntity={setSelectedEntity} />
  if (tab === 'traceability') return <Traceability results={results} lookup={lookup} setSelectedEntity={setSelectedEntity} />
  if (tab === 'validation') return <Validation results={results} runState={runState} />
  if (tab === 'diagnostics') return <DiagnosticsTab results={results} runState={runState} />
  return <EmptyState text="未知结果分区。" />
}

function Overview({ results, runState }) {
  const stats = results.reviews?.statistics || {}
  const scope = results.reviews?.scope_report || {}
  const metadata = results.metadata?.data || {}
  const counts = results.traceability?.validation?.counts || {}
  const reviews = results.reviews?.reviews || []
  const requirements = results.requirements?.requirements || []
  const testCases = results.testCases?.test_cases || []
  const acceptanceCriteriaCount = requirements.reduce((total, requirement) => {
    return total + listOf(requirement.acceptance_criteria).length
  }, 0)
  const cards = [
    ['Reviews In Scope', scope.selected_count ?? metadata.reviews_in_scope ?? counts.reviews ?? reviews.length],
    ['Reviews Collected', metadata.reviews_collected ?? scope.input_count ?? results.reviews?.raw_reviews?.length ?? reviews.length],
    ['Excluded by Constraint', metadata.reviews_excluded_by_constraint ?? scope.excluded_count ?? 0],
    ['Processed Reviews', stats.retained ?? results.reviews?.processing_report?.retained_count ?? reviews.length],
    ['Topics', counts.topics ?? listOf(results.topics?.topics).length],
    ['Issues', counts.issues ?? listOf(results.issues?.issues).length],
    ['Findings', counts.findings ?? listOf(results.findings?.findings).length],
    ['Requirements', counts.requirements ?? requirements.length],
    ['Versions', counts.versions ?? listOf(results.roadmap?.versions).length],
    ['PRDs', counts.prds ?? listOf(results.prd?.prds).length],
    ['Acceptance Criteria', counts.acceptance_criteria ?? acceptanceCriteriaCount],
    ['Test Cases', counts.test_cases ?? testCases.length],
  ]
  return (
    <div className="tab-content">
      <section className="metric-grid">
        {cards.map(([label, value]) => (
          <Metric key={label} label={label} value={value ?? 0} />
        ))}
      </section>
      <section className="two-column">
        <Distribution title="Rating Distribution" data={stats.rating_distribution} sourceLabel="Deterministic Statistics" />
        <Distribution title="Language Distribution" data={stats.language_distribution} sourceLabel="Deterministic Statistics" />
      </section>
      <section className="section-block">
        <h3>{t('Run Metadata')}</h3>
        <TagRow labels={['Evidence', 'Deterministic', 'Model + Evidence', 'Uncertainty', 'Conflict']} />
        <dl className="definition-grid">
          <FragmentPair term="Analysis Goal" description={runState.analysis_goal} />
          <FragmentPair term="Analysis Focus" description={analysisFocusLabel(metadata.analysis_focus || runState.analysis_focus)} />
          <FragmentPair term="Analysis Constraint" description={constraintLabel(scope.constraint || metadata.analysis_constraints || runState.constraints)} />
          <FragmentPair term="Average Rating" description={formatValue(stats.average_rating)} />
          <FragmentPair
            term="Data Source"
            description={tSource(results.metadata?.data?.display_source || results.reviews?.dataset_metadata?.display_source || results.reviews?.dataset_metadata?.provider || runState.source_type || 'artifact snapshot')}
          />
          <FragmentPair term="App Context" description={results.metadata?.data?.app_context || runState.app_url} />
          <FragmentPair term="Review Territory" description={results.metadata?.data?.territory || results.reviews?.dataset_metadata?.territory || runState.storefront || 'US'} />
          <FragmentPair
            term="Scope Summary"
            description={`${formatValue(scope.selected_count ?? metadata.reviews_in_scope)} 条纳入分析；${formatValue(scope.excluded_count ?? metadata.reviews_excluded_by_constraint)} 条被分析范围排除`}
          />
        </dl>
      </section>
    </div>
  )
}

function Reviews({ results, filters, setFilters, setSelectedEntity }) {
  const reviews = results.reviews?.reviews || []
  const pageSize = 10
  const languages = unique(reviews.map((review) => review.language).filter(Boolean))
  const filtered = reviews.filter((review) => {
    const ratingOk = filters.rating === 'all' || String(review.rating) === filters.rating
    const languageOk = filters.language === 'all' || review.language === filters.language
    const haystack = [review.id, review.raw_title, review.raw_body, review.clean_title, review.clean_body]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    const searchOk = !filters.search || haystack.includes(filters.search.toLowerCase())
    return ratingOk && languageOk && searchOk
  })
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const page = Math.min(filters.page, pageCount)
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize)

  return (
    <div className="tab-content">
      <div className="filter-row">
        <label>
          {t('Rating')}
          <select value={filters.rating} onChange={(event) => setFilters({ ...filters, rating: event.target.value, page: 1 })}>
            <option value="all">全部</option>
            {[1, 2, 3, 4, 5].map((rating) => (
              <option value={String(rating)} key={rating}>
                {rating}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('Language')}
          <select
            value={filters.language}
            onChange={(event) => setFilters({ ...filters, language: event.target.value, page: 1 })}
          >
            <option value="all">全部</option>
            {languages.map((language) => (
              <option value={language} key={language}>
                {language}
              </option>
            ))}
          </select>
        </label>
        <label className="search-field">
          {t('Search')}
          <input
            value={filters.search}
            onChange={(event) => setFilters({ ...filters, search: event.target.value, page: 1 })}
            placeholder="评论正文或评论 ID"
          />
        </label>
      </div>
      <div className="data-note">
        评论地区 = {results.metadata?.data?.territory || results.reviews?.dataset_metadata?.territory || UI_LABELS.unknownNotProvided} ·
        数据来源 = {tSource(results.metadata?.data?.display_source || results.reviews?.dataset_metadata?.display_source || results.reviews?.source || 'artifact API')}
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t('Review ID')}</th>
              <th>{t('Rating')}</th>
              <th>{t('Title')}</th>
              <th>{t('Body')}</th>
              <th>{t('Date')}</th>
              <th>{t('Language')}</th>
              <th>{t('Territory')}</th>
              <th>{t('App ID')}</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((review) => (
              <tr key={review.id} onClick={() => setSelectedEntity({ type: 'review', id: review.id })}>
                <td className="mono">{review.id}</td>
                <td>{review.rating}</td>
                <td>{review.raw_title || review.title || review.clean_title || '无标题'}</td>
                <td>{truncate(review.raw_body || review.body || review.clean_body, 130)}</td>
                <td>{review.created_at}</td>
                <td>{review.language || '未知'}</td>
                <td>{review.territory || 'US'}</td>
                <td>{review.app_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!visible.length ? <EmptyState text="没有符合当前筛选条件的评论。" /> : null}
      <Pagination page={page} pageCount={pageCount} onPage={(next) => setFilters({ ...filters, page: next })} />
    </div>
  )
}

function Processing({ results }) {
  const report = results.reviews?.processing_report || {}
  const stats = results.reviews?.statistics || {}
  const scope = results.reviews?.scope_report || {}
  const scopeValidation = results.reviews?.scope_validation || {}
  return (
    <div className="tab-content">
      <section className="metric-grid">
        <Metric label="Full Input Count" value={scope.input_count ?? results.reviews?.processing_report_all?.input_count ?? report.input_count ?? stats.total ?? 0} />
        <Metric label="Selected Count" value={scope.selected_count ?? report.input_count ?? stats.total ?? 0} />
        <Metric label="Excluded Count" value={scope.excluded_count ?? 0} />
        <Metric label="Valid Count" value={report.valid_count ?? stats.valid ?? 0} />
        <Metric label="Retained Count" value={report.retained_count ?? stats.retained ?? 0} />
        <Metric label="Duplicates" value={report.exact_duplicate_count ?? stats.exact_duplicates ?? 0} />
        <Metric label="Near Duplicate Candidates" value={report.near_duplicate_count ?? stats.near_duplicate_candidates ?? 0} />
      </section>
      <section className="two-column">
        <Distribution title="Rating Distribution" data={stats.rating_distribution} sourceLabel="Deterministic Statistics" />
        <Distribution title="Language Distribution" data={stats.language_distribution} sourceLabel="Deterministic Statistics" />
      </section>
      <KeyValuePanel title="Analysis Scope" data={{ constraint: constraintLabel(scope.constraint), validation: scopeValidation.status, selected_count: scope.selected_count, excluded_count: scope.excluded_count }} />
      <KeyValuePanel title="Processing Report" data={report} />
    </div>
  )
}

function Topics({ results, lookup, setSelectedEntity }) {
  const topics = results.topics?.topics || []
  return (
    <div className="card-list">
      {topics.map((topic) => (
        <article className="result-card" key={topic.topic_id}>
          <header>
            <button type="button" className="link-button" onClick={() => setSelectedEntity({ type: 'topic', id: topic.topic_id })}>
              {topic.topic_id}
            </button>
            <Confidence value={topic.confidence} />
          </header>
          <h3>{topic.name}</h3>
          <p>{topic.description}</p>
          <MetaLine items={[['Reviews', listOf(topic.review_ids).length], ['Uncertainty', topic.uncertainty]]} />
          <IdLinks ids={topic.review_ids} type="review" setSelectedEntity={setSelectedEntity} lookup={lookup.reviews} />
        </article>
      ))}
      {!topics.length ? <EmptyState text="当前运行尚无主题结果。" /> : null}
    </div>
  )
}

function Issues({ results, setSelectedEntity }) {
  const issues = results.issues?.issues || []
  return (
    <div className="card-list">
      {issues.map((issue) => (
        <article className="result-card" key={issue.issue_id}>
          <header>
            <button type="button" className="link-button" onClick={() => setSelectedEntity({ type: 'issue', id: issue.issue_id })}>
              {issue.issue_id}
            </button>
            <span className={`type-badge ${issue.issue_type || 'unknown'}`}>{formatValue(issue.issue_type || 'unknown')}</span>
            <Confidence value={issue.confidence} />
          </header>
          <h3>{issue.name}</h3>
          <p>{issue.description}</p>
          <MetaLine
            items={[
              ['Topics', listOf(issue.topic_ids).length],
              ['Reviews', listOf(issue.review_ids).length],
              ['Uncertainty', issue.uncertainty],
            ]}
          />
          {issue.issue_type === 'positive_feedback' ? (
            <div className="warning-note">该正向反馈不会作为普通产品问题进入 Finding，这是预期行为。</div>
          ) : null}
          <p className="rationale">{issue.merge_rationale}</p>
        </article>
      ))}
      {!issues.length ? <EmptyState text="当前运行尚无问题归并结果。" /> : null}
    </div>
  )
}

function Findings({ results, lookup, setSelectedEntity }) {
  const findings = results.findings?.findings || []
  const evidence = byId(results.findings?.evidence_reports || [], 'finding_id')
  return (
    <div className="card-list">
      {findings.map((finding) => {
        const report = evidence[finding.finding_id] || {}
        return (
          <article className="result-card" key={finding.finding_id}>
            <header>
              <button
                type="button"
                className="link-button"
                onClick={() => setSelectedEntity({ type: 'finding', id: finding.finding_id })}
              >
                {finding.finding_id}
              </button>
              <Confidence value={finding.confidence} />
              <span className={`type-badge ${finding.finding_type || 'product_problem'}`}>{formatValue(finding.finding_type || 'product_problem')}</span>
            </header>
            <h3>{finding.title || finding.name}</h3>
            <p>{finding.statement || finding.description}</p>
            <TagRow labels={['Model + Evidence', 'Evidence', 'Uncertainty', 'Conflict']} />
            <MetaLine
              items={[
                ['Support Count [Deterministic]', finding.support_count],
                ['Evidence Strength', finding.evidence_strength || report.evidence_strength],
                ['Conflicts', finding.conflicting_count ?? report.conflicting_count ?? 0],
                ['Uncertainty', finding.uncertainty],
              ]}
            />
            <ListBlock title="Supporting Review IDs [Evidence]" items={finding.review_ids} />
            <ListBlock title="Evidence Limitations [Uncertainty]" items={report.evidence_limitations} emphasized />
            {listOf(finding.conflicting_review_ids).length ? (
              <ListBlock title="Conflicting Evidence [Conflict]" items={finding.conflicting_review_ids} emphasized />
            ) : (
              <div className="conflict-note">[冲突证据] 暂无冲突证据记录</div>
            )}
            <button
              type="button"
              className="secondary compact"
              onClick={() => setSelectedEntity({ type: 'finding', id: finding.finding_id })}
            >
              {t('View Evidence')}
            </button>
            <IdLinks ids={finding.review_ids} type="review" setSelectedEntity={setSelectedEntity} />
          </article>
        )
      })}
      {!findings.length ? <EmptyState text="当前运行尚无分析发现。" /> : null}
    </div>
  )
}

function Requirements({ results, setSelectedEntity }) {
  const requirements = results.requirements?.requirements || []
  return (
    <div className="card-list">
      {requirements.map((requirement) => (
        <article className="result-card" key={requirement.requirement_id}>
          <header>
            <button
              type="button"
              className="link-button"
              onClick={() => setSelectedEntity({ type: 'requirement', id: requirement.requirement_id })}
            >
              {requirement.requirement_id}
            </button>
            <span className="priority-badge">{formatValue(requirement.priority || requirement.final_priority || 'priority unknown')}</span>
            <span className={`type-badge ${requirement.requirement_type || 'problem'}`}>{formatValue(requirement.requirement_type || 'problem')}</span>
          </header>
          <h3>{requirement.title || requirement.name}</h3>
          <p>{requirement.description}</p>
          <MetaLine
            items={[
              ['Acceptance Criteria', listOf(requirement.acceptance_criteria).length],
              ['Risk', requirement.risk || requirement.risks],
              ['Uncertainty', requirement.uncertainty],
            ]}
          />
          <ListBlock title="Success Metrics" items={requirement.success_metrics} />
          <ListBlock title="Acceptance Criteria" items={formatAcceptanceCriteria(requirement.acceptance_criteria)} />
        </article>
      ))}
      {!requirements.length ? <EmptyState text="当前运行尚无产品需求。" /> : null}
    </div>
  )
}

function Roadmap({ results, setSelectedEntity }) {
  const versions = results.roadmap?.versions || []
  const roadmapItems = results.roadmap?.roadmap_items || []
  return (
    <div className="roadmap-list">
      {versions.map((version) => (
        <article className="release-card" key={version.version_id}>
          <div className="release-marker">{version.version_id}</div>
          <div>
            <h3>{version.name}</h3>
            <p>{version.goal}</p>
            <MetaLine
              items={[
                ['Requirements', listOf(version.requirement_ids).length],
                ['Risks', formatValue(version.risks)],
                ['Success Metrics', formatValue(version.success_metrics)],
              ]}
            />
            <IdLinks ids={version.requirement_ids} type="requirement" setSelectedEntity={setSelectedEntity} />
            <ListBlock
              title="Roadmap Items"
              items={roadmapItems
                .filter((item) => item.version_id === version.version_id)
                .map((item) => `${item.requirement_id} · ${formatValue(item.priority || 'priority unknown')} · ${item.rationale || ''}`)}
            />
          </div>
        </article>
      ))}
      {!versions.length ? <EmptyState text="当前运行尚无版本规划。" /> : null}
    </div>
  )
}

function Prds({ results, setSelectedEntity }) {
  const prds = results.prd?.prds || []
  return (
    <div className="card-list">
      {prds.map((prd) => (
        <article className="result-card expanded" key={prd.prd_id}>
          <header>
            <button type="button" className="link-button" onClick={() => setSelectedEntity({ type: 'prd', id: prd.prd_id })}>
              {prd.prd_id}
            </button>
            <span className="type-badge">{prd.version_id}</span>
          </header>
          <h3>{prd.title}</h3>
          <p>{prd.overview || prd.problem_statement || prd.goal}</p>
          <ListBlock title="Goals" items={prd.goals} />
          <ListBlock title="Non-Goals" items={prd.non_goals} />
          <ListBlock title="Requirements" items={prd.requirement_ids} />
          <ListBlock title="Risks" items={prd.risks} />
          <SuccessMetricsBlock items={prd.success_metrics} />
          <OpenQuestionBlock items={prd.open_questions} />
        </article>
      ))}
      {!prds.length ? <EmptyState text="当前运行尚无 PRD。" /> : null}
    </div>
  )
}

function TestCases({ results, setSelectedEntity }) {
  const cases = results.testCases?.test_cases || []
  return (
    <div className="tab-content">
      <KeyValuePanel title="Coverage" data={results.testCases?.coverage || {}} />
      <div className="card-list">
        {cases.map((testCase) => (
          <article className="result-card" key={testCase.test_case_id}>
            <header>
              <button
                type="button"
                className="link-button"
                onClick={() => setSelectedEntity({ type: 'testCase', id: testCase.test_case_id })}
              >
                {testCase.test_case_id}
              </button>
              <span className="priority-badge">{formatValue(testCase.priority || 'priority unknown')}</span>
            </header>
            <h3>{testCase.title}</h3>
            <MetaLine
              items={[
                ['Requirement', testCase.requirement_id],
                ['Type', testCase.test_type],
                ['ACs', listOf(testCase.acceptance_criteria_ids).length],
              ]}
            />
            <ListBlock title="Preconditions" items={testCase.preconditions} />
            <ListBlock title="Steps" items={testCase.steps} />
            <p className="expected-result">{testCase.expected_result}</p>
            <SourceReviews
              reviewIds={testCase.source_review_ids}
              onSelect={(id) => setSelectedEntity({ type: 'review', id })}
            />
          </article>
        ))}
      </div>
      {!cases.length ? <EmptyState text="当前运行尚无测试用例。" /> : null}
    </div>
  )
}

function Traceability({ results, lookup, setSelectedEntity }) {
  const graph = results.traceability?.graph || {}
  const candidates = [
    ...Object.keys(lookup.reviews).map((id) => ['Review', 'review', id]),
    ...Object.keys(lookup.topics).map((id) => ['Topic', 'topic', id]),
    ...Object.keys(lookup.issues).map((id) => ['Issue', 'issue', id]),
    ...Object.keys(lookup.findings).map((id) => ['Finding', 'finding', id]),
    ...Object.keys(lookup.requirements).map((id) => ['Requirement', 'requirement', id]),
    ...Object.keys(lookup.testCases).map((id) => ['Test Case', 'testCase', id]),
  ]
  return (
    <div className="tab-content">
      <div className="trace-grid">
        <section className="section-block">
          <h3>{t('Entity Selector')}</h3>
          <div className="id-cloud">
            {candidates.slice(0, 120).map(([label, type, id]) => (
              <button type="button" className="id-chip" key={`${type}-${id}`} onClick={() => setSelectedEntity({ type, id })}>
                {t(label)}: {id}
              </button>
            ))}
          </div>
        </section>
        <section className="section-block">
          <h3>{t('Graph Health')}</h3>
          <StatusPill value={results.traceability?.validation?.runtime_validation_status || 'pending'} label="Runtime" />
          <KeyValuePanel title="Validation Counts" data={results.traceability?.validation?.counts || {}} />
        </section>
      </div>
      <TraceMaps graph={graph} />
    </div>
  )
}

function SourceReviews({ reviewIds, onSelect }) {
  const ids = listOf(reviewIds)
  return (
    <section className="source-reviews-block">
      <h4>{t('Source Reviews')}</h4>
      {ids.length ? (
        <div className="id-cloud compact-cloud">
          {ids.map((id) => (
            <button type="button" className="id-chip" key={id} onClick={() => onSelect(id)}>
              {id}
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">暂无来源评论关联。</p>
      )}
    </section>
  )
}

function Validation({ results, runState }) {
  const validation = results.validation?.validation || {}
  const metadata = results.validation?.metadata || {}
  const registry = metadata.model_registry || []
  const runtimeStatus = validation.runtime_validation_status || runState.runtime_validation_status
  const submissionStatus = validation.submission_validation_status || runState.submission_validation_status
  return (
    <div className="tab-content">
      <section className="validation-banner">
        <div>
          <strong>{t('Backend Analysis')}</strong>
          <StatusPill value={runtimeStatus} label="Runtime Pipeline" />
          <p>{runtimePipelineMessage(runtimeStatus)}</p>
        </div>
        <div>
          <strong>{t('Final Submission')}</strong>
          <StatusPill value={submissionStatus} label="Submission Validation" />
          <p>待完成检查会继续显示，但不会被视为运行时失败。</p>
        </div>
      </section>
      <section className="metric-grid">
        <Metric label="Runtime Validation" value={validation.runtime_validation_status || runState.runtime_validation_status} />
        <Metric label="Submission Validation" value={validation.submission_validation_status || runState.submission_validation_status} />
        <Metric label="Forward Traceability" value={validation.forward_traceability || 'pending'} />
        <Metric label="Backward Traceability" value={validation.backward_traceability || 'pending'} />
        <Metric label="Evidence Traceability" value={validation.evidence_traceability || 'pending'} />
        <Metric label="Test Case -> Review Link" value={validation.explicit_test_case_review_link || 'pending'} />
        <Metric label="Artifact Consistency" value={validation.artifact_consistency || 'pending'} />
        <Metric label="AI / Deterministic Boundary" value={validation.ai_deterministic_boundary || 'pending'} />
        <Metric label="Statistics / Model Separation" value={validation.statistics_model_separation || 'pending'} />
      </section>
      <ListBlock title="Pending Checks" items={pendingChecks(validation, results.validation)} emphasized />
      <section className="section-block">
        <h3>{t('Model / Data Metadata')}</h3>
        {registry.length ? (
          registry.map((item, index) => (
            <dl className="definition-grid compact-grid" key={`${item.provider}-${index}`}>
              <FragmentPair term="Provider" description={item.provider || 'DeepSeek'} />
              <FragmentPair term="Model" description={item.model || 'unknown'} />
              <FragmentPair term="Thinking" description={item.thinking || 'disabled'} />
              <FragmentPair term="Max Tokens" description={formatValue(item.max_tokens)} />
              <FragmentPair term="Temperature" description={formatValue(item.temperature)} />
              <FragmentPair term="Stream" description={formatValue(item.stream)} />
              <FragmentPair term="Timeout" description={formatValue(item.timeout_seconds)} />
            </dl>
          ))
        ) : (
          <EmptyState text="当前暂无模型元信息。" />
        )}
      </section>
      <KeyValuePanel title="Validation Report" data={validation} />
    </div>
  )
}

function DiagnosticsTab({ results, runState }) {
  const diagnostics = results.diagnostics || {}
  const warnings = results.warnings || {}
  const revisions = results.revisions || {}
  const metadata = results.metadata || {}
  return (
    <div className="tab-content">
      <FailurePropagationNotice diagnostics={diagnostics} runState={runState} inPanel />
      <section className="three-column">
        <Diagnostics title="Errors" items={diagnostics.errors || runState.errors || []} emptyText="暂无错误" />
        <Diagnostics title="Warnings" items={warnings.warnings || runState.warnings || []} emptyText="暂无警告" />
        <Diagnostics title="Revisions" items={revisions.revisions || runState.revisions || []} emptyText="暂无修订记录" />
      </section>
      <section className="section-block">
        <h3>{t('Data Metadata')}</h3>
        <TagRow labels={['Evidence', metadata.data?.artifact_source || 'Run Artifact Snapshot', metadata.data?.cached_label || metadata.data?.display_source || 'Run Data']} />
        <dl className="definition-grid">
          <FragmentPair term="Data Source" description={tSource(metadata.data?.display_source || metadata.data?.provider || 'unknown')} />
          <FragmentPair term="Review Source" description={tSource(metadata.data?.review_source || metadata.data?.display_source || 'unknown')} />
          <FragmentPair term="App Context" description={metadata.data?.app_context || runState.app_url || 'unknown'} />
          <FragmentPair term="Analysis Focus" description={analysisFocusLabel(metadata.data?.analysis_focus || runState.analysis_focus)} />
          <FragmentPair term="Filename" description={metadata.data?.filename || 'none'} />
          <FragmentPair term="Territory" description={metadata.data?.territory || UI_LABELS.unknownNotProvided} />
          <FragmentPair term="App ID" description={metadata.data?.app_id || runState.app_id || 'unknown'} />
          <FragmentPair term="Collection Time" description={metadata.data?.collection_time || 'unknown'} />
          <FragmentPair term="Requested Limit" description={formatValue(metadata.data?.requested_limit)} />
          <FragmentPair term="Record Count" description={formatValue(metadata.data?.record_count)} />
          <FragmentPair term="Valid Count" description={formatValue(metadata.data?.valid_count)} />
          <FragmentPair term="Invalid Count" description={formatValue(metadata.data?.invalid_count)} />
          <FragmentPair term="Actual Count" description={formatValue(metadata.data?.actual_count)} />
        </dl>
        <ListBlock title="Limitations [Uncertainty]" items={metadata.data?.limitations} emphasized />
      </section>
      <section className="section-block">
        <h3>{t('Model Metadata')}</h3>
        <TagRow labels={['Model-generated', 'No API Key Displayed']} />
        {(metadata.model?.model_registry || []).map((item, index) => (
          <dl className="definition-grid compact-grid" key={`${item.task || item.provider}-${index}`}>
            <FragmentPair term="Task" description={item.task || 'unknown'} />
            <FragmentPair term="Provider" description={item.provider || 'DeepSeek'} />
            <FragmentPair term="Model" description={item.model || 'unknown'} />
            <FragmentPair term="Thinking" description={item.thinking || 'disabled'} />
            <FragmentPair term="Max Tokens" description={formatValue(item.max_tokens)} />
            <FragmentPair term="Temperature" description={formatValue(item.temperature)} />
            <FragmentPair term="Timeout" description={formatValue(item.timeout_seconds)} />
            <FragmentPair term="Stream" description={formatValue(item.stream)} />
          </dl>
        ))}
      </section>
    </div>
  )
}

function FailurePropagationNotice({ diagnostics, runState, inPanel = false }) {
  const propagation = diagnostics?.failure_propagation
  if (!propagation?.has_failure) return null
  return (
    <section className={`failure-propagation ${inPanel ? 'in-panel' : ''}`}>
      <strong>{t('Failure Propagation')}</strong>
      <p>{propagation.message || `由于 ${propagation.failed_stage} 阶段失败，后续阶段未执行。`}</p>
      <MetaLine
        items={[
          ['Failed Stage', tStage(propagation.failed_stage)],
          ['Skipped Stages', listOf(propagation.skipped_stages).join(', ')],
          ['Run Status', runState?.status],
        ]}
      />
    </section>
  )
}

function EvidencePanel({ runState, results, lookup, selectedEntity, setSelectedEntity, setSelectedTab }) {
  const entity = selectedEntity ? lookupEntity(lookup, selectedEntity) : null
  const chain = selectedEntity ? buildChain(selectedEntity, results.traceability?.graph || {}) : []
  const reviewIds = evidenceReviewIds(selectedEntity, entity, results.traceability?.graph || {})
  const reviews = reviewIds.map((id) => lookup.reviews[id]).filter(Boolean)
  const conflictIds = selectedEntity?.type === 'finding' ? listOf(entity?.conflicting_review_ids) : []
  const conflictReviews = conflictIds.map((id) => lookup.reviews[id]).filter(Boolean)
  return (
    <div>
      <h2>证据 / 元信息</h2>
      {!selectedEntity ? (
        <EmptyState text="请选择一行、卡片或 ID 查看证据。" />
      ) : (
        <>
          <div className="entity-heading">
            <span className="type-badge">{t(selectedEntity.type)}</span>
            <strong className="mono">{selectedEntity.id}</strong>
          </div>
          {entity ? <EntitySummary entity={entity} /> : <div className="warning-note">当前运行结果中未找到该实体。</div>}
          <TagRow labels={['Evidence', 'Traceability', 'Uncertainty', 'Conflict']} />
          <section className="section-block">
            <h3>{t('Traceability Chain')}</h3>
            <div className="quick-actions">
              <span>查看来源证据</span>
              <span>查看上游分析发现</span>
              <span>查看相关产品需求</span>
              <span>查看相关测试用例</span>
            </div>
            {chain.length ? (
              <ol className="chain-list">
                {chain.map((item) => (
                  <li key={`${item.type}-${item.id}`}>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        setSelectedEntity(item)
                        setSelectedTab(tabForType(item.type))
                      }}
                    >
                      {t(item.label)}: {item.id}
                    </button>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState text="该实体暂无可追溯链。" />
            )}
          </section>
          <section className="section-block">
            <h3>{t('Evidence Reviews [Evidence]')}</h3>
            {reviews.map((review) => (
              <article className="review-evidence" key={review.id}>
                <div>
                  <span className="mono">{review.id}</span>
                  <strong>{review.rating} 星</strong>
                </div>
                <h4>{review.raw_title || review.title || review.clean_title || '无标题'}</h4>
                <p>{review.raw_body || review.body || review.clean_body}</p>
              </article>
            ))}
            {!reviews.length ? <EmptyState text="当前选择项没有直接评论证据。" /> : null}
          </section>
          <section className="section-block">
            <h3>{t('Conflicting Evidence [Conflict]')}</h3>
            {conflictReviews.map((review) => (
              <article className="review-evidence conflict" key={review.id}>
                <div>
                  <span className="mono">{review.id}</span>
                  <strong>{review.rating} 星</strong>
                </div>
                <h4>{review.raw_title || review.title || review.clean_title || '无标题'}</h4>
                <p>{review.raw_body || review.body || review.clean_body}</p>
              </article>
            ))}
            {!conflictReviews.length ? <div className="conflict-note">暂无冲突证据记录</div> : null}
          </section>
          <KeyValuePanel title="Run" data={{ run_id: runState?.run_id, status: runState?.status, source: results.reviews?.source }} />
        </>
      )}
    </div>
  )
}

function StageList({ stages, selectedStageId, onSelect }) {
  if (!stages.length) {
    return <EmptyState text="创建运行后会初始化 11 个工作流阶段。" />
  }
  return (
    <ol className="stage-list">
      {stages.map((stage) => {
        const meta = statusMeta[stage.status] || statusMeta.pending
        return (
          <li key={stage.stage}>
            <button
              type="button"
              className={`stage-row ${stage.status} ${selectedStageId === stage.stage ? 'selected' : ''}`}
              onClick={() => onSelect(stage.stage)}
            >
              <span className="stage-symbol">{meta.symbol}</span>
              <span className="stage-name">
                <strong>{STAGE_LABELS[stage.stage] || stage.label_zh || tStage(stage.stage)}</strong>
                <small>{stage.stage}</small>
              </span>
              <span className="stage-status">{meta.label}</span>
            </button>
          </li>
        )
      })}
    </ol>
  )
}

function StageDetail({ stage, revisions }) {
  if (!stage) return null
  const stageRevisions = listOf(revisions).filter((revision) => revision.stage === stage.stage)
  return (
    <section className="stage-detail">
      <h3>{t('Stage Detail')}</h3>
      <dl className="definition-grid compact-grid">
        <FragmentPair term="Status" description={stage.status} />
        <FragmentPair term="Started" description={stage.started_at || 'pending'} />
        <FragmentPair term="Completed" description={stage.completed_at || 'pending'} />
        <FragmentPair term="Elapsed" description={stage.elapsed_seconds !== null && stage.elapsed_seconds !== undefined ? `${stage.elapsed_seconds}s` : 'pending'} />
        <FragmentPair term="Message" description={stage.message || 'none'} />
      </dl>
      <KeyValuePanel title="Summary" data={stage.summary || {}} />
      <ListBlock title="Artifacts" items={stage.artifacts} />
      <ListBlock title="Warnings" items={stage.warnings} emphasized />
      <ListBlock title="Errors" items={(stage.errors || []).map((error) => `${tErrorType(error.type)}: ${error.message}`)} emphasized />
      <ListBlock
        title="Revisions"
        items={stageRevisions.map((revision) => `${revision.revision_id}: ${revision.status} · ${revision.reason}`)}
        emphasized
      />
    </section>
  )
}

function Diagnostics({ title, items, emptyText }) {
  return (
    <div className="diagnostic">
      <h2>{t(title)}</h2>
      {items.length ? (
        <ul className="diagnostic-list">
          {items.map((item, index) => (
            <li className="diagnostic-card" key={`${title}-${index}`}>
              <div className="diagnostic-head">
                <span className="type-badge">{tErrorType(item.category || title.replace(/s$/, ''))}</span>
                <strong className="mono">{item.stage || item.revision_id || 'run'}</strong>
              </div>
              <dl className="definition-grid compact-grid">
                <FragmentPair term="Type" description={tErrorType(item.type || item.status || 'status')} />
                <FragmentPair term="Message" description={item.message || item.reason || 'none'} />
                <FragmentPair term="Recoverable" description={formatValue(item.recoverable)} />
                <FragmentPair term="Timestamp" description={item.timestamp || 'unknown'} />
              </dl>
            </li>
          ))}
        </ul>
      ) : (
        <p>{emptyText}</p>
      )}
    </div>
  )
}

function Metric({ label, value, mono = false, valueFormatter = formatValue }) {
  return (
    <div className="metric">
      <span>{t(label)}</span>
      <strong className={mono ? 'mono' : ''}>{valueFormatter(value)}</strong>
    </div>
  )
}

function StatusPill({ value, label }) {
  const normalized = String(value || 'pending').toLowerCase()
  return (
    <span className={`status-pill ${normalized}`}>
      {t(label)}: {tStatus(value || 'pending')}
    </span>
  )
}

function Distribution({ title, data, sourceLabel }) {
  const entries = Object.entries(data || {})
  return (
    <section className="section-block">
      <h3>{t(title)}</h3>
      {sourceLabel ? <TagRow labels={[sourceLabel]} /> : null}
      {entries.length ? (
        <div className="distribution">
          {entries.map(([key, value]) => (
            <div key={key}>
              <span>{key}</span>
              <strong>{formatValue(value)}</strong>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState text="当前暂无分布数据。" />
      )}
    </section>
  )
}

function KeyValuePanel({ title, data }) {
  const entries = Object.entries(data || {}).filter(([, value]) => value !== undefined && value !== null)
  if (!entries.length) return null
  return (
    <section className="section-block">
      <h3>{t(title)}</h3>
      <dl className="definition-grid">
        {entries.slice(0, 30).map(([key, value]) => (
          <FragmentPair key={key} term={key} description={formatValue(value)} />
        ))}
      </dl>
    </section>
  )
}

function FragmentPair({ term, description }) {
  return (
    <>
      <dt>{t(term)}</dt>
      <dd>{formatValue(description)}</dd>
    </>
  )
}

function ListBlock({ title, items, emphasized = false }) {
  const values = listOf(items).map(formatValue).filter(Boolean)
  if (!values.length) return null
  return (
    <section className={`list-block ${emphasized ? 'emphasized' : ''}`}>
      <h4>{t(title)}</h4>
      <ul>
        {values.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  )
}

function OpenQuestionBlock({ items }) {
  const values = listOf(items)
  if (!values.length) return null
  return (
    <section className="open-question-block">
      <h4>{t('Open Questions')}</h4>
      <div className="status-line">{t('Status')}: {t('Open Product Decision')}</div>
      <ul>
        {values.map((item, index) => (
          <li key={`open-question-${index}`}>{formatValue(item)}</li>
        ))}
      </ul>
    </section>
  )
}

function SuccessMetricsBlock({ items }) {
  const values = listOf(items)
  if (values.length) {
    return <ListBlock title="Success Metrics" items={values} />
  }
  return (
    <section className="open-question-block">
      <h4>{t('Success Metrics')}</h4>
      <div className="status-line">当前没有已验证的成功指标。</div>
      <p>需要产品决策：定义可衡量的成功指标。</p>
    </section>
  )
}

function TagRow({ labels }) {
  return (
    <div className="tag-row">
      {labels.map((label) => (
        <span className="semantic-tag" key={label}>
          [{t(label)}]
        </span>
      ))}
    </div>
  )
}

function MetaLine({ items }) {
  return (
    <div className="meta-line">
      {items
        .filter(([, value]) => value !== undefined && value !== null && value !== '')
        .map(([label, value]) => (
          <span key={label}>
            {t(label)}: <strong>{formatValue(value)}</strong>
          </span>
        ))}
    </div>
  )
}

function IdLinks({ ids, type, setSelectedEntity }) {
  const values = listOf(ids)
  if (!values.length) return null
  return (
    <div className="id-cloud">
      {values.map((id) => (
        <button type="button" className="id-chip" key={id} onClick={() => setSelectedEntity({ type, id })}>
          {id}
        </button>
      ))}
    </div>
  )
}

function Confidence({ value }) {
  if (value === undefined || value === null || value === '') return null
  return <span className="confidence">置信度 {Number(value).toFixed(2)}</span>
}

function EmptyState({ text }) {
  return <div className="empty-state">{text}</div>
}

function Pagination({ page, pageCount, onPage }) {
  return (
    <div className="pagination">
      <button type="button" className="secondary compact" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        上一页
      </button>
      <span>
        第 {page} / {pageCount} 页
      </span>
      <button type="button" className="secondary compact" disabled={page >= pageCount} onClick={() => onPage(page + 1)}>
        下一页
      </button>
    </div>
  )
}

function TraceMaps({ graph }) {
  const maps = [
    ['Topic → Review', graph.topic_to_reviews],
    ['Issue → Topic', graph.issue_to_topics],
    ['Finding → Issue', graph.finding_to_issues],
    ['Requirement → Finding', graph.requirement_to_findings],
    ['Version → Requirement', graph.version_to_requirements],
    ['PRD → Requirement', graph.prd_to_requirements],
    ['Test Case → Requirement', graph.test_case_to_requirement],
  ]
  return (
    <div className="trace-map-list">
      {maps.map(([title, mapping]) => (
        <section className="section-block" key={title}>
          <h3>{t(title)}</h3>
          {Object.entries(mapping || {}).slice(0, 20).map(([parent, children]) => (
            <div className="trace-row" key={parent}>
              <span className="mono">{parent}</span>
              <strong>{formatValue(children)}</strong>
            </div>
          ))}
        </section>
      ))}
    </div>
  )
}

function EntitySummary({ entity }) {
  const keys = [
    'name',
    'title',
    'description',
    'statement',
    'rating',
    'language',
    'territory',
    'confidence',
    'uncertainty',
    'priority',
    'version_id',
    'requirement_id',
  ]
  const data = Object.fromEntries(keys.filter((key) => entity[key] !== undefined).map((key) => [key, entity[key]]))
  return <KeyValuePanel title="Selected Entity" data={data} />
}

function buildLookup(results) {
  return {
    reviews: byId(results.reviews?.reviews || [], 'id'),
    topics: byId(results.topics?.topics || [], 'topic_id'),
    issues: byId(results.issues?.issues || [], 'issue_id'),
    findings: byId(results.findings?.findings || [], 'finding_id'),
    requirements: byId(results.requirements?.requirements || [], 'requirement_id'),
    versions: byId(results.roadmap?.versions || [], 'version_id'),
    prds: byId(results.prd?.prds || [], 'prd_id'),
    testCases: byId(results.testCases?.test_cases || [], 'test_case_id'),
  }
}

function lookupEntity(lookup, selectedEntity) {
  const key = selectedEntity.type === 'testCase' ? 'testCases' : `${selectedEntity.type}s`
  return lookup[key]?.[selectedEntity.id]
}

function buildChain(selectedEntity, graph) {
  const add = (items, type, label) => listOf(items).map((id) => ({ type, label, id }))
  const id = selectedEntity.id
  if (selectedEntity.type === 'review') {
    const topicIds = graph.review_to_topics?.[id] || []
    const issueIds = topicIds.flatMap((topicId) => graph.topic_to_issues?.[topicId] || [])
    const findingIds = issueIds.flatMap((issueId) => graph.issue_to_findings?.[issueId] || [])
    const reqIds = findingIds.flatMap((findingId) => graph.finding_to_requirements?.[findingId] || [])
    const testCaseIds = graph.review_to_test_cases?.[id] || reqIds.flatMap((reqId) => graph.requirement_to_test_cases?.[reqId] || [])
    return [
      { type: 'review', label: 'Review', id },
      ...add(topicIds, 'topic', 'Topic'),
      ...add(issueIds, 'issue', 'Issue'),
      ...add(findingIds, 'finding', 'Finding'),
      ...add(reqIds, 'requirement', 'Requirement'),
      ...add(reqIds.flatMap((reqId) => graph.requirement_to_versions?.[reqId] || []), 'version', 'Version'),
      ...add(reqIds.flatMap((reqId) => graph.requirement_to_prds?.[reqId] || []), 'prd', 'PRD'),
      ...add(unique(testCaseIds), 'testCase', 'Test Case'),
    ]
  }
  if (selectedEntity.type === 'topic') {
    return [{ type: 'topic', label: 'Topic', id }, ...add(graph.topic_to_reviews?.[id], 'review', 'Review')]
  }
  if (selectedEntity.type === 'issue') {
    return [
      { type: 'issue', label: 'Issue', id },
      ...add(graph.issue_to_topics?.[id], 'topic', 'Topic'),
      ...add(graph.issue_to_reviews?.[id], 'review', 'Review'),
      ...add(graph.issue_to_findings?.[id], 'finding', 'Finding'),
    ]
  }
  if (selectedEntity.type === 'finding') {
    return [
      { type: 'finding', label: 'Finding', id },
      ...add(graph.finding_to_issues?.[id], 'issue', 'Issue'),
      ...add(graph.finding_to_reviews?.[id], 'review', 'Review'),
      ...add(graph.finding_to_requirements?.[id], 'requirement', 'Requirement'),
    ]
  }
  if (selectedEntity.type === 'requirement') {
    return [
      { type: 'requirement', label: 'Requirement', id },
      ...add(graph.requirement_to_findings?.[id], 'finding', 'Finding'),
      ...add(graph.requirement_to_versions?.[id], 'version', 'Version'),
      ...add(graph.requirement_to_prds?.[id], 'prd', 'PRD'),
      ...add(graph.requirement_to_test_cases?.[id], 'testCase', 'Test Case'),
    ]
  }
  if (selectedEntity.type === 'testCase') {
    const reqId = graph.test_case_to_requirement?.[id]
    return [
      { type: 'testCase', label: 'Test Case', id },
      ...(reqId ? [{ type: 'requirement', label: 'Requirement', id: reqId }] : []),
      ...add(graph.test_case_to_reviews?.[id], 'review', 'Source Review'),
    ]
  }
  return [{ ...selectedEntity, label: selectedEntity.type }]
}

function evidenceReviewIds(selectedEntity, entity, graph) {
  if (!selectedEntity) return []
  if (selectedEntity.type === 'review') return [selectedEntity.id]
  if (entity?.review_ids) return entity.review_ids
  if (selectedEntity.type === 'topic') return graph.topic_to_reviews?.[selectedEntity.id] || []
  if (selectedEntity.type === 'issue') return graph.issue_to_reviews?.[selectedEntity.id] || []
  if (selectedEntity.type === 'finding') return graph.finding_to_reviews?.[selectedEntity.id] || []
  if (selectedEntity.type === 'testCase') return graph.test_case_to_reviews?.[selectedEntity.id] || entity?.source_review_ids || []
  return []
}

function byId(items, key) {
  return Object.fromEntries(listOf(items).filter((item) => item?.[key]).map((item) => [item[key], item]))
}

function unique(items) {
  return [...new Set(items)]
}

function listOf(value) {
  if (Array.isArray(value)) return value
  if (value === undefined || value === null || value === '') return []
  return [value]
}

function constraintsForRating(value) {
  const option = ratingConstraintOptions.find((item) => item.value === value)
  return option?.constraints || {}
}

function constraintLabel(value) {
  const rating = value?.rating
  if (!rating) return '全部评分'
  const min = rating.min
  const max = rating.max
  if (min === undefined || max === undefined) return formatValue(value)
  return `${min}-${max} 星`
}

function analysisFocusLabel(value) {
  return tFocus(value)
}

function formatAcceptanceCriteria(items) {
  return listOf(items).map((item) => {
    if (typeof item === 'string') return item
    return `${item.acceptance_criteria_id || item.id || 'AC'}: ${item.statement || item.description || JSON.stringify(item)}`
  })
}

function pendingChecks(validation, validationPayload) {
  const blockers = listOf(validation?.submission_blockers || validationPayload?.submission_blockers)
  if (blockers.length) return blockers
  if (validation?.submission_validation_status === 'pending' || validationPayload?.submission_validation_status === 'pending') {
    return ['UI 就绪状态', '最终泛化真实输入测试', '最终交付文档']
  }
  return []
}

function runtimePipelineMessage(status) {
  if (status === 'pass' || status === 'completed') return '运行时流水线已完成'
  if (status === 'fail' || status === 'failed') return '运行时流水线失败'
  if (status === 'pending') return '运行时流水线待完成'
  return `运行时流水线：${formatValue(status)}`
}

function formatApiError(detail) {
  if (!detail) return '请求失败'
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object') {
    const type = tErrorType(detail.type || detail.error || 'unknown_error')
    const message = detail.message || detail.detail || JSON.stringify(detail)
    return `${type}: ${message}`
  }
  return String(detail)
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return '无'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function formatValue(value) {
  if (value === undefined || value === null || value === '') return '无'
  if (Array.isArray(value)) return value.map(formatValue).join(', ')
  if (typeof value === 'object') return Object.entries(value).map(([key, item]) => `${t(key)}=${formatValue(item)}`).join('; ')
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  return t(String(value))
}

function truncate(value, maxLength) {
  const text = formatValue(value)
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

function tabForType(type) {
  const mapping = {
    review: 'reviews',
    topic: 'topics',
    issue: 'issues',
    finding: 'findings',
    requirement: 'requirements',
    version: 'roadmap',
    prd: 'prd',
    testCase: 'testCases',
  }
  return mapping[type] || 'traceability'
}

export default App
