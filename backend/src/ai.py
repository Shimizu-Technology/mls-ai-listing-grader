import requests
from typing import Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL

def summarize_remarks(remarks: str, model: Optional[str] = None):
    text = (remarks or "").strip()
    if not text:
        return None

    if not OPENROUTER_API_KEY:
        return None

    prompt = (
        "Extract concise flipping-relevant signals from this real-estate listing remark. "
        "Return one short sentence with key upside and risk, no markdown.\n\n"
        f"Remarks: {text[:1200]}"
    )

    try:
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=20,
        )
        res.raise_for_status()
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
