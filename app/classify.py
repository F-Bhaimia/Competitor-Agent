# app/classify.py
import json
from pathlib import Path
from typing import Dict, Any, List

import yaml
from openai import OpenAI
from dotenv import load_dotenv

# Load .env if present
load_dotenv(override=False)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "monitors.yaml"

# Default categories if not configured
DEFAULT_CATEGORIES = [
    "Product/Feature", "Pricing/Plans", "Partnership", "Acquisition/Investment",
    "Case Study/Customer", "Events/Webinar", "Best Practices/Guides",
    "Security/Compliance", "Hiring/Leadership", "Company News", "Other"
]

DEFAULT_IMPACT_RULES = {
    "high": ["pricing change", "major feature GA", "acquisitions", "big partnerships", "security incidents"],
    "medium": ["meaningful feature update", "big case study", "notable event announcements"],
    "low": ["generic tips", "routine posts"]
}

DEFAULT_INDUSTRY = "membership/club management software"


def _load_classification_config() -> Dict[str, Any]:
    """Load classification settings from config file."""
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return config.get("classification", {})
    except Exception:
        pass
    return {}


def get_categories() -> List[str]:
    """Get categories from config or defaults."""
    config = _load_classification_config()
    categories = config.get("categories", DEFAULT_CATEGORIES)
    # Ensure "Other" is always present as fallback
    if "Other" not in categories:
        categories.append("Other")
    return categories


def get_impact_rules() -> Dict[str, List[str]]:
    """Get impact classification rules from config or defaults."""
    config = _load_classification_config()
    return config.get("impact_rules", DEFAULT_IMPACT_RULES)


def get_industry_context() -> str:
    """Get industry context for AI prompt."""
    config = _load_classification_config()
    return config.get("industry_context", DEFAULT_INDUSTRY)


def _build_system_prompt() -> str:
    """Build the system prompt from configuration."""
    categories = get_categories()
    impact_rules = get_impact_rules()
    industry = get_industry_context()

    high_rules = ", ".join(impact_rules.get("high", []))
    medium_rules = ", ".join(impact_rules.get("medium", []))
    low_rules = ", ".join(impact_rules.get("low", []))

    return (
        "You are a precise analyst. Given a competitor blog/news post, return:\n"
        "- 'summary': 40–80 words, plain text.\n"
        f"- 'category': one of {', '.join([repr(c) for c in categories])}.\n"
        f"- 'impact': High, Medium, or Low for a {industry} competitor.\n"
        "Impact guidance:\n"
        f"High = {high_rules}.\n"
        f"Medium = {medium_rules}.\n"
        f"Low = {low_rules}.\n"
        "Return ONLY valid JSON with keys: summary, category, impact."
    )


CLIENT = None
def _client():
    global CLIENT
    if CLIENT is None:
        CLIENT = OpenAI()  # reads OPENAI_API_KEY from env
    return CLIENT


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

    categories = get_categories()
    system_prompt = _build_system_prompt()

    try:
        client = _client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
        )
        raw = resp.choices[0].message.content
        data = json.loads(raw or "{}")
        summary = str(data.get("summary", "")).strip()
        category = str(data.get("category", "Other")).strip()
        impact = str(data.get("impact", "")).strip().title()

        if category not in categories:
            category = "Other"
        if impact not in {"High", "Medium", "Low"}:
            impact = "Low"

        return {"summary": summary, "category": category, "impact": impact}
    except Exception:
        # Best-effort fallback so pipeline never crashes
        return {"summary": "", "category": "Other", "impact": "Low"}


# Export for external use
CATEGORIES = get_categories()
