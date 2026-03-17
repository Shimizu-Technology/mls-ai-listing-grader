import type { IngestionResponse, ListingsResponse, Scorecard } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8011'

function apiHeaders(extra: HeadersInit = {}) {
  const key = localStorage.getItem('mls_api_key') || ''
  return key ? { ...extra, 'x-api-key': key } : extra
}

export async function uploadCsv(file: File): Promise<IngestionResponse> {
  const fd = new FormData()
  fd.append('source', 'manual_csv')
  fd.append('file', file)
  const res = await fetch(`${API_BASE}/api/ingestions`, { method: 'POST', body: fd, headers: apiHeaders() })
  return res.json()
}

export async function fetchListings(params: Record<string, string>): Promise<ListingsResponse> {
  const qs = new URLSearchParams(params)
  const res = await fetch(`${API_BASE}/api/listings?${qs}`, { headers: apiHeaders() })
  return res.json()
}

export async function fetchScorecard(): Promise<Scorecard> {
  const res = await fetch(`${API_BASE}/api/scorecards/active`, { headers: apiHeaders() })
  return res.json()
}

export async function saveScorecard(payload: Partial<Scorecard>) {
  const res = await fetch(`${API_BASE}/api/scorecards/active`, {
    method: 'PUT',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  return res.json()
}

export async function saveFeedback(runId: number, listingId: string, label: string, notes?: string) {
  return fetch(`${API_BASE}/api/feedback`, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ runId, listingId, label, notes }),
  })
}

export async function getFeedback(runId: number, listingId: string) {
  const qs = new URLSearchParams({ runId: String(runId), listingId })
  const res = await fetch(`${API_BASE}/api/feedback?${qs}`, { headers: apiHeaders() })
  return res.json()
}

export async function setReviewStatus(runId: number, listingId: string, status: string, notes?: string) {
  const res = await fetch(`${API_BASE}/api/review-status`, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ runId, listingId, status, notes }),
  })
  return res.json()
}

export async function getReviewStatus(runId: number, listingId: string) {
  const qs = new URLSearchParams({ runId: String(runId), listingId })
  const res = await fetch(`${API_BASE}/api/review-status?${qs}`, { headers: apiHeaders() })
  return res.json()
}

export async function exportCsv(runId: number, top = 200) {
  const res = await fetch(`${API_BASE}/api/export/top.csv?runId=${runId}&top=${top}`, { headers: apiHeaders() })
  return res.blob()
}

export async function emailDraft(runId: number, top = 5) {
  const res = await fetch(`${API_BASE}/api/digest/email_draft?runId=${runId}&top=${top}`, { headers: apiHeaders() })
  return res.json()
}
