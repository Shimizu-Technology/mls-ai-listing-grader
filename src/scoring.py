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


def score_listing(price: float, sqft: float, dom: int, condition: str, remarks: str, weights: dict | None = None):
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
    return round(score, 1), bucket, risk, upside
