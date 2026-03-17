export type Bucket = 'schedule_visit' | 'desk_review' | 'skip'

export interface Listing {
  listingId: string
  score: number
  bucket: Bucket
  price: number
  dom: number
  aiRiskCount: number
  aiUpsideCount: number
  aiSummary?: string | null
  reasons: string[]
  risks: string[]
  reviewStatus?: 'unreviewed' | 'watchlist' | 'visited' | 'rejected'
  roi?: {
    arv_estimate: number
    rehab_estimate: number
    holding_cost: number
    transaction_cost: number
    projected_profit: number
    projected_margin: number
  }
}

export interface ListingsResponse {
  items: Listing[]
  total: number
  page: number
  pageSize: number
}

export interface IngestionResponse {
  ingestionRunId: number
  rowsReceived: number
  rowsAccepted: number
  rowsRejected: number
}

export interface Scorecard {
  id: number
  name: string
  ppsf_low_bonus: number
  ppsf_mid_bonus: number
  dom_low_bonus: number
  dom_mid_bonus: number
  dom_high_penalty: number
  condition_good_bonus: number
  condition_fair_penalty: number
  ai_upside_bonus: number
  ai_risk_penalty: number
}
