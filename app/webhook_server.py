# app/webhook_server.py
"""
FastAPI webhook server for receiving newsletter emails from CloudMailin.

Run with: python -m app.webhook_server
Or use the start script: start_webhook.bat (Windows) / start_webhook.sh (Linux)

The server listens on /email for POST requests from CloudMailin
and saves the full email JSON to data/emails/
"""

import json
import os
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

from app.logger import get_system_logger, log_user_action

logger = get_system_logger("webhook")

# Paths
CONFIG_PATH = Path("config/monitors.yaml")
EMAILS_DIR = Path("data/emails")

app = FastAPI(
    title="Competitor Agent Webhook",
    description="Receives newsletter emails from CloudMailin",
    version="1.0.0"
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

        # Log the receipt
        subject = headers.get("subject") or headers.get("Subject", "(no subject)")
        from_addr = payload.get("envelope", {}).get("from", "unknown")

        logger.info(f"Received email: '{subject}' from {from_addr}")
        logger.debug(f"Saved to: {filepath}")
        log_user_action("webhook", "email_received", f"From: {from_addr}, Subject: {subject}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Email received and saved",
                "filename": filename,
            }
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    except Exception as e:
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

    logger.info(f"Starting webhook server on {host}:{port}")
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
