# jobs/process_emails.py
"""
Process received newsletter emails and add them to updates.csv.

This job:
1. Reads email JSON files from data/emails/
2. Extracts content and matches to competitors
3. Adds new entries to updates.csv (same format as crawled articles)
4. Moves processed emails to data/emails/processed/

Run with: python -m jobs.process_emails
"""

import csv
import hashlib
import json
import os
import re
import shutil
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional
from html.parser import HTMLParser

import yaml
import pandas as pd

from app.logger import get_system_logger, log_user_action

logger = get_system_logger("process_emails")

# Paths
EMAILS_DIR = Path("data/emails")
PROCESSED_DIR = EMAILS_DIR / "processed"
CONFIG_PATH = Path("config/monitors.yaml")
DATA_PATH = Path("data/updates.csv")

COLUMNS = [
    "id",
    "company",
    "source_url",
    "title",
    "published_at",
    "collected_at",
    "clean_text",
]


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML content."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_tags = {"script", "style", "head", "meta", "link"}
        self.current_skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.current_skip = True

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags:
            self.current_skip = False

    def handle_data(self, data):
        if not self.current_skip:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    if not html:
        return ""
    try:
        parser = HTMLTextExtractor()
        parser.feed(html)
        return parser.get_text()
    except Exception:
        # Fallback: strip tags with regex
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not CONFIG_PATH.exists():
        return {"competitors": []}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"competitors": []}


def load_existing_ids() -> set:
    """Load existing IDs from updates.csv to avoid duplicates."""
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
    """Ensure updates.csv exists with proper headers."""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        with open(DATA_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)


def make_id(company: str, message_id: str) -> str:
    """Generate deterministic ID for an email."""
    base = f"{company}||email||{message_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def match_competitor(from_addr: str, subject: str, config: Dict) -> Optional[str]:
    """
    Try to match an email to a competitor based on sender or subject.

    Returns the competitor name if matched, None otherwise.
    """
    competitors = config.get("competitors", [])

    from_lower = from_addr.lower()
    subject_lower = subject.lower()

    for comp in competitors:
        name = comp.get("name", "")
        if not name:
            continue

        # Extract keywords from competitor name
        keywords = name.lower().replace("(", " ").replace(")", " ").split()

        # Check if any keyword appears in from address or subject
        for keyword in keywords:
            if len(keyword) > 2:  # Skip short words
                if keyword in from_lower or keyword in subject_lower:
                    return name

        # Also check start_urls domains
        for url in comp.get("start_urls", []):
            # Extract domain from URL
            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if domain_match:
                domain = domain_match.group(1).lower()
                domain_name = domain.split(".")[0]
                if domain_name in from_lower:
                    return name

    return None


def extract_email_content(payload: Dict) -> Dict[str, Any]:
    """Extract relevant content from CloudMailin email payload."""
    headers = payload.get("headers", {})
    envelope = payload.get("envelope", {})

    # Get subject (try various header formats)
    subject = (
        headers.get("subject") or
        headers.get("Subject") or
        "(No Subject)"
    )

    # Get from address
    from_addr = envelope.get("from", "")
    if not from_addr:
        from_addr = headers.get("from") or headers.get("From") or "unknown"

    # Get message ID for deduplication
    message_id = (
        headers.get("message_id") or
        headers.get("Message-ID") or
        headers.get("Message-Id") or
        payload.get("_webhook_metadata", {}).get("received_at", "")
    )

    # Get date
    date_str = headers.get("date") or headers.get("Date") or ""
    published_at = None
    if date_str:
        try:
            from email.utils import parsedate_to_datetime
            published_at = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            pass

    # Get body content - prefer plain text, fall back to HTML
    plain_text = payload.get("plain", "") or ""
    html_content = payload.get("html", "") or ""

    if plain_text.strip():
        body = plain_text
    elif html_content.strip():
        body = html_to_text(html_content)
    else:
        body = ""

    # Clean up body text
    body = re.sub(r"\s+", " ", body).strip()

    return {
        "subject": subject,
        "from": from_addr,
        "message_id": message_id,
        "published_at": published_at,
        "body": body,
    }


def process_email_file(filepath: Path, config: Dict, existing_ids: set) -> Optional[Dict]:
    """
    Process a single email JSON file.

    Returns a row dict for updates.csv, or None if should be skipped.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {filepath}: {e}")
        return None

    # Extract content
    content = extract_email_content(payload)

    # Try to match to a competitor
    company = match_competitor(content["from"], content["subject"], config)

    if not company:
        # If no competitor match, use a generic label
        company = "Newsletter (Unmatched)"

    # Generate ID
    row_id = make_id(company, content["message_id"])

    # Check for duplicates
    if row_id in existing_ids:
        logger.debug(f"Skipping duplicate email: {content['subject']}")
        return None

    # Create source URL from message ID or filename
    source_url = f"email://{filepath.stem}"

    return {
        "id": row_id,
        "company": company,
        "source_url": source_url,
        "title": content["subject"],
        "published_at": content["published_at"] or "",
        "collected_at": datetime.now(UTC).isoformat(),
        "clean_text": content["body"],
        "filename": filepath.name,  # For tracking which file was processed
    }


def main():
    """Process all unprocessed email files."""
    logger.info("Starting email processing job")

    # Ensure directories exist
    EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ensure_csv_headers()

    # Load config and existing IDs
    config = load_config()
    existing_ids = load_existing_ids()

    # Find email files to process
    email_files = list(EMAILS_DIR.glob("*.json"))

    if not email_files:
        logger.info("No email files to process")
        print("No email files to process.")
        return

    logger.info(f"Found {len(email_files)} email files to process")

    new_rows = []
    processed_files = []

    for filepath in email_files:
        result = process_email_file(filepath, config, existing_ids)

        if result:
            filename = result.pop("filename")  # Remove filename from row
            new_rows.append(result)
            processed_files.append((filepath, filename))
            existing_ids.add(result["id"])  # Prevent duplicates within run

            logger.info(f"Processed: {result['title'][:50]}... -> {result['company']}")
        else:
            # Move unmatched/duplicate to processed anyway
            processed_files.append((filepath, filepath.name))

    # Append new rows to CSV
    if new_rows:
        with open(DATA_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            for row in new_rows:
                writer.writerow(row)

        logger.info(f"Added {len(new_rows)} newsletter articles to {DATA_PATH}")

        # Update parquet mirror
        try:
            df = pd.read_csv(DATA_PATH)
            df.to_parquet("data/updates.parquet", index=False)
            logger.debug("Parquet mirror updated")
        except Exception as e:
            logger.warning(f"Failed to update parquet: {e}")

    # Move processed files
    for filepath, filename in processed_files:
        try:
            dest = PROCESSED_DIR / filename
            shutil.move(str(filepath), str(dest))
            logger.debug(f"Moved {filename} to processed/")
        except Exception as e:
            logger.warning(f"Failed to move {filename}: {e}")

    # Summary
    print(f"\nEmail Processing Complete")
    print(f"  Files processed: {len(processed_files)}")
    print(f"  New articles added: {len(new_rows)}")

    if new_rows:
        print("\nNewly added articles:")
        for row in new_rows:
            print(f"  [{row['company']}] {row['title'][:60]}")

    log_user_action("process_emails", "completed", f"Processed {len(processed_files)} files, added {len(new_rows)} articles")


if __name__ == "__main__":
    main()
