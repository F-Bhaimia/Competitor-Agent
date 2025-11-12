# app/classify.py
import os
import json
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Load .env if present
load_dotenv(override=False)

CLIENT = None
def _client():
    global CLIENT
    if CLIENT is None:
        CLIENT = OpenAI()  # reads OPENAI_API_KEY from env
    return CLIENT

# Keep categories tight so charts look good
CATEGORIES = [
    "Product/Feature", "Pricing/Plans", "Partnership", "Acquisition/Investment",
    "Case Study/Customer", "Events/Webinar", "Best Practices/Guides",
    "Security/Compliance", "Hiring/Leadership", "Company News", "Other"
]

SYSTEM = (
    "You are a precise analyst. Given a competitor blog/news post, return:\n"
    "- 'summary': 40–80 words, plain text.\n"
    "- 'category': one of " + ", ".join([repr(c) for c in CATEGORIES]) + ".\n"
    "- 'impact': High, Medium, or Low for a membership/club management software competitor.\n"
    "Impact guidance:\n"
    "High = pricing change, major feature GA, acquisitions, big partnerships, security incidents.\n"
    "Medium = meaningful feature update, big case study, notable event announcements.\n"
    "Low = generic tips, routine posts.\n"
    "Return ONLY valid JSON with keys: summary, category, impact."
)

def _truncate(txt: str, max_chars: int = 4000) -> str:
    txt = (txt or "").strip()
    return txt[:max_chars]

def classify_article(company: str, title: str, body: str) -> Dict[str, Any]:
    """
    Returns dict: {'summary': str, 'category': str, 'impact': 'High'|'Medium'|'Low'}
    Falls back to defaults if API fails.
    """
    title = (title or "").strip()
    body = _truncate(body or "")

    if not body and not title:
        return {"summary": "", "category": "Other", "impact": "Low"}

    prompt = (
        f"Company: {company or 'Unknown'}\n"
        f"Title: {title}\n\n"
        f"Body:\n{body}\n\n"
        "Respond in JSON."
    )

    try:
        client = _client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # small, fast, good enough
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt}
            ],
            response_format={ "type": "json_object" },
            max_tokens=400,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw or "{}")
        summary = str(data.get("summary", "")).strip()
        category = str(data.get("category", "Other")).strip()
        impact = str(data.get("impact", "")).strip().title()

        if category not in CATEGORIES:
            category = "Other"
        if impact not in {"High","Medium","Low"}:
            impact = "Low"

        return {"summary": summary, "category": category, "impact": impact}
    except Exception as e:
        # Best-effort fallback so pipeline never crashes
        return {"summary": "", "category": "Other", "impact": "Low"}
