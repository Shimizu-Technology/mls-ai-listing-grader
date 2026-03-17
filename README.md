# MLS AI Listing Grader (MVP Scaffold)

Working MVP API + minimal web uploader for CSV-based MLS scoring with optional OpenRouter enrichment.

## Features
- CSV ingestion endpoint
- SQLite persistence (runs + listings + scorecard + feedback)
- Deterministic score + recommendation bucket
- Optional AI summary per listing remarks via OpenRouter
- Ranked listing retrieval endpoint (sorting + pagination)
- Listing explanation signals (top reasons + risks)
- Editable active scorecard weights + presets (conservative/balanced/aggressive)
- Feedback label endpoint
- Digest preview endpoint + email draft endpoint
- Top candidates CSV export endpoint
- Basic web UI at `/` with filters/actions
- UI state persistence (bucket/sort/limit/page/runId) via localStorage

## Setup
```bash
cd ~/work/mls-ai-listing-grader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `OPENROUTER_API_KEY` in `.env` (you can reuse from another project env).

## Run API
```bash
uvicorn src.app:app --reload --port 8011
```

Open browser:
- http://localhost:8011/

## Quick API test (upload sample CSV)
```bash
curl -s -X POST http://localhost:8011/api/ingestions \
  -F "source=sample" \
  -F "file=@/Users/jerry/.openclaw/workspaces/theo/mls-sample/mls_listings_sample.csv"
```

Then query top listings:
```bash
curl -s "http://localhost:8011/api/listings?runId=1&limit=5" | jq
```

Get scorecard:
```bash
curl -s http://localhost:8011/api/scorecards/active | jq
```

Digest preview:
```bash
curl -s "http://localhost:8011/api/digest/preview?runId=1&top=5" | jq
```

Email draft:
```bash
curl -s "http://localhost:8011/api/digest/email_draft?runId=1&top=5" | jq
```

Export CSV:
```bash
curl -L "http://localhost:8011/api/export/top.csv?runId=1&top=50" -o top.csv
```
