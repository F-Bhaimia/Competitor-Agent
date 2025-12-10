# jobs/process_emails.py
"""
Batch process received newsletter emails through the full pipeline.

This job:
1. Reads email JSON files from data/emails/
2. Runs each through the 4-stage pipeline:
   - RECEIVED: Log to emails.csv
   - MATCHED: AI matches to competitor
   - QUALIFIED: AI quality gate (accept/reject)
   - INJECTED: Add to updates.csv
3. Moves processed emails to data/emails/processed/

Run with: python -m jobs.process_emails
"""

import json
import shutil
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, Optional
import csv

import pandas as pd

from app.logger import (
    get_system_logger,
    log_user_action,
)
from app.email_matcher import (
    match_email_to_competitor,
    check_email_quality,
    record_email_received,
    record_email_matched,
    record_email_injected,
    email_exists,
)

logger = get_system_logger("process_emails")

# Paths
EMAILS_DIR = Path("data/emails")
PROCESSED_DIR = EMAILS_DIR / "processed"
DATA_PATH = Path("data/updates.csv")

COLUMNS = ["id", "company", "source_url", "title", "published_at", "collected_at", "clean_text"]


def extract_plain_text(payload: Dict) -> str:
    """Extract plain text from email payload."""
    import re
    from html.parser import HTMLParser

    plain = payload.get("plain", "") or ""
    if plain.strip():
        return re.sub(r"\s+", " ", plain).strip()

    # Fallback to HTML stripping
    html = payload.get("html", "") or ""
    if html:
        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []

            def handle_data(self, data):
                self.text_parts.append(data.strip())

            def get_text(self):
                return " ".join(self.text_parts)

        try:
            parser = TextExtractor()
            parser.feed(html)
            return re.sub(r"\s+", " ", parser.get_text()).strip()
        except Exception:
            pass

    return ""


def make_id(company: str, message_id: str) -> str:
    """Generate deterministic ID for an email."""
    import hashlib
    base = f"{company}||email||{message_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def load_existing_ids() -> set:
    """Load existing IDs from updates.csv."""
    if not DATA_PATH.exists():
        return set()
    try:
        df = pd.read_csv(DATA_PATH)
        if "id" in df.columns:
            return set(df["id"].astype(str).tolist())
    except Exception:
        pass
    return set()


def ensure_csv_headers():
    """Ensure updates.csv exists with headers."""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        with open(DATA_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)


def process_single_email(filepath: Path, existing_ids: set) -> Optional[Dict]:
    """
    Process a single email through the full pipeline.

    Returns row dict if injected, None otherwise.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return None

    headers = payload.get("headers", {})
    envelope = payload.get("envelope", {})

    # Extract fields
    subject = headers.get("subject") or headers.get("Subject") or "(No Subject)"
    from_addr = envelope.get("from", "") or headers.get("from") or headers.get("From") or "unknown"
    to_addr = envelope.get("to", "") or headers.get("to") or headers.get("To") or "unknown"
    message_id = (
        headers.get("message_id") or headers.get("Message-ID") or headers.get("Message-Id") or
        payload.get("_webhook_metadata", {}).get("received_at", filepath.stem)
    )

    date_str = headers.get("date") or headers.get("Date") or ""
    published_at = None
    if date_str:
        try:
            from email.utils import parsedate_to_datetime
            published_at = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            pass

    body = extract_plain_text(payload)

    # Check if already processed
    if email_exists(filepath.name):
        logger.debug(f"Already processed: {filepath.name}")
        return None

    # STAGE 1: Record received
    record_email_received(
        json_file=filepath.name,
        from_address=from_addr,
        to_address=to_addr,
        date=date_str,
        subject=subject,
    )
    logger.info(f"[RECEIVED] {subject[:50]}")

    # STAGE 2: AI matching
    company = match_email_to_competitor(from_addr, subject, body)
    if not company:
        logger.info(f"[NO MATCH] {subject[:50]} - no competitor matched")
        return None

    record_email_matched(filepath.name, from_addr, company)
    logger.info(f"[MATCHED] {subject[:50]} -> {company}")

    # STAGE 3: Quality gate
    if not check_email_quality(from_addr, subject, body):
        logger.info(f"[REJECTED] {subject[:50]} - failed quality gate")
        return None

    logger.info(f"[QUALIFIED] {subject[:50]} - passed quality gate")

    # Check for duplicates
    row_id = make_id(company, message_id)
    if row_id in existing_ids:
        logger.debug(f"[DUPLICATE] {subject[:50]}")
        return None

    # STAGE 4: Inject
    row = {
        "id": row_id,
        "company": company,
        "source_url": f"email://{filepath.stem}",
        "title": subject,
        "published_at": published_at or "",
        "collected_at": datetime.now(UTC).isoformat(),
        "clean_text": body,
    }

    record_email_injected(filepath.name, from_addr)
    logger.info(f"[INJECTED] {subject[:50]} -> updates.csv")

    return row


def main():
    """Process all unprocessed email files."""
    start_time = time.time()

    EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ensure_csv_headers()

    existing_ids = load_existing_ids()
    email_files = list(EMAILS_DIR.glob("*.json"))

    if not email_files:
        print("No email files to process.")
        return

    print(f"\nProcessing {len(email_files)} email(s)...\n")

    injected_rows = []
    processed_files = []

    for filepath in email_files:
        print(f"--- {filepath.name} ---")
        row = process_single_email(filepath, existing_ids)

        if row:
            injected_rows.append(row)
            existing_ids.add(row["id"])

        processed_files.append(filepath)

    # Write injected rows to CSV
    if injected_rows:
        with open(DATA_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            for row in injected_rows:
                writer.writerow(row)

        # Update parquet
        try:
            df = pd.read_csv(DATA_PATH)
            df.to_parquet("data/updates.parquet", index=False)
        except Exception as e:
            logger.warning(f"Failed to update parquet: {e}")

    # Move all processed files
    for filepath in processed_files:
        try:
            dest = PROCESSED_DIR / filepath.name
            shutil.move(str(filepath), str(dest))
        except Exception as e:
            logger.warning(f"Failed to move {filepath.name}: {e}")

    duration = time.time() - start_time

    print(f"\n{'='*50}")
    print(f"Processing Complete")
    print(f"  Files processed: {len(processed_files)}")
    print(f"  Injected to pipeline: {len(injected_rows)}")
    print(f"  Duration: {duration:.1f}s")
    print(f"{'='*50}")

    if injected_rows:
        print("\nInjected articles:")
        for row in injected_rows:
            print(f"  [{row['company']}] {row['title'][:60]}")

    log_user_action("process_emails", "batch_complete", f"{len(processed_files)} processed, {len(injected_rows)} injected")


if __name__ == "__main__":
    main()
