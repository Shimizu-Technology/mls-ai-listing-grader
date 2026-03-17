# MLS AI Listing Grader

Production-oriented split architecture:
- `backend/` — FastAPI API + SQLAlchemy persistence + scoring + OpenRouter hook
- `frontend/` — React + TypeScript (Vite) UI

## Stack
- Backend: FastAPI, SQLAlchemy, SQLite (default), OpenRouter integration
- Frontend: React, TypeScript, Vite, Lucide icons

## Run Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set OPENROUTER_API_KEY in .env
uvicorn src.app:app --reload --port 8011
```

## Run Frontend
```bash
cd frontend
npm install
# optional: VITE_API_BASE=http://localhost:8011
npm run dev
```

Frontend URL: `http://localhost:5173`
Backend docs: `http://localhost:8011/docs`

## Core API Endpoints
- `POST /api/ingestions`
- `GET /api/listings`
- `GET /api/scorecards/active`
- `PUT /api/scorecards/active`
- `POST /api/feedback`
- `GET /api/digest/preview`
- `GET /api/digest/email_draft`
- `GET /api/export/top.csv`

## Frontend Features
- CSV upload
- Ranked listings table
- Filters, sorting, pagination
- Scorecard weight editor + presets
- Feedback labeling
- CSV export + email draft generation
- Inline reason/risk explainability
- Local UI state persistence
