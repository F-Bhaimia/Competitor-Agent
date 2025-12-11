# app/email_matcher.py
"""
AI-powered email-to-competitor matching and tracking.

Maintains two CSV files:
- emails.csv: One row per email received (unique by json_file)
- email_senders.csv: Aggregated stats per unique sender address

Pipeline stages:
1. RECEIVED - Email logged
2. MATCHED - AI identified competitor
3. QUALIFIED - AI determined email has value (quality gate)
4. INJECTED - Added to updates.csv
"""

import csv
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

from app.logger import get_system_logger

load_dotenv(override=False)

logger = get_system_logger("email_matcher")

CONFIG_PATH = Path("config/monitors.yaml")
EMAILS_CSV = Path("data/emails.csv")
SENDERS_CSV = Path("data/email_senders.csv")

# OpenAI client singleton
_openai_client = None

def _get_openai_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client

# CSV columns for emails.csv - one row per email
EMAIL_COLUMNS = [
    "json_file",        # Unique identifier (filename)
    "from_address",     # Sender email
    "to_address",       # Recipient
    "date",             # Email date header
    "subject",          # Subject line
    "matched_company",  # Competitor matched (or "unmatched")
    "injected",         # Whether added to updates.csv (True/False)
    "received_at",      # Timestamp when webhook received
    "processed_at",     # Timestamp when AI matching completed
    "status",           # Email status: "inbox" or "deleted"
]

# CSV columns for email_senders.csv - one row per unique sender
SENDER_COLUMNS = [
    "from_address",      # Unique key
    "emails_received",   # Total emails from this sender
    "emails_processed",  # Emails that matched a competitor
    "emails_injected",   # Emails added to updates.csv
    "assigned_company",  # Manual override for auto-matching
    "last_seen",         # Last email timestamp
]


def _load_config() -> Dict[str, Any]:
    """Load full config from YAML file."""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_competitors() -> List[Dict[str, Any]]:
    """Load competitor list from config."""
    return _load_config().get("competitors", [])


def _get_prompt(prompt_name: str) -> Dict[str, str]:
    """
    Get a prompt from config by name.
    Returns dict with 'system' and 'user' keys.
    """
    config = _load_config()
    prompts = config.get("prompts", {})
    prompt = prompts.get(prompt_name, {})

    # Defaults if not configured
    defaults = {
        "email_match": {
            "system": "You match emails to companies. Respond only with a company name or NONE.",
            "user": "Match this email to a competitor: {from_address} - {subject}"
        },
        "email_quality": {
            "system": "You filter emails for a competitive intelligence system. Respond only with ACCEPT or REJECT.",
            "user": "Should this email be processed? From: {from_address}, Subject: {subject}"
        }
    }

    return {
        "system": prompt.get("system", defaults.get(prompt_name, {}).get("system", "")),
        "user": prompt.get("user", defaults.get(prompt_name, {}).get("user", ""))
    }


def get_competitor_names() -> List[str]:
    """Get list of competitor names from config."""
    competitors = load_competitors()
    return [c.get("name", "") for c in competitors if c.get("name")]


# =============================================================================
# emails.csv Management
# =============================================================================

