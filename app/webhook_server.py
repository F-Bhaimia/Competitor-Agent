# app/webhook_server.py
"""
FastAPI webhook server for receiving newsletter emails from CloudMailin.

Run with: python -m app.webhook_server
Or use the start script: start_webhook.bat (Windows) / start_webhook.sh (Linux)

The server listens on /email for POST requests from CloudMailin,
saves the full email JSON to data/emails/, and immediately processes
it into updates.csv for competitor analysis.
"""

import csv
import json
import os
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from app.logger import (
    get_system_logger,
    log_user_action,
    log_webhook_startup,
    log_email_received,
    log_email_error,
    log_email_processed,
)

logger = get_system_logger("webhook")

# Paths
CONFIG_PATH = Path("config/monitors.yaml")
EMAILS_DIR = Path("data/emails")
PROCESSED_DIR = EMAILS_DIR / "processed"
DATA_PATH = Path("data/updates.csv")

# CSV columns for updates.csv
COLUMNS = ["id", "company", "source_url", "title", "published_at", "collected_at", "clean_text"]

app = FastAPI(
    title="Competitor Agent Webhook",
    description="Receives newsletter emails from CloudMailin",
    version="1.0.0",
    redirect_slashes=True,  # Handle /email and /email/ the same way
)


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not CONFIG_PATH.exists():
        return {"global": {"webhook_port": 8001, "webhook_host": "0.0.0.0"}}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sanitize_filename(s: str) -> str:
    """Remove unsafe characters from filename."""
    # Replace unsafe chars with underscore
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', s)[:100]


