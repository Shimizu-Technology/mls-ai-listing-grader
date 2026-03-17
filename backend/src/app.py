from fastapi import FastAPI, UploadFile, File, Form, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import csv
import io
from typing import Optional

from .db import Base, engine, get_db
from .models import IngestionRun, Listing, ScorecardConfig, FeedbackLabel, ListingReviewStatus
from .scoring import score_listing, explain_listing, estimate_flip_roi
from .ai import summarize_remarks
from .config import TOP_DEFAULT, APP_API_KEY

Base.metadata.create_all(bind=engine)
app = FastAPI(title="MLS AI Listing Grader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_gate(request, call_next):
    if APP_API_KEY and request.url.path.startswith("/api"):
        incoming = request.headers.get("x-api-key", "")
        if incoming != APP_API_KEY:
            return Response(content='{"error":"unauthorized"}', media_type="application/json", status_code=401)
    return await call_next(request)


class ScorecardUpdate(BaseModel):
    ppsf_low_bonus: float
    ppsf_mid_bonus: float
    dom_low_bonus: float
    dom_mid_bonus: float
    dom_high_penalty: float
    condition_good_bonus: float
    condition_fair_penalty: float
    ai_upside_bonus: float
    ai_risk_penalty: float


class FeedbackIn(BaseModel):
    runId: int
    listingId: str
    label: str
    notes: Optional[str] = None


class ReviewStatusIn(BaseModel):
    runId: int
    listingId: str
    status: str
    notes: Optional[str] = None


def to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default


def to_int(v, default=0):
    try:
        return int(float(v))
    except Exception:
        return default


def get_or_create_scorecard(db: Session):
    cfg = db.query(ScorecardConfig).order_by(ScorecardConfig.id.asc()).first()
    if not cfg:
        cfg = ScorecardConfig(name="default")
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def cfg_to_dict(cfg: ScorecardConfig):
    return {
        "ppsf_low_bonus": cfg.ppsf_low_bonus,
        "ppsf_mid_bonus": cfg.ppsf_mid_bonus,
        "dom_low_bonus": cfg.dom_low_bonus,
        "dom_mid_bonus": cfg.dom_mid_bonus,
        "dom_high_penalty": cfg.dom_high_penalty,
        "condition_good_bonus": cfg.condition_good_bonus,
        "condition_fair_penalty": cfg.condition_fair_penalty,
        "ai_upside_bonus": cfg.ai_upside_bonus,
        "ai_risk_penalty": cfg.ai_risk_penalty,
    }


@app.get("/")
def root():
    return {"name": "MLS AI Listing Grader API", "docs": "/docs"}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/ingestions")
async def create_ingestion(
    file: UploadFile = File(...),
    source: str = Form(default="manual_csv"),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))

    cfg = get_or_create_scorecard(db)
    weights = cfg_to_dict(cfg)

    run = IngestionRun(source=source, filename=file.filename)
    db.add(run)
    db.flush()

    rows_received = 0
    rows_accepted = 0

    for row in reader:
        rows_received += 1
        listing_id = row.get("ListingId") or f"row-{rows_received}"
        price = to_float(row.get("ListPrice"))
        beds = to_float(row.get("BedroomsTotal"))
        baths = to_float(row.get("BathroomsTotalInteger"))
        sqft = to_float(row.get("LivingArea"))
        dom = to_int(row.get("DaysOnMarket"))
        condition = (row.get("PropertyCondition") or "").strip()
        remarks = (row.get("PublicRemarks") or "").strip()

        score, bucket, risk, upside, _reasons, _risks, _roi = score_listing(price, sqft, dom, condition, remarks, weights)
        ai_summary = summarize_remarks(remarks)

        rec = Listing(
            run_id=run.id,
            listing_id=listing_id,
            list_price=price,
            beds=beds,
            baths=baths,
            sqft=sqft,
            dom=dom,
            condition=condition,
            remarks=remarks,
            score=score,
            bucket=bucket,
            ai_risk_count=risk,
            ai_upside_count=upside,
            ai_summary=ai_summary,
        )
        db.add(rec)
        rows_accepted += 1

    run.rows_received = rows_received
    run.rows_accepted = rows_accepted
    db.commit()

    return {
        "ingestionRunId": run.id,
        "rowsReceived": rows_received,
        "rowsAccepted": rows_accepted,
        "rowsRejected": max(0, rows_received - rows_accepted),
        "errors": [],
    }


