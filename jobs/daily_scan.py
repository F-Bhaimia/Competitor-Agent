# jobs/daily_scan.py
import os
import csv
import hashlib
from datetime import datetime, UTC
from urllib.parse import urlsplit, urlunsplit
from collections import Counter

import pandas as pd

from app.crawl import crawl_all
from app.parse import parse_article

DATA_PATH = "data/updates.csv"

COLUMNS = [
    "id",            # deterministic hash of (company + normalized_url)
    "company",
    "source_url",
    "title",
    "published_at",
    "collected_at",
    "clean_text",
]

def ensure_headers(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)

def normalize_url(u: str) -> str:
    """
    Normalize URLs so the same page yields the same ID:
      - lower-case scheme/host
      - strip fragment and query
      - remove trailing slash (except root)
    """
    parts = urlsplit(u)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path.endswith("/") and path != "/":
        path = path[:-1]
    return urlunsplit((scheme, netloc, path, "", ""))

def make_id(company: str, url: str) -> str:
    base = f"{company}||{normalize_url(url)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def load_existing_ids(path: str) -> set:
    if not os.path.exists(path):
        return set()
    try:
        df = pd.read_csv(path)
    except Exception:
        return set()

    # If id column exists, use it; otherwise derive from company+url
    if "id" in df.columns:
        return set(df["id"].astype(str).tolist())

    # Backfill ids for legacy files (no id column)
    ids = set()
    for _, row in df.iterrows():
        comp = str(row.get("company", "") or "")
        url = str(row.get("source_url", "") or "")
        if comp and url:
            ids.add(make_id(comp, url))
    return ids

def get_previous_update_date(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, usecols=["collected_at"])
        if df.empty:
            return None
        # latest collected_at
        latest = pd.to_datetime(df["collected_at"], errors="coerce").max()
        if pd.isna(latest):
            return None
        return latest.strftime("%m%d%Y")
    except Exception:
        return None

def main():
    print("Daily scan job started at:", datetime.now())
    import os
    today_str = datetime.now().strftime("%m%d%Y")
    print("Starting daily scan...")
    print(f"  VERBOSE={os.getenv('VERBOSE','1')} USE_PLAYWRIGHT={os.getenv('USE_PLAYWRIGHT','1')} FILTER_COMPANY={os.getenv('FILTER_COMPANY')}")

    ensure_headers(DATA_PATH)

    existing_ids = load_existing_ids(DATA_PATH)
    seen_ids_this_run = set()
    new_rows = []
    new_counter = Counter()  # <-- counts new rows per company this run

    for page in crawl_all():
        rid = make_id(page.company, page.url)
        if rid in existing_ids or rid in seen_ids_this_run:
            continue

        art = parse_article(page.company, page.url, page.html)

        new_rows.append([
            rid,
            art.company,
            art.source_url,
            art.title,
            art.published_at or "",
            datetime.now(UTC).isoformat(),  # timezone-aware, replaces utcnow()
            art.clean_text,
        ])
        seen_ids_this_run.add(rid)
        new_counter[art.company] += 1

    if new_rows:
        # Append new rows
        with open(DATA_PATH, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(new_rows)

        # Keep a Parquet copy for analytics (best-effort)
        try:
            df_all = pd.read_csv(DATA_PATH)
            df_all.to_parquet("data/updates.parquet", index=False)
        except Exception:
            df_all = pd.read_csv(DATA_PATH)  # still load for summary if parquet failed

        print(f"✅ {len(new_rows)} new updates added as of {today_str}.")
    else:
        prev_str = get_previous_update_date(DATA_PATH) or "N/A"
        print(f"No new updates are found as of {today_str}. Here are the updates from {prev_str} (previous update).")
        # Load for summary if exists
        df_all = pd.read_csv(DATA_PATH) if os.path.exists(DATA_PATH) else pd.DataFrame(columns=COLUMNS)

    # ---- Per-run summary (new vs total) ----
    if not df_all.empty and "company" in df_all.columns:
        totals = df_all["company"].value_counts().to_dict()

        # Print compact summary (sorted by most new first, then by name)
        print("\nRun Summary")
        if new_counter:
            for company, added in sorted(new_counter.items(), key=lambda x: (-x[1], x[0])):
                total = totals.get(company, 0)
                print(f"  • {company}: +{added} new, {total} total")
        else:
            # No new items — still show top totals (up to 10)
            top = sorted(totals.items(), key=lambda x: (-x[1], x[0]))[:10]
            for company, total in top:
                print(f"  • {company}: {total} total")
    else:
        print("\nRun Summary\n  (no data yet)")

# --- keep this at the very end of the file ---
if __name__ == "__main__":
    from datetime import datetime, UTC
    print("__main__ guard hit at", datetime.now(UTC).isoformat(), flush=True)
    try:
        main()
    except Exception as e:
        import traceback
        print("Unhandled error:", repr(e))
        traceback.print_exc()