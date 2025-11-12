# app/parse.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
import json
import re

@dataclass
class Article:
    company: str
    source_url: str
    title: str
    published_at: Optional[str]
    clean_text: str

def _normalize_date(value: str) -> Optional[str]:
    try:
        dt = dateparser.parse(value)
        return dt.isoformat() if dt else None
    except Exception:
        return None

def _extract_json_ld_date(soup: BeautifulSoup) -> Optional[str]:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            text = tag.string or ""
            if not text.strip():
                continue
            data = json.loads(text)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key in ("datePublished", "dateCreated", "dateModified", "uploadDate"):
                    if key in item:
                        return _normalize_date(item[key])
        except Exception:
            continue
    return None

def _extract_og_date(soup: BeautifulSoup) -> Optional[str]:
    og = soup.find("meta", attrs={"property": "article:published_time"})
    if og and og.get("content"):
        return _normalize_date(og["content"])
    return None

def _extract_title(soup: BeautifulSoup) -> str:
    ogt = soup.find("meta", attrs={"property": "og:title"})
    if ogt and ogt.get("content"):
        return ogt["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(" ", strip=True) if h1 else "Untitled"

def _extract_body_text(soup: BeautifulSoup) -> str:
    # Prefer semantic containers
    for selector in ("article", "main"):
        el = soup.find(selector)
        if el:
            return el.get_text("\n", strip=True)
    # Fallback: whole page text
    return soup.get_text("\n", strip=True)

def parse_article(company: str, url: str, html: str):
    """
    Parse raw HTML into a structured Article (title, date, clean_text).
    """
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    date = _extract_json_ld_date(soup) or _extract_og_date(soup)
    text = _extract_body_text(soup)
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse extra newlines
    return Article(
        company=company,
        source_url=url,
        title=title,
        published_at=date,
        clean_text=text,
    )
