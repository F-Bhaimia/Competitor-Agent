# jobs/daily_scan.py
import os
import csv
import hashlib
import time
from datetime import datetime, UTC
from urllib.parse import urlsplit, urlunsplit
from collections import Counter

import pandas as pd

from app.crawl import crawl_all
from app.parse import parse_article
from app.logger import (
    get_system_logger,
    log_startup,
    log_scan_start,
    log_scan_progress,
    log_scan_complete,
    log_scan_error,
)

logger = get_system_logger(__name__)

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
    start_time = time.time()
    today_str = datetime.now().strftime("%m%d%Y")

    # Log startup
    log_startup("Daily Scan Job")
    logger.info(f"Environment: VERBOSE={os.getenv('VERBOSE','1')} "
                f"USE_PLAYWRIGHT={os.getenv('USE_PLAYWRIGHT','1')} "
                f"FILTER_COMPANY={os.getenv('FILTER_COMPANY', 'all')}")

    ensure_headers(DATA_PATH)

    existing_ids = load_existing_ids(DATA_PATH)
    seen_ids_this_run = set()
    new_rows = []
    new_counter = Counter()  # <-- counts new rows per company this run

    pages_processed = 0
    pages_skipped = 0

    for page in crawl_all():
        pages_processed += 1
        rid = make_id(page.company, page.url)

        if rid in existing_ids or rid in seen_ids_this_run:
            pages_skipped += 1
            logger.debug(f"[{page.company}] Skipped (duplicate): {page.url}")
            continue

        art = parse_article(page.company, page.url, page.html)

        # Log each new article found
        logger.debug(f"[{art.company}] NEW: {art.title[:60]}..." if len(art.title) > 60 else f"[{art.company}] NEW: {art.title}")
        logger.debug(f"  URL: {art.source_url}")
        logger.debug(f"  Published: {art.published_at or 'unknown'}")
        logger.debug(f"  Content length: {len(art.clean_text)} chars")

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

        # Periodic progress logging
        if len(new_rows) % 10 == 0:
            logger.info(f"Progress: {len(new_rows)} new articles found, {pages_processed} pages processed")

    logger.info(f"Crawl finished: {pages_processed} pages processed, {pages_skipped} skipped (duplicates)")

    # Calculate duration
    duration = time.time() - start_time

    if new_rows:
        # Append new rows
        with open(DATA_PATH, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(new_rows)
        logger.info(f"Appended {len(new_rows)} rows to {DATA_PATH}")

        # Keep a Parquet copy for analytics (best-effort)
        try:
            df_all = pd.read_csv(DATA_PATH)
            df_all.to_parquet("data/updates.parquet", index=False)
            logger.debug("Parquet mirror updated")
        except Exception as e:
            logger.warning(f"Failed to update parquet mirror: {e}")
            df_all = pd.read_csv(DATA_PATH)

        # Log completion
        log_scan_complete(
            total_articles=len(existing_ids) + len(new_rows),
            new_articles=len(new_rows),
            duration_seconds=duration
        )
        print(f"Scan complete: {len(new_rows)} new updates added as of {today_str}.")
    else:
        prev_str = get_previous_update_date(DATA_PATH) or "N/A"
        logger.info(f"No new updates found. Previous update: {prev_str}")
        print(f"No new updates found as of {today_str}. Previous update: {prev_str}.")
        df_all = pd.read_csv(DATA_PATH) if os.path.exists(DATA_PATH) else pd.DataFrame(columns=COLUMNS)
        log_scan_complete(total_articles=len(existing_ids), new_articles=0, duration_seconds=duration)

    # ---- Per-run summary (new vs total) ----
    if not df_all.empty and "company" in df_all.columns:
        totals = df_all["company"].value_counts().to_dict()

        # Log and print compact summary
        logger.info("Run Summary:")
        print("\nRun Summary")
        if new_counter:
            for company, added in sorted(new_counter.items(), key=lambda x: (-x[1], x[0])):
                total = totals.get(company, 0)
                logger.info(f"  {company}: +{added} new, {total} total")
                print(f"  {company}: +{added} new, {total} total")
        else:
            top = sorted(totals.items(), key=lambda x: (-x[1], x[0]))[:10]
            for company, total in top:
                logger.info(f"  {company}: {total} total")
                print(f"  {company}: {total} total")
    else:
        logger.info("Run Summary: (no data yet)")
        print("\nRun Summary\n  (no data yet)")

# --- keep this at the very end of the file ---
if __name__ == "__main__":
    logger.debug(f"__main__ guard hit at {datetime.now(UTC).isoformat()}")
    try:
        main()
    except Exception as e:
        logger.exception(f"Unhandled error in daily_scan: {e}")
        raise