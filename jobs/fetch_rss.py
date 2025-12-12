# jobs/fetch_rss.py
import argparse, os, sys, time
from datetime import datetime, timezone
import pandas as pd
import feedparser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DEFAULT = os.path.join(DATA_DIR, "updates.csv")

# ——— Your competitor set ———
COMPETITORS = [
    ("Mindbody", "https://news.google.com/rss/search?q=Mindbody&hl=en-US&gl=US&ceid=US:en"),
    ("Glofox",   "https://news.google.com/rss/search?q=Glofox&hl=en-US&gl=US&ceid=US:en"),
    ("Wodify",   "https://news.google.com/rss/search?q=Wodify&hl=en-US&gl=US&ceid=US:en"),
    # ("Zen Planner", "..."),
    # ("ClubReady",   "..."),
]

def parse_pubdate(entry):
    # Try updated/ published; fallback to now
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)

def main():
    parser = argparse.ArgumentParser(description="Fetch competitor RSS into updates.csv")
    parser.add_argument("--since", type=str, required=True, help="YYYY-MM-DD (UTC)")
    parser.add_argument("--out", type=str, default=OUT_DEFAULT)
    args = parser.parse_args()

    since_date = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    rows = []

    for company, url in COMPETITORS:
        feed = feedparser.parse(url)
        for e in feed.entries:
            pub = parse_pubdate(e)
            if pub < since_date:
                continue
            title = e.get("title", "").strip()
            link = e.get("link", "").strip()
            summary = (e.get("summary") or e.get("description") or "").strip()
            # clean_text is what enrich uses if available; fallback to summary.
            clean_text = summary
            rows.append({
                "company": company,
                "title": title,
                "source_url": link,
                "clean_text": clean_text,
                "published_at": pub.isoformat(),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    new_df = pd.DataFrame(rows)
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(args.out):
        cur = pd.read_csv(args.out)
        merged = pd.concat([cur, new_df], ignore_index=True)
    else:
        merged = new_df

    # dedupe best-effort (company + source_url)
    if not merged.empty and {"company","source_url"} <= set(merged.columns):
        merged = merged.drop_duplicates(subset=["company","source_url"], keep="first")

    merged.to_csv(args.out, index=False, encoding="utf-8")
    print(f"[fetch_rss] wrote {len(merged)} rows to {args.out} "
          f"(added {len(new_df)} new since {args.since})")

if __name__ == "__main__":
    main()