def ensure_emails_csv():
    """Ensure emails.csv exists with headers."""
    EMAILS_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not EMAILS_CSV.exists():
        with open(EMAILS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(EMAIL_COLUMNS)


def load_emails_df() -> pd.DataFrame:
    """Load emails.csv as DataFrame."""
    ensure_emails_csv()
    try:
        df = pd.read_csv(EMAILS_CSV)
        # Ensure all columns exist
        for col in EMAIL_COLUMNS:
            if col not in df.columns:
                if col == "status":
                    df[col] = "inbox"  # Default status for existing records
                else:
                    df[col] = ""
        # Fill NaN status values with "inbox"
        if "status" in df.columns:
            df["status"] = df["status"].fillna("inbox").replace("", "inbox")
        return df
    except Exception:
        return pd.DataFrame(columns=EMAIL_COLUMNS)


def email_exists(json_file: str) -> bool:
    """Check if an email with this json_file already exists."""
    df = load_emails_df()
    return json_file in df["json_file"].values


def save_email_record(
    json_file: str,
    from_address: str,
    to_address: str,
    date: str,
    subject: str,
    matched_company: Optional[str] = None,
    injected: bool = False,
    status: str = "inbox",
) -> Dict[str, Any]:
    """
    Save email record to emails.csv.
    Returns the row dict.
    """
    ensure_emails_csv()

    now = datetime.now(UTC).isoformat()
    row = {
        "json_file": json_file,
        "from_address": from_address,
        "to_address": to_address,
        "date": date,
        "subject": subject,
        "matched_company": matched_company or "unmatched",
        "injected": str(injected),
        "received_at": now,
        "processed_at": now if matched_company else "",
        "status": status,
    }

    with open(EMAILS_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EMAIL_COLUMNS)
        writer.writerow(row)

    logger.debug(f"Saved email record: {json_file}")
    return row


def update_email_injected(json_file: str, injected: bool = True):
    """Mark an email as injected into updates.csv."""
    df = load_emails_df()
    if json_file in df["json_file"].values:
        df.loc[df["json_file"] == json_file, "injected"] = str(injected)
        df.to_csv(EMAILS_CSV, index=False)
        logger.debug(f"Marked email as injected: {json_file}")


# =============================================================================
# email_senders.csv Management
# =============================================================================

def ensure_senders_csv():
    """Ensure email_senders.csv exists with headers."""
    SENDERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    if not SENDERS_CSV.exists():
        with open(SENDERS_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(SENDER_COLUMNS)


def load_senders_df() -> pd.DataFrame:
    """Load email_senders.csv as DataFrame."""
    ensure_senders_csv()
    try:
        df = pd.read_csv(SENDERS_CSV)
        # Ensure all columns exist
        for col in SENDER_COLUMNS:
            if col not in df.columns:
                if col in ["emails_received", "emails_processed", "emails_injected"]:
                    df[col] = 0
                else:
                    df[col] = ""
        return df
    except Exception:
        return pd.DataFrame(columns=SENDER_COLUMNS)


def get_sender_assigned_company(from_address: str) -> Optional[str]:
    """Get manually assigned company for a sender, if any."""
    df = load_senders_df()
    match = df[df["from_address"] == from_address]
    if not match.empty:
        assigned = match.iloc[0].get("assigned_company", "")
        if assigned and str(assigned).strip() and str(assigned).lower() != "nan":
            return str(assigned).strip()
    return None


def update_sender_stats(
    from_address: str,
    received: int = 0,
    processed: int = 0,
    injected: int = 0,
):
    """
    Update sender statistics. Increments the counts by the given amounts.
    Creates the sender row if it doesn't exist.
    """
    ensure_senders_csv()
    df = load_senders_df()
    now = datetime.now(UTC).isoformat()

    if from_address in df["from_address"].values:
        # Update existing row
        idx = df[df["from_address"] == from_address].index[0]
        df.loc[idx, "emails_received"] = int(df.loc[idx, "emails_received"] or 0) + received
        df.loc[idx, "emails_processed"] = int(df.loc[idx, "emails_processed"] or 0) + processed
        df.loc[idx, "emails_injected"] = int(df.loc[idx, "emails_injected"] or 0) + injected
        df.loc[idx, "last_seen"] = now
    else:
        # Create new row
        new_row = {
            "from_address": from_address,
            "emails_received": received,
            "emails_processed": processed,
            "emails_injected": injected,
            "assigned_company": "",
            "last_seen": now,
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.to_csv(SENDERS_CSV, index=False)
    logger.debug(f"Updated sender stats: {from_address} (+{received} recv, +{processed} proc, +{injected} inj)")


def set_sender_assigned_company(from_address: str, company: str):
    """Manually assign a company to a sender for auto-matching."""
    ensure_senders_csv()
    df = load_senders_df()

    if from_address in df["from_address"].values:
        df.loc[df["from_address"] == from_address, "assigned_company"] = company
    else:
        # Create new row with assignment
        new_row = {
            "from_address": from_address,
            "emails_received": 0,
            "emails_processed": 0,
            "emails_injected": 0,
            "assigned_company": company,
            "last_seen": datetime.now(UTC).isoformat(),
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    df.to_csv(SENDERS_CSV, index=False)
    logger.info(f"Assigned sender {from_address} to company: {company}")


def get_all_senders() -> pd.DataFrame:
    """Get all senders with their stats for the UI."""
    return load_senders_df()


# =============================================================================
# AI Email Matching
# =============================================================================

def match_email_to_competitor(from_address: str, subject: str, body_preview: str) -> Optional[str]:
    """
    Match an email to a competitor.

    First checks for manual assignment, then uses AI.
    Returns competitor name if matched, None if no match.
    """
    # Check for manual assignment first
    assigned = get_sender_assigned_company(from_address)
    if assigned:
        logger.info(f"Using assigned company for {from_address}: {assigned}")
        return assigned

    # Use AI matching
    competitor_names = get_competitor_names()

    if not competitor_names:
        logger.warning("No competitors configured")
        return None

    # Build prompt from config
    competitors_list = "\n".join(f"- {name}" for name in competitor_names)
    prompt_config = _get_prompt("email_match")

    user_prompt = prompt_config["user"].format(
        competitors_list=competitors_list,
        from_address=from_address,
        subject=subject,
        body_preview=body_preview[:500]
    )

    try:
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=50,
            messages=[
                {"role": "system", "content": prompt_config["system"]},
                {"role": "user", "content": user_prompt}
            ],
        )

        result = resp.choices[0].message.content.strip()

        # Validate result is in our list
        if result.upper() == "NONE":
            return None

        # Find case-insensitive match
        for name in competitor_names:
            if name.lower() == result.lower():
                return name

        # Partial match fallback
        for name in competitor_names:
            if name.lower() in result.lower() or result.lower() in name.lower():
                return name

        logger.debug(f"OpenAI returned '{result}' but no match found in competitors")
        return None

    except Exception as e:
        logger.error(f"OpenAI matching failed: {e}")
        return None


def check_email_quality(from_address: str, subject: str, body_preview: str) -> bool:
    """
    Quality gate: Determine if an email is worth injecting into the pipeline.

    Returns True if email should be processed (ACCEPT), False otherwise (REJECT).
    """
    prompt_config = _get_prompt("email_quality")

    user_prompt = prompt_config["user"].format(
        from_address=from_address,
        subject=subject,
        body_preview=body_preview[:1000]  # More context for quality check
    )

    try:
        client = _get_openai_client()
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=10,
            messages=[
                {"role": "system", "content": prompt_config["system"]},
                {"role": "user", "content": user_prompt}
            ],
        )

        result = resp.choices[0].message.content.strip().upper()
        is_accepted = "ACCEPT" in result

        logger.info(f"Quality gate: {result} for '{subject[:50]}...'")
        return is_accepted

    except Exception as e:
        logger.error(f"Quality check failed: {e}")
        # Default to accepting if quality check fails (fail open)
        return True


# =============================================================================
# Convenience Functions
# =============================================================================

def record_email_received(
    json_file: str,
    from_address: str,
    to_address: str,
    date: str,
    subject: str,
) -> Dict[str, Any]:
    """
    Record that an email was received (first step in pipeline).
    Updates both emails.csv and sender stats.
    Returns the email record.
    """
    # Check for duplicate
    if email_exists(json_file):
        logger.debug(f"Email already recorded: {json_file}")
        return {}

    # Save to emails.csv (not yet matched)
    record = save_email_record(
        json_file=json_file,
        from_address=from_address,
        to_address=to_address,
        date=date,
        subject=subject,
        matched_company=None,
        injected=False,
    )

    # Update sender received count
    update_sender_stats(from_address, received=1)

    return record


def record_email_matched(json_file: str, from_address: str, matched_company: str):
    """
    Record that an email was matched to a competitor.
    Updates emails.csv and sender stats.
    """
    df = load_emails_df()
    if json_file in df["json_file"].values:
        df.loc[df["json_file"] == json_file, "matched_company"] = matched_company
        df.loc[df["json_file"] == json_file, "processed_at"] = datetime.now(UTC).isoformat()
        df.to_csv(EMAILS_CSV, index=False)

    # Update sender processed count
    update_sender_stats(from_address, processed=1)
    logger.info(f"Email matched: {json_file} -> {matched_company}")


def record_email_injected(json_file: str, from_address: str):
    """
    Record that an email was injected into updates.csv.
    Updates emails.csv and sender stats.
    """
    update_email_injected(json_file, injected=True)
    update_sender_stats(from_address, injected=1)
    logger.info(f"Email injected: {json_file}")


def rebuild_sender_stats():
    """
    Rebuild email_senders.csv from emails.csv.
    Only counts inbox emails (excludes deleted).
    Useful for data recovery or migration.
    """
    emails_df = load_emails_df()

    if emails_df.empty:
        logger.info("No emails to rebuild stats from")
        return

    # Filter to only inbox emails (not deleted)
    inbox_df = emails_df[emails_df["status"] != "deleted"]
    logger.info(f"Rebuilding stats from {len(inbox_df)} inbox emails ({len(emails_df) - len(inbox_df)} deleted)")

    # Group by sender and calculate stats
    stats = []
    for from_address, group in inbox_df.groupby("from_address"):
        stats.append({
            "from_address": from_address,
            "emails_received": len(group),
            "emails_processed": len(group[group["matched_company"] != "unmatched"]),
            "emails_injected": len(group[group["injected"].astype(str).str.lower() == "true"]),
            "assigned_company": "",  # Preserve if exists
            "last_seen": group["received_at"].max(),
        })

    # Preserve manual assignments from existing senders.csv
    existing_df = load_senders_df()
    assignments = dict(zip(existing_df["from_address"], existing_df["assigned_company"]))

    for stat in stats:
        if stat["from_address"] in assignments:
            stat["assigned_company"] = assignments[stat["from_address"]] or ""

    # Write new senders.csv
    new_df = pd.DataFrame(stats)
    new_df.to_csv(SENDERS_CSV, index=False)
    logger.info(f"Rebuilt sender stats: {len(stats)} senders")


# =============================================================================
# Delete Functions
# =============================================================================

def _decrement_sender_stats(
    from_address: str,
    received: int = 0,
    processed: int = 0,
    injected: int = 0,
):
    """
    Decrement sender statistics when an email is deleted.
    Ensures counts don't go below zero.
    """
    df = load_senders_df()

    if from_address not in df["from_address"].values:
        logger.warning(f"Sender not found for stats decrement: {from_address}")
        return

    idx = df[df["from_address"] == from_address].index[0]

    # Decrement counts, ensuring they don't go negative
    current_received = int(df.loc[idx, "emails_received"] or 0)
    current_processed = int(df.loc[idx, "emails_processed"] or 0)
    current_injected = int(df.loc[idx, "emails_injected"] or 0)

    df.loc[idx, "emails_received"] = max(0, current_received - received)
    df.loc[idx, "emails_processed"] = max(0, current_processed - processed)
    df.loc[idx, "emails_injected"] = max(0, current_injected - injected)

    df.to_csv(SENDERS_CSV, index=False)
    logger.info(f"Decremented sender stats: {from_address} (-{received} recv, -{processed} proc, -{injected} inj)")


def delete_sender(from_address: str) -> bool:
    """
    Delete a sender from email_senders.csv.
    Only allows deletion if sender has no assigned company.

    Returns True if deleted, False otherwise.
    """
    df = load_senders_df()

    if from_address not in df["from_address"].values:
        logger.warning(f"Sender not found: {from_address}")
        return False

    # Check if sender has an assigned company
    sender_row = df[df["from_address"] == from_address].iloc[0]
    assigned = sender_row.get("assigned_company", "")
    if assigned and str(assigned).strip() and str(assigned).lower() != "nan":
        logger.warning(f"Cannot delete sender with assigned company: {from_address} -> {assigned}")
        return False

    # Delete the sender
    df = df[df["from_address"] != from_address]
    df.to_csv(SENDERS_CSV, index=False)
    logger.info(f"Deleted sender: {from_address}")
    return True


def delete_email(json_file: str) -> bool:
    """
    Delete an email:
    1. Mark status as "deleted" in emails.csv
    2. Update sender stats (decrement counts)
    3. Move JSON file to data/emails/deleted/
    4. Remove from updates.csv and enriched_updates.csv

    Returns True if successful, False otherwise.
    """
    import shutil

    # Paths
    emails_dir = Path("data/emails")
    processed_dir = emails_dir / "processed"
    deleted_dir = emails_dir / "deleted"
    deleted_dir.mkdir(parents=True, exist_ok=True)

    updates_csv = Path("data/updates.csv")
    enriched_csv = Path("data/enriched_updates.csv")

    # 1. Get email record and update status
    df = load_emails_df()
    if json_file not in df["json_file"].values:
        logger.warning(f"Email not found in emails.csv: {json_file}")
        return False

    # Get email info before marking deleted (for sender stats update)
    email_row = df[df["json_file"] == json_file].iloc[0]
    from_address = email_row.get("from_address", "")
    matched_company = email_row.get("matched_company", "")
    was_injected = str(email_row.get("injected", "")).lower() == "true"
    was_processed = matched_company and matched_company != "unmatched"

    df.loc[df["json_file"] == json_file, "status"] = "deleted"
    df.to_csv(EMAILS_CSV, index=False)
    logger.info(f"Marked email as deleted: {json_file}")

    # 2. Update sender stats (decrement counts)
    if from_address:
        _decrement_sender_stats(
            from_address,
            received=1,
            processed=1 if was_processed else 0,
            injected=1 if was_injected else 0,
        )

    # 3. Move JSON file to deleted folder
    email_id = json_file.replace(".json", "")
    source_url = f"email://{email_id}"

    # Try to find and move the file
    source_file = emails_dir / json_file
    if not source_file.exists():
        source_file = processed_dir / json_file

    if source_file.exists():
        dest_file = deleted_dir / json_file
        try:
            shutil.move(str(source_file), str(dest_file))
            logger.info(f"Moved email file to deleted: {json_file}")
        except Exception as e:
            logger.warning(f"Failed to move email file: {e}")

    # 4. Remove from updates.csv
    if updates_csv.exists():
        try:
            updates_df = pd.read_csv(updates_csv)
            original_len = len(updates_df)
            updates_df = updates_df[updates_df["source_url"] != source_url]
            if len(updates_df) < original_len:
                updates_df.to_csv(updates_csv, index=False)
                logger.info(f"Removed from updates.csv: {source_url}")
        except Exception as e:
            logger.warning(f"Failed to update updates.csv: {e}")

    # 5. Remove from enriched_updates.csv
    if enriched_csv.exists():
        try:
            enriched_df = pd.read_csv(enriched_csv)
            original_len = len(enriched_df)
            enriched_df = enriched_df[enriched_df["source_url"] != source_url]
            if len(enriched_df) < original_len:
                enriched_df.to_csv(enriched_csv, index=False)
                logger.info(f"Removed from enriched_updates.csv: {source_url}")
        except Exception as e:
            logger.warning(f"Failed to update enriched_updates.csv: {e}")

    return True