@app.get("/api/ingestions/{run_id}")
def get_ingestion(run_id: int, db: Session = Depends(get_db)):
    run = db.query(IngestionRun).filter(IngestionRun.id == run_id).first()
    if not run:
        return {"error": "not_found"}
    return {
        "id": run.id,
        "source": run.source,
        "filename": run.filename,
        "rowsReceived": run.rows_received,
        "rowsAccepted": run.rows_accepted,
        "createdAt": run.created_at.isoformat() if run.created_at else None,
    }


@app.get("/api/runs")
def list_runs(limit: int = Query(default=20), db: Session = Depends(get_db)):
    rows = db.query(IngestionRun).order_by(IngestionRun.id.desc()).limit(max(1, min(100, limit))).all()
    return {
        "items": [
            {
                "id": r.id,
                "filename": r.filename,
                "source": r.source,
                "rowsAccepted": r.rows_accepted,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@app.get("/api/runs/compare")
def compare_runs(currentRunId: int = Query(...), db: Session = Depends(get_db)):
    prev = db.query(IngestionRun).filter(IngestionRun.id < currentRunId).order_by(IngestionRun.id.desc()).first()
    if not prev:
        return {"error": "no_previous_run"}

    current_rows = db.query(Listing).filter(Listing.run_id == currentRunId).order_by(Listing.score.desc()).limit(20).all()
    prev_rows = db.query(Listing).filter(Listing.run_id == prev.id).order_by(Listing.score.desc()).limit(20).all()
    current_ids = [r.listing_id for r in current_rows]
    prev_ids = [r.listing_id for r in prev_rows]

    overlap = sorted(set(current_ids).intersection(set(prev_ids)))
    new_ids = [x for x in current_ids if x not in prev_ids]
    dropped_ids = [x for x in prev_ids if x not in current_ids]

    return {
        "currentRunId": currentRunId,
        "previousRunId": prev.id,
        "overlap": overlap,
        "newTop": new_ids,
        "droppedTop": dropped_ids,
    }


@app.get("/api/listings")
def get_listings(
    runId: int = Query(...),
    bucket: Optional[str] = Query(default=None),
    reviewStatus: Optional[str] = Query(default=None),
    limit: int = Query(default=TOP_DEFAULT),
    page: int = Query(default=1),
    sortBy: str = Query(default="score"),
    sortDir: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    q = db.query(Listing).filter(Listing.run_id == runId)
    if bucket:
        q = q.filter(Listing.bucket == bucket)

    if reviewStatus:
        review_rows = (
            db.query(ListingReviewStatus.listing_id)
            .filter(ListingReviewStatus.run_id == runId, ListingReviewStatus.status == reviewStatus)
            .all()
        )
        listing_ids = [r[0] for r in review_rows]
        if listing_ids:
            q = q.filter(Listing.listing_id.in_(listing_ids))
        else:
            return {"items": [], "total": 0, "page": 1, "pageSize": limit}

    total = q.count()

    sort_map = {
        "score": Listing.score,
        "price": Listing.list_price,
        "dom": Listing.dom,
        "listing": Listing.listing_id,
    }
    col = sort_map.get(sortBy, Listing.score)
    q = q.order_by(col.desc() if sortDir == "desc" else col.asc())

    page = max(1, page)
    limit = max(1, min(500, limit))
    offset = (page - 1) * limit
    rows = q.offset(offset).limit(limit).all()

    items = []
    for r in rows:
        reasons, risks = explain_listing(r.list_price, r.sqft, r.dom, r.condition, r.ai_risk_count, r.ai_upside_count)
        roi = estimate_flip_roi(r.list_price, r.condition, r.ai_risk_count, r.ai_upside_count)
        review = (
            db.query(ListingReviewStatus)
            .filter(ListingReviewStatus.run_id == runId, ListingReviewStatus.listing_id == r.listing_id)
            .order_by(ListingReviewStatus.id.desc())
            .first()
        )
        items.append(
            {
                "listingId": r.listing_id,
                "score": r.score,
                "bucket": r.bucket,
                "price": r.list_price,
                "dom": r.dom,
                "aiRiskCount": r.ai_risk_count,
                "aiUpsideCount": r.ai_upside_count,
                "aiSummary": r.ai_summary,
                "reasons": reasons,
                "risks": risks,
                "reviewStatus": review.status if review else "unreviewed",
                "roi": roi,
            }
        )

    return {"items": items, "total": total, "page": page, "pageSize": limit}


@app.get("/api/export/top.csv")
def export_top_csv(runId: int = Query(...), top: int = Query(default=25), db: Session = Depends(get_db)):
    rows = (
        db.query(Listing)
        .filter(Listing.run_id == runId)
        .order_by(Listing.score.desc())
        .limit(max(1, min(500, top)))
        .all()
    )
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["ListingId", "Score", "Bucket", "Price", "DOM", "AiSummary"])
    for r in rows:
        w.writerow([r.listing_id, r.score, r.bucket, r.list_price, r.dom, r.ai_summary or ""])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=mls_top_{runId}.csv"},
    )


@app.get("/api/digest/preview")
def digest_preview(runId: int = Query(...), top: int = Query(default=5), db: Session = Depends(get_db)):
    rows = db.query(Listing).filter(Listing.run_id == runId).order_by(Listing.score.desc()).limit(top).all()
    return {
        "subject": f"MLS Top {top} candidates (run {runId})",
        "items": [
            {
                "listingId": r.listing_id,
                "score": r.score,
                "bucket": r.bucket,
                "price": r.list_price,
                "dom": r.dom,
                "summary": r.ai_summary,
            }
            for r in rows
        ],
    }


@app.get("/api/digest/email_draft")
def digest_email_draft(runId: int = Query(...), top: int = Query(default=5), status: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    base_q = db.query(Listing).filter(Listing.run_id == runId)
    rows = base_q.order_by(Listing.score.desc()).limit(max(1, min(20, top))).all()
    if status:
      keep = []
      for r in rows:
          review = db.query(ListingReviewStatus).filter(ListingReviewStatus.run_id == runId, ListingReviewStatus.listing_id == r.listing_id).first()
          current = review.status if review else "unreviewed"
          if current == status:
              keep.append(r)
      rows = keep
    lines = [f"MLS Top {top} candidates (run {runId})", ""]
    for i, r in enumerate(rows, start=1):
        lines.append(f"{i}. {r.listing_id} | score {r.score} | {r.bucket} | ${r.list_price:,.0f} | DOM {r.dom}")
        if r.ai_summary:
            lines.append(f"   - {r.ai_summary}")
    return {"subject": f"MLS Top {top} candidates", "body": "\n".join(lines)}


@app.get("/api/scorecards/active")
def get_scorecard(db: Session = Depends(get_db)):
    cfg = get_or_create_scorecard(db)
    return {"id": cfg.id, "name": cfg.name, **cfg_to_dict(cfg)}


@app.put("/api/scorecards/active")
def update_scorecard(payload: ScorecardUpdate, db: Session = Depends(get_db)):
    cfg = get_or_create_scorecard(db)
    for k, v in payload.model_dump().items():
        setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return {"ok": True, "scorecard": {"id": cfg.id, **cfg_to_dict(cfg)}}


@app.post("/api/feedback")
def create_feedback(payload: FeedbackIn, db: Session = Depends(get_db)):
    if payload.label not in ["good_lead", "false_positive", "false_negative"]:
        return {"error": "invalid_label"}
    fb = FeedbackLabel(run_id=payload.runId, listing_id=payload.listingId, label=payload.label, notes=payload.notes)
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"ok": True, "id": fb.id}


@app.get("/api/feedback")
def get_feedback(runId: int = Query(...), listingId: str = Query(...), db: Session = Depends(get_db)):
    rows = (
        db.query(FeedbackLabel)
        .filter(FeedbackLabel.run_id == runId, FeedbackLabel.listing_id == listingId)
        .order_by(FeedbackLabel.id.desc())
        .limit(20)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "label": r.label,
                "notes": r.notes,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }


@app.post("/api/review-status")
def set_review_status(payload: ReviewStatusIn, db: Session = Depends(get_db)):
    if payload.status not in ["unreviewed", "watchlist", "visited", "rejected"]:
        return {"error": "invalid_status"}
    row = (
        db.query(ListingReviewStatus)
        .filter(ListingReviewStatus.run_id == payload.runId, ListingReviewStatus.listing_id == payload.listingId)
        .first()
    )
    if not row:
        row = ListingReviewStatus(run_id=payload.runId, listing_id=payload.listingId)
        db.add(row)
    row.status = payload.status
    row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return {"ok": True, "status": row.status}


@app.get("/api/review-status")
def get_review_status(runId: int = Query(...), listingId: str = Query(...), db: Session = Depends(get_db)):
    row = (
        db.query(ListingReviewStatus)
        .filter(ListingReviewStatus.run_id == runId, ListingReviewStatus.listing_id == listingId)
        .first()
    )
    return {"status": row.status if row else "unreviewed", "notes": row.notes if row else None}
