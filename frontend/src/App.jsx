import { useEffect, useMemo, useState } from 'react'

const DEFAULT_APP_URL = 'https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684'
const DEFAULT_GOAL = '分析低评分用户对订阅和价格的主要问题'

const statusMeta = {
  pending: { symbol: '○', label: 'Pending' },
  running: { symbol: '◉', label: 'Running' },
  completed: { symbol: '✓', label: 'Completed' },
  failed: { symbol: '✕', label: 'Failed' },
  skipped: { symbol: '⊘', label: 'Skipped' },
}

function App() {
  const [appUrl, setAppUrl] = useState(DEFAULT_APP_URL)
  const [analysisGoal, setAnalysisGoal] = useState(DEFAULT_GOAL)
  const [sourceType, setSourceType] = useState('app_store')
  const [runId, setRunId] = useState(null)
  const [runState, setRunState] = useState(null)
  const [requestError, setRequestError] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const progressValue = useMemo(() => {
    if (!runState) return 0
    return Math.max(0, Math.min(100, Number(runState.progress || 0)))
  }, [runState])

  useEffect(() => {
    if (!runId || !runState || !['queued', 'running'].includes(runState.status)) return undefined
    const timer = window.setInterval(() => {
      refreshRun(runId)
    }, 1500)
    return () => window.clearInterval(timer)
  }, [runId, runState?.status])

  async function startRun(event) {
    event.preventDefault()
    setRequestError(null)
    setIsSubmitting(true)
    try {
      const response = await fetch('/api/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          app_url: appUrl,
          analysis_goal: analysisGoal,
        }),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to create run')
      }
      setRunId(payload.run_id)
      await refreshRun(payload.run_id)
    } catch (error) {
      setRequestError(error.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  async function refreshRun(targetRunId = runId) {
    if (!targetRunId) return
    setRequestError(null)
    try {
      const response = await fetch(`/api/runs/${targetRunId}`)
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.detail || 'Unable to load run')
      }
      setRunState(payload)
    } catch (error) {
      setRequestError(error.message)
    }
  }

  return (
    <main className="app-shell">
      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>App Review Insights</h1>
            <p>Review analysis workflow shell</p>
          </div>
          <div className="api-badge">Backend API</div>
        </header>

        <div className="layout">
          <section className="panel control-panel">
            <form onSubmit={startRun}>
              <label className="field">
                <span>App Store URL</span>
                <input
                  value={appUrl}
                  onChange={(event) => setAppUrl(event.target.value)}
                  placeholder="https://apps.apple.com/us/app/example/id123"
                />
              </label>

              <label className="field">
                <span>Analysis Goal</span>
                <textarea
                  value={analysisGoal}
                  onChange={(event) => setAnalysisGoal(event.target.value)}
                  rows={4}
                  placeholder="分析用户评论中的主要产品问题、用户体验问题和改进机会。"
                />
              </label>

              <fieldset className="source-group">
                <legend>Data Source</legend>
                <label>
                  <input
                    type="radio"
                    name="source"
                    value="app_store"
                    checked={sourceType === 'app_store'}
                    onChange={(event) => setSourceType(event.target.value)}
                  />
                  App Store
                </label>
                <label>
                  <input
                    type="radio"
                    name="source"
                    value="json"
                    checked={sourceType === 'json'}
                    onChange={(event) => setSourceType(event.target.value)}
                    disabled
                  />
                  JSON
                </label>
                <label>
                  <input
                    type="radio"
                    name="source"
                    value="csv"
                    checked={sourceType === 'csv'}
                    onChange={(event) => setSourceType(event.target.value)}
                    disabled
                  />
                  CSV
                </label>
              </fieldset>

              <div className="actions">
                <button type="submit" disabled={isSubmitting || sourceType !== 'app_store'}>
                  {isSubmitting ? 'Creating Run...' : '开始分析'}
                </button>
                <button type="button" className="secondary" onClick={() => refreshRun()} disabled={!runId}>
                  Refresh
                </button>
              </div>
            </form>

            {requestError ? <div className="message error-message">{requestError}</div> : null}
          </section>

          <section className="panel run-panel">
            <div className="run-summary">
              <div>
                <span className="label">Run Status</span>
                <strong>{runState?.status || 'not_started'}</strong>
              </div>
              <div>
                <span className="label">Current Stage</span>
                <strong>{runState?.current_stage || 'none'}</strong>
              </div>
              <div>
                <span className="label">Run ID</span>
                <strong className="mono">{runState?.run_id || 'none'}</strong>
              </div>
            </div>

            <div className="progress-block">
              <div className="progress-label">
                <span>Overall Progress</span>
                <strong>{progressValue.toFixed(1)}%</strong>
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${progressValue}%` }} />
              </div>
            </div>

            <StageList stages={runState?.stages || []} />
          </section>
        </div>

        <section className="panel diagnostics-panel">
          <Diagnostics title="Errors" items={runState?.errors || []} emptyText="No errors" />
          <Diagnostics title="Warnings" items={runState?.warnings || []} emptyText="No warnings" />
          <Diagnostics title="Revisions" items={runState?.revisions || []} emptyText="No revisions" />
        </section>
      </section>
    </main>
  )
}

function StageList({ stages }) {
  if (!stages.length) {
    return <div className="empty-state">Create a run to initialize the 11 workflow stages.</div>
  }

  return (
    <ol className="stage-list">
      {stages.map((stage) => {
        const meta = statusMeta[stage.status] || statusMeta.pending
        return (
          <li className={`stage-row ${stage.status}`} key={stage.stage}>
            <span className="stage-symbol">{meta.symbol}</span>
            <span className="stage-name">
              <strong>{stage.label_zh}</strong>
              <small>{stage.label_en}</small>
            </span>
            <span className="stage-status">{meta.label}</span>
          </li>
        )
      })}
    </ol>
  )
}

function Diagnostics({ title, items, emptyText }) {
  return (
    <div className="diagnostic">
      <h2>{title}</h2>
      {items.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>
              <span className="mono">{item.stage || item.revision_id || 'run'}</span>
              <span>{item.type || item.status || 'status'}</span>
              <strong>{item.message || item.reason}</strong>
            </li>
          ))}
        </ul>
      ) : (
        <p>{emptyText}</p>
      )}
    </div>
  )
}

export default App
