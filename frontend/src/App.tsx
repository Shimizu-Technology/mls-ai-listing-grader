import { useEffect, useMemo, useState } from 'react'
import { FileUp, Filter, SlidersHorizontal, Download, Mail, KeyRound, X } from 'lucide-react'
import { compareRuns, emailDraft, exportCsv, fetchListings, fetchRuns, fetchScorecard, getFeedback, getReviewStatus, saveFeedback, saveScorecard, setReviewStatus, uploadCsv } from './api'
import type { Listing, Scorecard } from './types'

const WEIGHT_KEYS: (keyof Scorecard)[] = [
  'ppsf_low_bonus', 'ppsf_mid_bonus', 'dom_low_bonus', 'dom_mid_bonus', 'dom_high_penalty',
  'condition_good_bonus', 'condition_fair_penalty', 'ai_upside_bonus', 'ai_risk_penalty',
]

function App() {
  const [runId, setRunId] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [meta, setMeta] = useState('')
  const [bucket, setBucket] = useState('')
  const [reviewFilter, setReviewFilter] = useState('')
  const [limit, setLimit] = useState(20)
  const [sortBy, setSortBy] = useState('score')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [items, setItems] = useState<Listing[]>([])
  const [scorecard, setScorecard] = useState<Scorecard | null>(null)
  const [debug, setDebug] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [selected, setSelected] = useState<Listing | null>(null)
  const [runs, setRuns] = useState<Array<{id:number;createdAt?:string;rowsAccepted:number;filename?:string}>>([])
  const [runCompare, setRunCompare] = useState<{previousRunId?:number;overlap?:string[];newTop?:string[];droppedTop?:string[]}|null>(null)
  const [feedbackHistory, setFeedbackHistory] = useState<Array<{label:string;createdAt?:string;notes?:string}>>([])
  const [detailStatus, setDetailStatus] = useState<'unreviewed'|'watchlist'|'visited'|'rejected'>('unreviewed')
  const [detailFeedbackLabel, setDetailFeedbackLabel] = useState<'good_lead'|'false_positive'|'false_negative'|''>('')
  const [detailFeedbackNotes, setDetailFeedbackNotes] = useState('')

  useEffect(() => {
    const persistedKey = localStorage.getItem('mls_api_key') || ''
    setApiKey(persistedKey)

    fetchScorecard().then(setScorecard).catch((e) => setDebug(String(e)))
    refreshRuns().catch((e) => setDebug(String(e)))
    const raw = localStorage.getItem('mls_ui_state')
    if (raw) {
      const s = JSON.parse(raw)
      if (s.runId) setRunId(s.runId)
      if (s.bucket !== undefined) setBucket(s.bucket)
      if (s.reviewFilter !== undefined) setReviewFilter(s.reviewFilter)
      if (s.limit) setLimit(s.limit)
      if (s.sortBy) setSortBy(s.sortBy)
      if (s.sortDir) setSortDir(s.sortDir)
      if (s.page) setPage(s.page)
    }
  }, [])

  useEffect(() => {
    localStorage.setItem('mls_ui_state', JSON.stringify({ runId, bucket, reviewFilter, limit, sortBy, sortDir, page }))
  }, [runId, bucket, reviewFilter, limit, sortBy, sortDir, page])

  useEffect(() => {
    if (!runId) return
    refreshListings()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, bucket, reviewFilter, limit, sortBy, sortDir, page])

  const maxPage = useMemo(() => Math.max(1, Math.ceil(total / Math.max(1, limit))), [total, limit])

  async function onUpload() {
    if (!file) return
    const res = await uploadCsv(file)
    setRunId(res.ingestionRunId)
    setMeta(`Rows accepted: ${res.rowsAccepted}/${res.rowsReceived}`)
    setDebug(JSON.stringify(res, null, 2))
    setPage(1)
    await refreshRuns()
  }

  async function refreshListings() {
    if (!runId) return
    const res = await fetchListings({
      runId: String(runId),
      page: String(page),
      limit: String(limit),
      sortBy,
      sortDir,
      ...(bucket ? { bucket } : {}),
      ...(reviewFilter ? { reviewStatus: reviewFilter } : {}),
    })
    setItems(res.items)
    setTotal(res.total)
  }

  async function refreshRuns() {
    const res = await fetchRuns(20)
    setRuns(res.items || [])
  }

  async function onSaveWeights() {
    if (!scorecard) return
    const payload: Partial<Scorecard> = {}
    WEIGHT_KEYS.forEach((k) => { payload[k] = scorecard[k] as never })
    const res = await saveScorecard(payload)
    if (res.scorecard) setScorecard({ ...scorecard, ...res.scorecard })
  }

  function applyPreset(name: 'conservative' | 'balanced' | 'aggressive') {
    if (!scorecard) return
    const presets: Record<string, Partial<Scorecard>> = {
      conservative: { ppsf_low_bonus: 8, ppsf_mid_bonus: 4, dom_low_bonus: 4, dom_mid_bonus: 2, dom_high_penalty: 5, condition_good_bonus: 6, condition_fair_penalty: 8, ai_upside_bonus: 1.5, ai_risk_penalty: 3.5 },
      balanced: { ppsf_low_bonus: 12, ppsf_mid_bonus: 6, dom_low_bonus: 6, dom_mid_bonus: 3, dom_high_penalty: 3, condition_good_bonus: 8, condition_fair_penalty: 6, ai_upside_bonus: 2, ai_risk_penalty: 2.5 },
      aggressive: { ppsf_low_bonus: 14, ppsf_mid_bonus: 8, dom_low_bonus: 5, dom_mid_bonus: 2, dom_high_penalty: 2, condition_good_bonus: 6, condition_fair_penalty: 4, ai_upside_bonus: 2.5, ai_risk_penalty: 1.8 },
    }
    setScorecard({ ...scorecard, ...presets[name] })
  }

  async function onFeedback(listingId: string, label: string, notes?: string) {
    if (!runId || !label) return
    await saveFeedback(runId, listingId, label, notes)
    if (selected?.listingId === listingId) {
      const fb = await getFeedback(runId, listingId)
      setFeedbackHistory((fb.items || []).map((x: { label: string; createdAt?: string; notes?: string }) => ({ label: x.label, createdAt: x.createdAt, notes: x.notes })))
    }
  }

  async function onEmailDraft() {
    if (!runId) return
    const res = await emailDraft(runId, 5)
    setDebug(`SUBJECT: ${res.subject}\n\n${res.body}`)
  }

  async function onCompareRun() {
    if (!runId) return
    const res = await compareRuns(runId)
    setRunCompare(res)
    setDebug(JSON.stringify(res, null, 2))
  }

  async function openDetail(item: Listing) {
    setSelected(item)
    if (!runId) return
    const [fb, rs] = await Promise.all([
      getFeedback(runId, item.listingId),
      getReviewStatus(runId, item.listingId),
    ])
    setFeedbackHistory((fb.items || []).map((x: { label: string; createdAt?: string; notes?: string }) => ({ label: x.label, createdAt: x.createdAt, notes: x.notes })))
    setDetailStatus((rs.status || 'unreviewed') as 'unreviewed' | 'watchlist' | 'visited' | 'rejected')
    setDetailFeedbackLabel('')
    setDetailFeedbackNotes('')
  }

  async function saveDetailStatus(next: 'unreviewed'|'watchlist'|'visited'|'rejected') {
    if (!runId || !selected) return
    await setReviewStatus(runId, selected.listingId, next)
    setDetailStatus(next)
    setItems((prev) => prev.map((x) => x.listingId === selected.listingId ? { ...x, reviewStatus: next } : x))
  }

  async function onExportCsv() {
    if (!runId) return
    const blob = await exportCsv(runId, 200)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `mls_top_${runId}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  function saveApiKey() {
    if (apiKey.trim()) localStorage.setItem('mls_api_key', apiKey.trim())
    else localStorage.removeItem('mls_api_key')
    setDebug('Saved API key setting. Refreshing scorecard...')
    fetchScorecard().then(setScorecard).catch((e) => setDebug(String(e)))
  }

  return (
    <main className="app-shell">
      <h1 style={{ margin: 0 }}>MLS AI Listing Grader</h1>
      <p className="muted" style={{ marginTop: 6 }}>FastAPI backend + React frontend. Distinctive, explainable scoring workflow.</p>

      <section className="grid-two" style={{ marginTop: 14 }}>
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Upload Run</h3>
          <div className="row">
            <input type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
            <button className="primary" onClick={onUpload}><FileUp size={16} /> Upload CSV</button>
          </div>
          <p className="muted">Run ID: {runId ?? '-'} · {meta}</p>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>API Access</h3>
          <div className="row">
            <KeyRound size={16} />
            <input type="password" placeholder="x-api-key (optional)" value={apiKey} onChange={(e)=>setApiKey(e.target.value)} style={{ minWidth: 280 }} />
            <button onClick={saveApiKey}>Save Key</button>
          </div>
          <p className="muted">Set this if backend APP_API_KEY is enabled.</p>
        </div>
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Scorecard Weights</h3>
        {scorecard && (
          <>
            <div className="row" style={{ marginBottom: 8 }}>
              <button onClick={() => applyPreset('conservative')}>Conservative</button>
              <button onClick={() => applyPreset('balanced')}>Balanced</button>
              <button onClick={() => applyPreset('aggressive')}>Aggressive</button>
              <button className="primary" onClick={onSaveWeights}><SlidersHorizontal size={16} /> Save</button>
            </div>
            <div className="row">
              {WEIGHT_KEYS.map((k) => (
                <label key={k} style={{ display: 'grid', gap: 4 }}>
                  <span className="muted">{k}</span>
                  <input
                    type="number"
                    step="0.1"
                    value={Number(scorecard[k] as number)}
                    onChange={(e) => setScorecard({ ...scorecard, [k]: Number(e.target.value) })}
                    style={{ width: 120 }}
                  />
                </label>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="card" style={{ marginTop: 16 }}>
        <div className="row" style={{ marginBottom: 10 }}>
          <Filter size={16} />
          <select value={bucket} onChange={(e) => { setBucket(e.target.value); setPage(1) }}>
            <option value="">all buckets</option>
            <option value="schedule_visit">schedule_visit</option>
            <option value="desk_review">desk_review</option>
            <option value="skip">skip</option>
          </select>
          <select value={reviewFilter} onChange={(e) => { setReviewFilter(e.target.value); setPage(1) }}>
            <option value="">all review states</option>
            <option value="unreviewed">unreviewed</option>
            <option value="watchlist">watchlist</option>
            <option value="visited">visited</option>
            <option value="rejected">rejected</option>
          </select>
          <input type="number" min={1} max={500} value={limit} onChange={(e) => { setLimit(Number(e.target.value)); setPage(1) }} style={{ width: 90 }} />
          <select value={sortBy} onChange={(e) => { setSortBy(e.target.value); setPage(1) }}>
            <option value="score">score</option>
            <option value="price">price</option>
            <option value="dom">dom</option>
            <option value="listing">listing</option>
          </select>
          <select value={sortDir} onChange={(e) => { setSortDir(e.target.value as 'asc' | 'desc'); setPage(1) }}>
            <option value="desc">desc</option>
            <option value="asc">asc</option>
          </select>
          <button onClick={() => setPage(Math.max(1, page - 1))}>Prev</button>
          <span className="muted">Page {page}/{maxPage} ({total})</span>
          <button onClick={() => setPage(Math.min(maxPage, page + 1))}>Next</button>
          <button onClick={refreshListings}>Refresh</button>
          <button onClick={onExportCsv}><Download size={16} /> CSV</button>
          <button onClick={onEmailDraft}><Mail size={16} /> Draft</button>
          <button onClick={onCompareRun}>Compare Prev Run</button>
        </div>

        <div className="kicker" style={{ marginBottom: 10 }}>
          Recent runs: {runs.slice(0, 6).map((r) => `${r.id}${r.id === runId ? '*' : ''} (${r.rowsAccepted})`).join(' • ') || 'none'}
        </div>
        {runCompare && (
          <div className="kicker" style={{ marginBottom: 10 }}>
            Compare vs run {runCompare.previousRunId}: overlap {runCompare.overlap?.length || 0}, new {runCompare.newTop?.length || 0}, dropped {runCompare.droppedTop?.length || 0}
          </div>
        )}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Listing</th><th>Score</th><th>Bucket</th><th>Price</th><th>DOM</th><th>Analysis</th><th>Feedback</th>
              </tr>
            </thead>
            <tbody>
              {items.map((x) => (
                <tr key={x.listingId} onClick={() => openDetail(x)} style={{ cursor: 'pointer' }}>
                  <td>{x.listingId}</td>
                  <td><strong>{x.score}</strong></td>
                  <td><span className={`badge ${x.bucket}`}>{x.bucket}</span></td>
                  <td>${x.price.toLocaleString()}</td>
                  <td>{x.dom}</td>
                  <td>
                    <div>{x.aiSummary || ''}</div>
                    <div className="kicker">+ {x.reasons.join(' • ')}</div>
                    <div className="kicker risk">! {x.risks.join(' • ')}</div>
                    <div className="kicker">review: {x.reviewStatus || 'unreviewed'}</div>
                    {x.roi && <div className="kicker">ROI est: {(x.roi.projected_margin * 100).toFixed(1)}% · profit ${x.roi.projected_profit.toLocaleString()}</div>}
                  </td>
                  <td>
                    <div className="row">
                      <select onClick={(e)=>e.stopPropagation()} onChange={(e) => onFeedback(x.listingId, e.target.value)} defaultValue="">
                        <option value="">feedback</option>
                        <option value="good_lead">good_lead</option>
                        <option value="false_positive">false_positive</option>
                        <option value="false_negative">false_negative</option>
                      </select>
                      <button onClick={(e)=>{
                        e.stopPropagation();
                        if(runId) setReviewStatus(runId, x.listingId, 'watchlist').then(() =>
                          setItems(prev => prev.map(i => i.listingId === x.listingId ? { ...i, reviewStatus: 'watchlist' } : i))
                        )
                      }}>watch</button>
                      <button onClick={(e)=>{
                        e.stopPropagation();
                        if(runId) setReviewStatus(runId, x.listingId, 'visited').then(() =>
                          setItems(prev => prev.map(i => i.listingId === x.listingId ? { ...i, reviewStatus: 'visited' } : i))
                        )
                      }}>visited</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {selected && (
        <div className="card" style={{ marginTop: 16, borderColor: '#99f6e4' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h3 style={{ margin: 0 }}>Listing Detail · {selected.listingId}</h3>
            <button onClick={() => setSelected(null)}><X size={16} /></button>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <span className={`badge ${selected.bucket}`}>{selected.bucket}</span>
            <span><strong>Score:</strong> {selected.score}</span>
            <span><strong>Price:</strong> ${selected.price.toLocaleString()}</span>
            <span><strong>DOM:</strong> {selected.dom}</span>
          </div>
          <p className="kicker" style={{ marginTop: 10 }}><strong>AI Summary:</strong> {selected.aiSummary || '—'}</p>
          <p className="kicker"><strong>Reasons:</strong> {selected.reasons.join(' • ') || '—'}</p>
          <p className="kicker risk"><strong>Risks:</strong> {selected.risks.join(' • ') || '—'}</p>
          {selected.roi && (
            <div className="kicker" style={{ marginTop: 8 }}>
              <strong>ROI estimate:</strong> margin {(selected.roi.projected_margin * 100).toFixed(1)}% · profit ${selected.roi.projected_profit.toLocaleString()} · ARV ${selected.roi.arv_estimate.toLocaleString()} · rehab ${selected.roi.rehab_estimate.toLocaleString()}
            </div>
          )}
          <div className="row" style={{ marginTop: 10 }}>
            <strong>Status:</strong>
            <select value={detailStatus} onChange={(e)=>saveDetailStatus(e.target.value as any)}>
              <option value="unreviewed">unreviewed</option>
              <option value="watchlist">watchlist</option>
              <option value="visited">visited</option>
              <option value="rejected">rejected</option>
            </select>
          </div>
          <div className="row" style={{ marginTop: 10 }}>
            <strong>Add feedback:</strong>
            <select value={detailFeedbackLabel} onChange={(e)=>setDetailFeedbackLabel(e.target.value as any)}>
              <option value="">select label</option>
              <option value="good_lead">good_lead</option>
              <option value="false_positive">false_positive</option>
              <option value="false_negative">false_negative</option>
            </select>
            <input placeholder="optional notes" value={detailFeedbackNotes} onChange={(e)=>setDetailFeedbackNotes(e.target.value)} style={{ minWidth: 260 }} />
            <button onClick={async()=>{ if(selected && detailFeedbackLabel){ await onFeedback(selected.listingId, detailFeedbackLabel, detailFeedbackNotes); setDetailFeedbackLabel(''); setDetailFeedbackNotes(''); }}}>save feedback</button>
          </div>
          <div className="kicker" style={{ marginTop: 10 }}>
            <strong>Recent feedback:</strong> {feedbackHistory.length ? feedbackHistory.map((f)=>`${f.label}${f.notes?`: ${f.notes}`:''}${f.createdAt?` (${new Date(f.createdAt).toLocaleString()})`:''}`).join(' | ') : 'none'}
          </div>
        </div>
      )}

      <pre style={{ background: '#f5f5f4', border: '1px solid var(--border)', borderRadius: 12, padding: 12, marginTop: 16, whiteSpace: 'pre-wrap' }}>{debug}</pre>
    </main>
  )
}

export default App
