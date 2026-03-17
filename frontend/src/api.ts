import type { IngestionResponse, ListingsResponse, Scorecard } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8011'

export async function uploadCsv(file: File): Promise<IngestionResponse> {
  const fd = new FormData()
  fd.append('source', 'manual_csv')
  fd.append('file', file)
  const res = await fetch(`${API_BASE}/api/ingestions`, { method: 'POST', body: fd })
  return res.json()
}

export async function fetchListings(params: Record<string, string>): Promise<ListingsResponse> {
  const qs = new URLSearchParams(params)
  const res = await fetch(`${API_BASE}/api/listings?${qs}`)
  return res.json()
}

export async function fetchScorecard(): Promise<Scorecard> {
  const res = await fetch(`${API_BASE}/api/scorecards/active`)
  return res.json()
}

export async function saveScorecard(payload: Partial<Scorecard>) {
  const res = await fetch(`${API_BASE}/api/scorecards/active`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}

export async function saveFeedback(runId: number, listingId: string, label: string) {
  return fetch(`${API_BASE}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ runId, listingId, label }),
  })
}

export function exportCsvUrl(runId: number, top = 200) {
  return `${API_BASE}/api/export/top.csv?runId=${runId}&top=${top}`
}

export async function emailDraft(runId: number, top = 5) {
  const res = await fetch(`${API_BASE}/api/digest/email_draft?runId=${runId}&top=${top}`)
  return res.json()
}
