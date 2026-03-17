from fastapi import FastAPI, UploadFile, File, Form, Depends, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import csv, io

from .db import Base, engine, get_db
from .models import IngestionRun, Listing, ScorecardConfig, FeedbackLabel
from .scoring import score_listing
from .ai import summarize_remarks
from .config import TOP_DEFAULT

Base.metadata.create_all(bind=engine)
app = FastAPI(title="MLS AI Listing Grader")


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
    notes: str | None = None


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


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <body style='font-family:Arial;padding:24px;max-width:1200px;margin:auto'>
        <h2>MLS AI Listing Grader</h2>
        <p>Upload MLS CSV, tune scorecard, and review ranked candidates.</p>

        <section style='display:grid;grid-template-columns:1fr 1fr;gap:16px'>
          <div style='border:1px solid #ddd;padding:12px;border-radius:8px'>
            <h3>Upload CSV</h3>
            <form id='uploadForm'>
              <input type='file' id='file' accept='.csv' required />
              <button type='submit'>Upload</button>
            </form>
            <p style='font-size:12px;color:#666'>Current run: <span id='runId'>-</span></p>
            <p style='font-size:12px;color:#666' id='ingestionMeta'></p>
          </div>

          <div style='border:1px solid #ddd;padding:12px;border-radius:8px'>
            <h3>Scorecard Weights</h3>
            <div id='weights' style='display:grid;grid-template-columns:1fr 110px;gap:6px 10px;align-items:center'></div>
            <button id='saveWeights'>Save Weights</button>
            <button id='presetConservative' type='button'>Preset: conservative</button>
            <button id='presetBalanced' type='button'>Preset: balanced</button>
            <button id='presetAggressive' type='button'>Preset: aggressive</button>
            <span id='weightsMsg' style='font-size:12px;color:#666;margin-left:8px'></span>
          </div>
        </section>

        <section style='margin-top:16px;border:1px solid #ddd;padding:12px;border-radius:8px'>
          <h3>Listing Results</h3>
          <div style='display:flex;gap:8px;align-items:center;margin-bottom:10px'>
            <label>Bucket:</label>
            <select id='bucket'>
              <option value=''>all</option>
              <option value='schedule_visit'>schedule_visit</option>
              <option value='desk_review'>desk_review</option>
              <option value='skip'>skip</option>
            </select>
            <label>Limit:</label>
            <input id='limit' type='number' value='20' min='1' max='500' style='width:80px' />
            <label>Sort:</label>
            <select id='sortBy'><option value='score'>score</option><option value='price'>price</option><option value='dom'>dom</option><option value='listing'>listing</option></select>
            <select id='sortDir'><option value='desc'>desc</option><option value='asc'>asc</option></select>
            <button id='prevPage'>Prev</button><span id='pageInfo' style='font-size:12px;color:#666'>p1</span><button id='nextPage'>Next</button>
            <button id='refresh'>Refresh</button>
            <button id='digest'>Digest Preview</button>
            <button id='exportCsv'>Export CSV</button>
            <button id='emailDraft'>Email Draft</button>
          </div>
          <div id='digestOut' style='font-size:12px;color:#444;margin-bottom:10px'></div>
          <table border='1' cellspacing='0' cellpadding='6' width='100%' style='border-collapse:collapse'>
            <thead>
              <tr style='background:#f4f4f4'>
                <th>Listing</th><th>Score</th><th>Bucket</th><th>Price</th><th>DOM</th><th>AI Summary</th><th>Feedback</th>
              </tr>
            </thead>
            <tbody id='rows'></tbody>
          </table>
        </section>

        <pre id='debug' style='background:#f8f8f8;padding:10px;margin-top:14px;white-space:pre-wrap'></pre>

        <script>
          const runIdEl = document.getElementById('runId');
          const ingestionMeta = document.getElementById('ingestionMeta');
          const rowsEl = document.getElementById('rows');
          const debug = document.getElementById('debug');
          const weightsEl = document.getElementById('weights');
          const weightsMsg = document.getElementById('weightsMsg');
          const digestOut = document.getElementById('digestOut');
          let currentRunId = null;
          let currentWeights = {};
          let currentPage = 1;
          let totalRows = 0;

          function fmtMoney(n){ return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n||0); }

          async function loadWeights(){
            const r = await fetch('/api/scorecards/active');
            const j = await r.json();
            currentWeights = j;
            const keys = [
              'ppsf_low_bonus','ppsf_mid_bonus','dom_low_bonus','dom_mid_bonus','dom_high_penalty',
              'condition_good_bonus','condition_fair_penalty','ai_upside_bonus','ai_risk_penalty'
            ];
            weightsEl.innerHTML = '';
            keys.forEach(k => {
              const label = document.createElement('label');
              label.textContent = k;
              const input = document.createElement('input');
              input.type = 'number'; input.step = '0.1'; input.value = j[k]; input.id = 'w_' + k;
              weightsEl.appendChild(label); weightsEl.appendChild(input);
            });
          }

          async function saveWeights(){
            const payload = {};
            Object.keys(currentWeights)
              .filter(k => k.includes('_bonus') || k.includes('_penalty'))
              .forEach(k => payload[k] = parseFloat(document.getElementById('w_'+k).value || '0'));
            const r = await fetch('/api/scorecards/active', {
              method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)
            });
            const j = await r.json();
            weightsMsg.textContent = j.ok ? 'saved' : 'save failed';
            setTimeout(()=>weightsMsg.textContent='', 1800);
          }

          async function loadListings(){
            if(!currentRunId){ rowsEl.innerHTML=''; return; }
            const bucket = document.getElementById('bucket').value;
            const limit = document.getElementById('limit').value || '20';
            const sortBy = document.getElementById('sortBy').value;
            const sortDir = document.getElementById('sortDir').value;
            const q = new URLSearchParams({runId:String(currentRunId), limit:String(limit), page:String(currentPage), sortBy, sortDir});
            if(bucket) q.set('bucket', bucket);
            const r = await fetch('/api/listings?' + q.toString());
            const j = await r.json();
            rowsEl.innerHTML = '';
            totalRows = j.total || 0;
            const maxPage = Math.max(1, Math.ceil(totalRows / Number(limit)));
            if(currentPage > maxPage){ currentPage = maxPage; }
            document.getElementById('pageInfo').textContent = `p${currentPage}/${maxPage} (${totalRows})`;
            (j.items || []).forEach(item => {
              const tr = document.createElement('tr');
              tr.innerHTML = `
                <td>${item.listingId}</td>
                <td><b>${item.score}</b></td>
                <td>${item.bucket}</td>
                <td>${fmtMoney(item.price)}</td>
                <td>${item.dom}</td>
                <td>${item.aiSummary || ''}</td>
                <td>
                  <select data-listing='${item.listingId}'>
                    <option value=''>-</option>
                    <option value='good_lead'>good_lead</option>
                    <option value='false_positive'>false_positive</option>
                    <option value='false_negative'>false_negative</option>
                  </select>
                  <button data-save='${item.listingId}'>save</button>
                </td>
              `;
              rowsEl.appendChild(tr);
            });
          }

          async function saveFeedback(listingId, label){
            if(!label) return;
            await fetch('/api/feedback', {
              method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({runId: currentRunId, listingId, label})
            });
          }

          async function loadDigest(){
            if(!currentRunId) return;
            const r = await fetch('/api/digest/preview?runId=' + currentRunId + '&top=5');
            const j = await r.json();
            digestOut.textContent = j.subject + ' | ' + (j.items||[]).map(x => `${x.listingId}(${x.score})`).join(', ');
          }

          document.getElementById('uploadForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const file = document.getElementById('file').files[0];
            const fd = new FormData();
            fd.append('source','manual_csv');
            fd.append('file', file);
            const r = await fetch('/api/ingestions', {method:'POST', body:fd});
            const j = await r.json();
            debug.textContent = JSON.stringify(j, null, 2);
            currentRunId = j.ingestionRunId;
            currentPage = 1;
            runIdEl.textContent = currentRunId || '-';
            ingestionMeta.textContent = `Rows: ${j.rowsAccepted}/${j.rowsReceived}`;
            await loadListings();
          });

          document.getElementById('refresh').addEventListener('click', ()=>{currentPage=1; loadListings();});
          document.getElementById('digest').addEventListener('click', loadDigest);
          document.getElementById('saveWeights').addEventListener('click', saveWeights);
          document.getElementById('prevPage').addEventListener('click', ()=>{ if(currentPage>1){ currentPage--; loadListings(); }});
          document.getElementById('nextPage').addEventListener('click', ()=>{ currentPage++; loadListings(); });
          document.getElementById('sortBy').addEventListener('change', ()=>{ currentPage=1; loadListings(); });
          document.getElementById('sortDir').addEventListener('change', ()=>{ currentPage=1; loadListings(); });
          document.getElementById('bucket').addEventListener('change', ()=>{ currentPage=1; loadListings(); });
          document.getElementById('limit').addEventListener('change', ()=>{ currentPage=1; loadListings(); });

          document.getElementById('exportCsv').addEventListener('click', ()=>{
            if(!currentRunId) return;
            window.open(`/api/export/top.csv?runId=${currentRunId}&top=200`, '_blank');
          });

          document.getElementById('emailDraft').addEventListener('click', async ()=>{
            if(!currentRunId) return;
            const r = await fetch(`/api/digest/email_draft?runId=${currentRunId}&top=5`);
            const j = await r.json();
            debug.textContent = `SUBJECT: ${j.subject}\n\n${j.body}`;
          });

          function applyPreset(name){
            const presets = {
              conservative: {ppsf_low_bonus:8, ppsf_mid_bonus:4, dom_low_bonus:4, dom_mid_bonus:2, dom_high_penalty:5, condition_good_bonus:6, condition_fair_penalty:8, ai_upside_bonus:1.5, ai_risk_penalty:3.5},
              balanced: {ppsf_low_bonus:12, ppsf_mid_bonus:6, dom_low_bonus:6, dom_mid_bonus:3, dom_high_penalty:3, condition_good_bonus:8, condition_fair_penalty:6, ai_upside_bonus:2, ai_risk_penalty:2.5},
              aggressive: {ppsf_low_bonus:14, ppsf_mid_bonus:8, dom_low_bonus:5, dom_mid_bonus:2, dom_high_penalty:2, condition_good_bonus:6, condition_fair_penalty:4, ai_upside_bonus:2.5, ai_risk_penalty:1.8}
            };
            const p = presets[name];
            Object.keys(p).forEach(k=>{ const el=document.getElementById('w_'+k); if(el) el.value = p[k]; });
          }
          document.getElementById('presetConservative').addEventListener('click', ()=>applyPreset('conservative'));
          document.getElementById('presetBalanced').addEventListener('click', ()=>applyPreset('balanced'));
          document.getElementById('presetAggressive').addEventListener('click', ()=>applyPreset('aggressive'));


          rowsEl.addEventListener('click', async (e) => {
            const listingId = e.target.getAttribute('data-save');
            if(!listingId) return;
            const sel = rowsEl.querySelector(`select[data-listing='${listingId}']`);
            await saveFeedback(listingId, sel?.value || '');
          });

          loadWeights().catch(err => debug.textContent = String(err));
        </script>
      </body>
    </html>
    """


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

        score, bucket, risk, upside = score_listing(price, sqft, dom, condition, remarks, weights)
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


@app.get("/api/listings")
def get_listings(
    runId: int = Query(...),
    bucket: str | None = Query(default=None),
    limit: int = Query(default=TOP_DEFAULT),
    page: int = Query(default=1),
    sortBy: str = Query(default="score"),
    sortDir: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    q = db.query(Listing).filter(Listing.run_id == runId)
    if bucket:
        q = q.filter(Listing.bucket == bucket)

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

    return {
        "items": [
            {
                "listingId": r.listing_id,
                "score": r.score,
                "bucket": r.bucket,
                "price": r.list_price,
                "dom": r.dom,
                "aiRiskCount": r.ai_risk_count,
                "aiUpsideCount": r.ai_upside_count,
                "aiSummary": r.ai_summary,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pageSize": limit,
    }




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


@app.get("/api/digest/email_draft")
def digest_email_draft(runId: int = Query(...), top: int = Query(default=5), db: Session = Depends(get_db)):
    rows = (
        db.query(Listing)
        .filter(Listing.run_id == runId)
        .order_by(Listing.score.desc())
        .limit(max(1, min(20, top)))
        .all()
    )
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
    fb = FeedbackLabel(
        run_id=payload.runId,
        listing_id=payload.listingId,
        label=payload.label,
        notes=payload.notes,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"ok": True, "id": fb.id}


@app.get("/api/digest/preview")
def digest_preview(runId: int = Query(...), top: int = Query(default=5), db: Session = Depends(get_db)):
    rows = (
        db.query(Listing)
        .filter(Listing.run_id == runId)
        .order_by(Listing.score.desc())
        .limit(top)
        .all()
    )
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