def ensure_emails_dir():
    """Ensure the emails directory exists."""
    EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def ensure_csv_headers():
    """Ensure updates.csv exists with proper headers."""
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        with open(DATA_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(COLUMNS)


def make_id(company: str, message_id: str) -> str:
    """Generate deterministic ID for an email."""
    import hashlib
    base = f"{company}||email||{message_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


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


def match_competitor(from_addr: str, subject: str, body: str, config: Dict) -> Optional[str]:
    """Match an email to a competitor based on sender, subject, or body content."""
    competitors = config.get("competitors", [])

    from_lower = from_addr.lower()
    subject_lower = subject.lower()
    body_lower = body.lower()[:1000]  # First 1000 chars of body

    for comp in competitors:
        name = comp.get("name", "")
        if not name:
            continue

        # Extract keywords from competitor name
        keywords = name.lower().replace("(", " ").replace(")", " ").split()

        # Check if any keyword appears in from address, subject, or body
        for keyword in keywords:
            if len(keyword) > 2:  # Skip short words
                if keyword in from_lower or keyword in subject_lower or keyword in body_lower:
                    return name

        # Also check start_urls domains
        for url in comp.get("start_urls", []):
            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", url)
            if domain_match:
                domain_name = domain_match.group(1).split(".")[0].lower()
                if len(domain_name) > 2 and domain_name in from_lower:
                    return name

    return None


def extract_plain_text(payload: Dict) -> str:
    """Extract plain text from email payload."""
    plain = payload.get("plain", "") or ""
    if plain.strip():
        return re.sub(r"\s+", " ", plain).strip()

    # Fallback to HTML stripping
    html = payload.get("html", "") or ""
    if html:
        from html.parser import HTMLParser

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


def process_email_immediately(filepath: Path, payload: Dict, config: Dict) -> Optional[Dict]:
    """
    Process a single email immediately after receipt.
    Returns the row dict if added to updates.csv, None if skipped.
    """
    existing_ids = load_existing_ids()

    headers = payload.get("headers", {})
    envelope = payload.get("envelope", {})

    # Extract fields
    subject = headers.get("subject") or headers.get("Subject") or "(No Subject)"
    from_addr = envelope.get("from", "") or headers.get("from") or headers.get("From") or "unknown"
    message_id = (
        headers.get("message_id") or headers.get("Message-ID") or headers.get("Message-Id") or
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

    # Extract body
    body = extract_plain_text(payload)

    # Match to competitor
    company = match_competitor(from_addr, subject, body, config)
    if not company:
        company = "Newsletter (Unmatched)"

    # Generate ID
    row_id = make_id(company, message_id)

    # Check for duplicates
    if row_id in existing_ids:
        logger.debug(f"Skipping duplicate email: {subject}")
        return None

    # Create row
    row = {
        "id": row_id,
        "company": company,
        "source_url": f"email://{filepath.stem}",
        "title": subject,
        "published_at": published_at or "",
        "collected_at": datetime.now(UTC).isoformat(),
        "clean_text": body,
    }

    # Ensure CSV exists
    ensure_csv_headers()

    # Append to CSV
    with open(DATA_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)

    # Update parquet mirror
    try:
        df = pd.read_csv(DATA_PATH)
        df.to_parquet("data/updates.parquet", index=False)
    except Exception as e:
        logger.warning(f"Failed to update parquet: {e}")

    # Move to processed
    try:
        dest = PROCESSED_DIR / filepath.name
        filepath.rename(dest)
        logger.debug(f"Moved {filepath.name} to processed/")
    except Exception as e:
        logger.warning(f"Failed to move {filepath.name}: {e}")

    return row


@app.on_event("startup")
async def startup_event():
    """Initialize on server startup."""
    ensure_emails_dir()
    logger.info(f"Webhook server started. Emails will be saved to {EMAILS_DIR.absolute()}")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "Competitor Agent Webhook", "endpoint": "/email"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "emails_dir": str(EMAILS_DIR.absolute())}


@app.post("/email")
async def receive_email(request: Request):
    """
    Receive email webhook from CloudMailin.

    CloudMailin sends emails as JSON POST with the following structure:
    - headers: email headers
    - envelope: from/to info
    - plain: plain text body
    - html: HTML body
    - attachments: list of attachments
    - And more...

    We save the entire payload to data/emails/[message-id]-[timestamp].json
    """
    try:
        # Get the raw JSON payload
        payload = await request.json()

        # Extract message ID if available
        headers = payload.get("headers", {})
        message_id = headers.get("message_id") or headers.get("Message-ID") or headers.get("Message-Id", "")

        # Clean message ID for filename
        if message_id:
            # Remove angle brackets and sanitize
            message_id = message_id.strip("<>").replace("@", "_at_")
            message_id = sanitize_filename(message_id)
        else:
            message_id = "unknown"

        # Generate timestamp
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")

        # Create filename
        filename = f"{message_id}-{timestamp}.json"
        filepath = EMAILS_DIR / filename

        # Add metadata to payload
        payload["_webhook_metadata"] = {
            "received_at": datetime.now(UTC).isoformat(),
            "source_ip": request.client.host if request.client else "unknown",
            "filename": filename,
        }

        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False, default=str)

        # Get file size for logging
        file_size = filepath.stat().st_size

        # Log the receipt with detailed info
        subject = headers.get("subject") or headers.get("Subject", "(no subject)")
        from_addr = payload.get("envelope", {}).get("from", "unknown")

        log_email_received(from_addr, subject, filename, file_size)
        logger.debug(f"Saved to: {filepath}")

        # Immediately process into updates.csv
        config = load_config()
        result = process_email_immediately(filepath, payload, config)

        if result:
            log_email_processed(filename, result["company"], result["title"])
            log_user_action("webhook", "email_processed", f"[{result['company']}] {subject}")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Email received, processed, and added to updates",
                    "filename": filename,
                    "company": result["company"],
                    "added_to_updates": True,
                }
            )
        else:
            log_user_action("webhook", "email_received", f"From: {from_addr}, Subject: {subject} (duplicate, skipped)")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Email received but skipped (duplicate)",
                    "filename": filename,
                    "added_to_updates": False,
                }
            )

    except json.JSONDecodeError as e:
        log_email_error("Invalid JSON payload", details=str(e))
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    except Exception as e:
        log_email_error("Webhook processing failed", details=str(e))
        logger.exception(f"Error processing email webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.get("/emails")
async def list_emails(limit: int = 20):
    """List recently received emails."""
    ensure_emails_dir()

    files = sorted(EMAILS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    emails = []
    for f in files[:limit]:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                headers = data.get("headers", {})
                emails.append({
                    "filename": f.name,
                    "subject": headers.get("subject") or headers.get("Subject", "(no subject)"),
                    "from": data.get("envelope", {}).get("from", "unknown"),
                    "received_at": data.get("_webhook_metadata", {}).get("received_at", "unknown"),
                })
        except Exception:
            emails.append({"filename": f.name, "error": "Could not parse"})

    return {"count": len(files), "emails": emails}


def main():
    """Run the webhook server."""
    config = load_config()
    global_cfg = config.get("global", {})

    host = global_cfg.get("webhook_host", "0.0.0.0")
    port = int(global_cfg.get("webhook_port", 8001))

    # Log startup with standard format
    log_webhook_startup(host, port)

    print(f"\n{'='*60}")
    print(f"  Competitor Agent Webhook Server")
    print(f"  Listening on: http://{host}:{port}")
    print(f"  Webhook endpoint: POST /email")
    print(f"  Health check: GET /health")
    print(f"  List emails: GET /emails")
    print(f"{'='*60}\n")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
