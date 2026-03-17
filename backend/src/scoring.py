from typing import Optional
DEFAULT_WEIGHTS = {
    "ppsf_low_bonus": 12,
    "ppsf_mid_bonus": 6,
    "dom_low_bonus": 6,
    "dom_mid_bonus": 3,
    "dom_high_penalty": 3,
    "condition_good_bonus": 8,
    "condition_fair_penalty": 6,
    "ai_upside_bonus": 2,
    "ai_risk_penalty": 2.5,
}


def ai_signals(remarks: str):
    text = (remarks or "").lower()
    risk_words = ["as-is", "deferred maintenance", "moisture", "plumbing", "foundation", "roof leak"]
    upside_words = ["updated", "renovated", "move-in ready", "rental potential", "new roof"]
    risk = sum(1 for w in risk_words if w in text)
    upside = sum(1 for w in upside_words if w in text)
    return risk, upside


def explain_listing(price: float, sqft: float, dom: int, condition: str, risk: int, upside: int):
    reasons = []
    risks = []
    ppsf = (price / sqft) if sqft and sqft > 0 else None

    if ppsf is None:
        risks.append("Missing sqft")
    elif ppsf < 260:
        reasons.append("Low price/sqft")
    elif ppsf < 320:
        reasons.append("Reasonable price/sqft")
    else:
        risks.append("High price/sqft")

    if dom <= 21:
        reasons.append("Fresh listing (low DOM)")
    elif dom > 45:
        risks.append("Stale listing (high DOM)")

    c = (condition or "").lower()
    if c in ["good", "excellent"]:
        reasons.append("Good condition")
    elif c == "fair":
        risks.append("Fair condition")

    if upside > 0:
        reasons.append(f"Upside signals x{upside}")
    if risk > 0:
        risks.append(f"Risk signals x{risk}")

    return reasons[:3], risks[:3]


def estimate_flip_roi(price: float, condition: str, risk_signals: int, upside_signals: int):
    c = (condition or "").lower()
    # heuristics for MVP (tunable later)
    rehab_pct = 0.22 if c == "fair" else 0.12 if c in ["average", "good"] else 0.07
    rehab_pct += max(0, risk_signals - upside_signals) * 0.01
    rehab_estimate = price * rehab_pct
    holding_cost = price * 0.03
    transaction_cost = price * 0.08
    arv_estimate = price * (1.18 + (0.01 * upside_signals) - (0.005 * risk_signals))
    projected_profit = arv_estimate - (price + rehab_estimate + holding_cost + transaction_cost)
    projected_margin = (projected_profit / price) if price > 0 else 0.0
    return {
        "arv_estimate": round(arv_estimate, 2),
        "rehab_estimate": round(rehab_estimate, 2),
        "holding_cost": round(holding_cost, 2),
        "transaction_cost": round(transaction_cost, 2),
        "projected_profit": round(projected_profit, 2),
        "projected_margin": round(projected_margin, 4),
    }


def score_listing(price: float, sqft: float, dom: int, condition: str, remarks: str, weights: Optional[dict] = None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    score = 50.0
    ppsf = (price / sqft) if sqft and sqft > 0 else 9999

    if ppsf < 260:
        score += w["ppsf_low_bonus"]
    elif ppsf < 320:
        score += w["ppsf_mid_bonus"]

    if dom <= 21:
        score += w["dom_low_bonus"]
    elif dom <= 45:
        score += w["dom_mid_bonus"]
    else:
        score -= w["dom_high_penalty"]

    c = (condition or "").lower()
    if c in ["good", "excellent"]:
        score += w["condition_good_bonus"]
    elif c in ["fair"]:
        score -= w["condition_fair_penalty"]

    risk, upside = ai_signals(remarks)
    score += upside * w["ai_upside_bonus"]
    score -= risk * w["ai_risk_penalty"]

    score = max(0, min(100, score))
    bucket = "schedule_visit" if score >= 75 else "desk_review" if score >= 60 else "skip"
    reasons, risks = explain_listing(price, sqft, dom, condition, risk, upside)
    roi = estimate_flip_roi(price, condition, risk, upside)
    return round(score, 1), bucket, risk, upside, reasons, risks, roi
