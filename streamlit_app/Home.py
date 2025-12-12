# streamlit_app/Home.py
import os
import sys
import subprocess
import signal
import time
from html import escape
from pathlib import Path
import re
from collections import Counter
from io import BytesIO
from typing import Dict

from dotenv import load_dotenv
load_dotenv()  # Load .env file for API keys

import pandas as pd
import streamlit as st
import yaml
from openai import OpenAI
from dateutil import parser as dateparser

from app.logger import (
    get_system_logger,
    log_startup,
    log_user_action,
    init_client_ip,
    get_client_ip,
)
from app.email_matcher import (
    get_all_senders,
    load_emails_df,
    set_sender_assigned_company,
    get_competitor_names,
    rebuild_sender_stats,
    delete_sender,
    delete_email,
)

# Initialize logging
logger = get_system_logger(__name__)

# --- reportlab for PDF ---
from reportlab.lib.pagesizes import LETTER, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

# --------------------------- Constants ---------------------------
DATA_ENRICHED = "data/enriched_updates.csv"
DATA_RAW = "data/updates.csv"
LOGO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "member_solutions_logo.png"))
SCAN_LOCK_FILE = "data/.scan_in_progress.lock"

st.set_page_config(page_title="Competitor Updates", layout="wide")

# --------------------------- Session & Logging Init ---------------------------
# Initialize client IP tracking
init_client_ip()

# Log page view on first load (once per session)
if "logged_page_view" not in st.session_state:
    st.session_state.logged_page_view = True
    client_ip = get_client_ip()
    log_startup("Streamlit Dashboard")
    log_user_action(client_ip, "page_view", "Dashboard loaded")

# --------------------------- Scan State Management ---------------------------
def is_scan_running() -> bool:
    """Check if a scan is currently in progress by checking lock file."""
    if os.path.exists(SCAN_LOCK_FILE):
        try:
            with open(SCAN_LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            # Check if process is still running
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                else:
                    # Process not running, clean up stale lock
                    os.remove(SCAN_LOCK_FILE)
                    return False
            else:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return True
        except (ValueError, ProcessLookupError, OSError, FileNotFoundError):
            # Process not running or lock file invalid, clean up
            try:
                os.remove(SCAN_LOCK_FILE)
            except FileNotFoundError:
                pass
            return False
    return False

def get_scan_pid() -> int | None:
    """Get the PID of the running scan process."""
    if os.path.exists(SCAN_LOCK_FILE):
        try:
            with open(SCAN_LOCK_FILE, "r") as f:
                return int(f.read().strip())
        except (ValueError, FileNotFoundError):
            return None
    return None

def start_scan() -> bool:
    """Start a new scan process in the background."""
    if is_scan_running():
        return False

    client_ip = get_client_ip()
    try:
        # Start the scan process
        if sys.platform == "win32":
            # Windows: use CREATE_NEW_PROCESS_GROUP for proper process management
            proc = subprocess.Popen(
                [sys.executable, "-m", "jobs.daily_scan"],
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            # Unix: start in new process group
            proc = subprocess.Popen(
                [sys.executable, "-m", "jobs.daily_scan"],
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )

        # Write lock file with PID
        os.makedirs(os.path.dirname(SCAN_LOCK_FILE), exist_ok=True)
        with open(SCAN_LOCK_FILE, "w") as f:
            f.write(str(proc.pid))

        logger.info(f"Scan started by user, PID: {proc.pid}")
        log_user_action(client_ip, "scan_start", f"Started scan process PID={proc.pid}")
        return True
    except Exception as e:
        logger.error(f"Failed to start scan: {e}")
        log_user_action(client_ip, "scan_error", f"Failed to start scan: {e}")
        st.error(f"Failed to start scan: {e}")
        return False

def cancel_scan() -> bool:
    """Cancel the running scan process."""
    pid = get_scan_pid()
    if pid is None:
        return False

    client_ip = get_client_ip()
    try:
        if sys.platform == "win32":
            # Windows: use taskkill to terminate process tree
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                         capture_output=True, check=False)
        else:
            # Unix: send SIGTERM to process group
            os.killpg(os.getpgid(pid), signal.SIGTERM)

        # Clean up lock file
        try:
            os.remove(SCAN_LOCK_FILE)
        except FileNotFoundError:
            pass

        logger.info(f"Scan cancelled by user, PID: {pid}")
        log_user_action(client_ip, "scan_cancel", f"Cancelled scan process PID={pid}")
        return True
    except Exception as e:
        logger.error(f"Failed to cancel scan: {e}")
        log_user_action(client_ip, "scan_error", f"Failed to cancel scan: {e}")
        st.error(f"Failed to cancel scan: {e}")
        # Still try to clean up lock file
        try:
            os.remove(SCAN_LOCK_FILE)
        except FileNotFoundError:
            pass
        return False

# Initialize session state for scan confirmation dialogs
if "scan_dialog_state" not in st.session_state:
    st.session_state.scan_dialog_state = None  # None, "confirm_scan", "confirm_cancel"
if "confirmation_text" not in st.session_state:
    st.session_state.confirmation_text = ""

# Initialize session state for settings page
if "show_settings" not in st.session_state:
    st.session_state.show_settings = False

# --------------------------- Header with Scan Button & Settings Gear ---------------------------
header_col1, header_col2, header_col3 = st.columns([4, 0.5, 1])

with header_col1:
    st.title("Competitor Analysis")

with header_col2:
    # Settings gear icon
    if st.button("⚙️", key="btn_settings", help="Settings & Admin Tools"):
        st.session_state.show_settings = True
        st.rerun()

with header_col3:
    scan_running = is_scan_running()

    if scan_running:
        # Show Cancel Scan button (red/warning style)
        if st.button("🛑 Cancel Scan", key="btn_cancel_scan", type="secondary", use_container_width=True):
            st.session_state.scan_dialog_state = "confirm_cancel"
            st.session_state.confirmation_text = ""
            st.rerun()
        st.caption("⏳ Scan in progress...")
    else:
        # Show Re-scan button
        if st.button("🔄 Re-scan", key="btn_rescan", type="primary", use_container_width=True):
            st.session_state.scan_dialog_state = "confirm_scan"
            st.session_state.confirmation_text = ""
            st.rerun()

# --------------------------- Live Scan Logs (when scan is running) ---------------------------
if scan_running:
    SYSTEM_LOG_PATH = "logs/system.log"
    with st.expander("📋 Live Scan Logs", expanded=True):
        st.caption("Showing latest scan activity (auto-refreshes)")

        # Read last N lines from system.log
        try:
            if os.path.exists(SYSTEM_LOG_PATH):
                with open(SYSTEM_LOG_PATH, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    # Get last 30 lines
                    recent_lines = lines[-30:] if len(lines) > 30 else lines
                    log_text = "".join(recent_lines)
                    st.code(log_text, language="log")
            else:
                st.info("No log file found yet. Logs will appear once the scan starts processing.")
        except Exception as e:
            st.warning(f"Could not read log file: {e}")

        # Auto-refresh button
        if st.button("🔄 Refresh Logs", key="btn_refresh_logs"):
            st.rerun()

# --------------------------- Confirmation Dialogs ---------------------------
if st.session_state.scan_dialog_state == "confirm_scan":
    st.warning("### ⚠️ Confirm Re-scan")
    st.write("This will start a full competitor scan which may take 5-15 minutes.")
    st.write("**Type `I'm sure` below to confirm:**")

    confirm_input = st.text_input(
        "Confirmation",
        value=st.session_state.confirmation_text,
        key="scan_confirm_input",
        placeholder="Type: I'm sure",
        label_visibility="collapsed"
    )
    st.session_state.confirmation_text = confirm_input

    col_confirm, col_cancel = st.columns(2)

    with col_confirm:
        # Only enable if user typed the exact phrase
        can_proceed = confirm_input.strip().lower() == "i'm sure"
        if st.button("✅ Start Scan", disabled=not can_proceed, type="primary", key="btn_confirm_scan"):
            if start_scan():
                st.session_state.scan_dialog_state = None
                st.session_state.confirmation_text = ""
                st.success("Scan started! The page will refresh to show progress.")
                time.sleep(1)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Failed to start scan. A scan may already be in progress.")

    with col_cancel:
        if st.button("❌ Cancel", key="btn_cancel_confirm"):
            st.session_state.scan_dialog_state = None
            st.session_state.confirmation_text = ""
            st.rerun()

    st.divider()

elif st.session_state.scan_dialog_state == "confirm_cancel":
    st.error("### 🛑 Confirm Cancel Scan")
    st.write("This will terminate the running scan process. Any partial data will be preserved.")
    st.write("**Type `I'm sure` below to confirm:**")

    confirm_input = st.text_input(
        "Confirmation",
        value=st.session_state.confirmation_text,
        key="cancel_confirm_input",
        placeholder="Type: I'm sure",
        label_visibility="collapsed"
    )
    st.session_state.confirmation_text = confirm_input

    col_confirm, col_cancel = st.columns(2)

    with col_confirm:
        can_proceed = confirm_input.strip().lower() == "i'm sure"
        if st.button("🛑 Cancel Scan", disabled=not can_proceed, type="primary", key="btn_confirm_cancel"):
            if cancel_scan():
                st.session_state.scan_dialog_state = None
                st.session_state.confirmation_text = ""
                st.success("Scan cancelled.")
                time.sleep(1)
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Failed to cancel scan.")

    with col_cancel:
        if st.button("⬅️ Go Back", key="btn_back_from_cancel"):
            st.session_state.scan_dialog_state = None
            st.session_state.confirmation_text = ""
            st.rerun()

    st.divider()

# Reload button (clears Streamlit cache)
if st.button("Reload Data", key="reload_button"):
    st.cache_data.clear()
    st.rerun()

# --------------------------- Helpers ---------------------------
def _parse_datetime_to_utc(value):
    """Parse a datetime string to UTC-aware datetime, handling various formats."""
    if pd.isna(value) or str(value).strip() in ("", "nan", "NaN", "None", "NaT"):
        return pd.NaT
    try:
        dt = dateparser.parse(str(value))
        if dt is None:
            return pd.NaT
        if dt.tzinfo is not None:
            return dt.astimezone(pd.Timestamp.now('UTC').tzinfo)
        else:
            return dt.replace(tzinfo=pd.Timestamp.now('UTC').tzinfo)
    except Exception:
        return pd.NaT


@st.cache_data(show_spinner=False)
def load_data():
    """Load enriched if present, else raw; normalize timestamps and required cols."""
    path = DATA_ENRICHED if os.path.exists(DATA_ENRICHED) else DATA_RAW
    df = pd.read_csv(path)

    # Normalize datetimes using dateutil parser (handles timezone offsets properly)
    for col in ["published_at", "collected_at"]:
        if col in df.columns:
            df[col] = df[col].apply(_parse_datetime_to_utc)

    # Ensure required columns exist
    for col, default in [
        ("company", ""),
        ("title", ""),
        ("summary", ""),
        ("category", "Uncategorized"),
        ("impact", ""),
    ]:
        if col not in df.columns:
            df[col] = default

    # Unified reference date: prefer collected_at (when we discovered it) for competitive intelligence
    # published_at can be years old for blog archive crawls, which isn't useful for CI
    coll = df.get("collected_at")
    if coll is not None:
        df["date_ref"] = coll
    elif "date_ref" in df.columns:
        df["date_ref"] = df["date_ref"].apply(_parse_datetime_to_utc)
    else:
        pub = df.get("published_at")
        df["date_ref"] = pub if pub is not None else pd.NaT

    return df, path

def impact_badge(val):
    """Render nice badge or empty string if no impact yet."""
    if pd.isna(val):
        return ""
    txt = str(val).strip().title()
    if not txt or txt in {"Nan", "Na"}:
        return ""
    color = {"High": "red", "Medium": "orange", "Low": "gray"}.get(txt, "gray")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;">{txt}</span>'

def clickable_title(title: str, url: str) -> str:
    from urllib.parse import quote

    t = escape((title or "").strip() or "View")
    u = (url or "").strip()
    if not u:
        return t

    # For email entries, link to the webhook email viewer
    if u.startswith("email://"):
        email_id = u.replace("email://", "")
        # URL-encode the email ID to handle special characters like = and +
        email_id_encoded = quote(email_id, safe="")
        # Get webhook port from config
        config_path = Path("config/monitors.yaml")
        webhook_port = 8001
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                    webhook_port = cfg.get("global", {}).get("webhook_port", 8001)
            except Exception:
                pass
        u = f"http://localhost:{webhook_port}/email/view/{email_id_encoded}"

    return f'<a href="{escape(u)}" target="_blank" rel="noopener">{t}</a>'

def _condense_words(text: str, max_words: int = 28) -> str:
    """Return a compact sentence capped at ~max_words, cleaned and ellipsized."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip(" \t\n\r-–—")
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",.;:—- ") + "…"

# OpenAI client for summaries
client = OpenAI()

def _get_summarize_prompts() -> Dict[str, str]:
    """Get summarize_point prompts from config."""
    import yaml
    config_path = "config/monitors.yaml"
    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            prompts = config.get("prompts", {}).get("summarize_point", {})
            if prompts:
                return prompts
    except Exception:
        pass
    # Defaults
    return {
        "system": "You are a professional business summarizer.",
        "user": "Summarize the following news or blog content in a single concise paragraph of about {max_words} words. Make it clear, factual, and self-contained:\n\n{text}"
    }

def summarize_point(text: str, max_words: int = 50) -> str:
    """Uses GPT to generate a clean 1–2 sentence summary (~50 words)."""
    text = (text or "").strip()
    if not text:
        return ""

    prompts = _get_summarize_prompts()
    user_prompt = prompts["user"].format(max_words=max_words, text=text)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=120,
            messages=[
                {"role": "system", "content": prompts["system"]},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("Summarization failed:", e)
        return text[:300]  # fallback

def build_exec_blocks(filtered_df: pd.DataFrame, max_highlights: int = 3, progress_callback=None):
    """Create structured summary blocks from the current filtered data.

    Args:
        filtered_df: DataFrame with competitor data
        max_highlights: Max highlight sentences per company
        progress_callback: Optional callable(current, total, company_name) for progress updates
    """
    blocks = []
    if filtered_df.empty:
        return blocks

    companies = list(filtered_df.groupby("company"))
    total = len(companies)

    for idx, (company, g) in enumerate(companies):
        if progress_callback:
            progress_callback(idx, total, company)

        posts = len(g)

        # Impact counts
        ic = g.get("impact", pd.Series([], dtype=object)).astype(str).str.title()
        impact = {k: int(ic.eq(k).sum()) for k in ["High", "Medium", "Low"]}

        # Top topics
        top_topics = []
        if "category" in g.columns:
            cats = (g["category"].astype(str).str.strip().replace({"": "Uncategorized"})
                    .value_counts().head(3))
            top_topics = list(cats.items())  # [(name, count), ...]

        # Highlight sentences: prefer 'summary'; fallback to 'title'
        texts = (
            g.apply(lambda r: (str(r.get("summary", "")).strip()
                               or str(r.get("title", "")).strip()), axis=1)
             .head(max_highlights)
             .tolist()
        )

        # Refine highlight sentences with summarize_point (short, ~50 words)
        refined = []
        for t in texts:
            s = summarize_point(t, max_words=50)
            if s:
                refined.append(s)

        blocks.append({
            "company": company,
            "posts": posts,
            "impact": impact,
            "top_topics": top_topics,
            "highlights": refined
        })

    if progress_callback:
        progress_callback(total, total, "Done")

    return blocks

def exec_blocks_to_pdf(blocks, daterange_label: str = "") -> bytes:
    """Render the executive summary blocks into a PDF and return bytes (with logo header)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        rightMargin=36, leftMargin=36, topMargin=54, bottomMargin=36  # space for header
    )
    styles = getSampleStyleSheet()
    elements = []

    # Title & date range
    elements.append(Paragraph("Executive Summary", styles["Title"]))
    if daterange_label:
        elements.append(Paragraph(daterange_label, styles["Italic"]))
    elements.append(Spacer(1, 0.25 * inch))

    # Body blocks
    for b in blocks:
        elements.append(Paragraph(b["company"], styles["Heading2"]))

        meta = (f'{b["posts"]} posts'
                f' • Impact mix — High: {b["impact"]["High"]}, '
                f'Medium: {b["impact"]["Medium"]}, '
                f'Low: {b["impact"]["Low"]}')
        elements.append(Paragraph(meta, styles["BodyText"]))

        if b.get("top_topics"):
            topics = ", ".join(f"{name} ({cnt})" for name, cnt in b["top_topics"])
            elements.append(Paragraph(f"Top topics: {topics}", styles["BodyText"]))

        if b.get("highlights"):
            elements.append(Spacer(1, 0.08 * inch))
            elements.append(Paragraph("Highlights", styles["Heading3"]))
            bullets = [ListItem(Paragraph(text, styles["BodyText"]), leftIndent=12)
                       for text in b["highlights"]]
            elements.append(ListFlowable(bullets, bulletType="bullet"))

        elements.append(Spacer(1, 0.2 * inch))

    # Header (logo top-right)
    def _header(cv, _doc):
        try:
            if os.path.exists(LOGO_PATH):
                page_w, page_h = _doc.pagesize
                img = ImageReader(LOGO_PATH)
                iw, ih = img.getSize()
                target_w = 120
                target_h = target_w * (ih / iw)
                x = page_w - target_w - 36
                y = page_h - target_h - 18
                cv.drawImage(
                    LOGO_PATH, x, y,
                    width=target_w, height=target_h,
                    mask='auto', preserveAspectRatio=True, anchor='n'
                )
        except Exception as e:
            print("Logo draw failed:", e)

    doc.build(elements, onFirstPage=_header, onLaterPages=_header)
    pdf = buf.getvalue()
    buf.close()
    return pdf

def render_feed(f: pd.DataFrame):
    """Render the feed table from the current filtered frame `f`."""
    st.divider()
    st.subheader("Feed")
    st.write("Click a title to open the source; summaries appear if enrichment is complete.")

    if f.empty:
        st.info("No rows in the current selection.")
        return

    show_cols = [c for c in ["date_ref", "company", "title", "category", "impact", "source_url", "summary"] if c in f.columns]
    if not show_cols:
        st.info("Feed cannot render because required columns are missing.")
        return

    sorted_f = f.sort_values(by=["date_ref"], ascending=False)
    display = sorted_f[show_cols].copy()

    # format / cleanup
    if "date_ref" in display.columns:
        display["date_ref"] = pd.to_datetime(display["date_ref"], errors="coerce", utc=True).dt.strftime("%m-%d-%Y")

    for c in [c for c in ["category", "summary", "title", "company", "source_url", "impact"] if c in display.columns]:
        display[c] = display[c].astype(object).where(display[c].notna(), "")

    if "category" in display.columns:
        display["category"] = display["category"].apply(lambda s: s if str(s).strip() else "Uncategorized")

    # clickable title + hide raw title/source_url in UI
    if {"title", "source_url"}.issubset(display.columns):
        title_link_series = pd.Series(
            [clickable_title(t, u) for t, u in zip(display["title"], display["source_url"])],
            index=display.index,
            name="title_link",
            dtype="object",
        )
        display = display.assign(title_link=title_link_series)
        display = display.drop(columns=["source_url", "title"], errors="ignore")
        ui_cols = [c for c in ["date_ref", "company", "title_link", "category", "impact", "summary"] if c in display.columns]
        display = display[ui_cols]

    # impact badge
    if "impact" in display.columns:
        display["impact"] = display["impact"].apply(impact_badge)

    # Render
    st.markdown(
        display.to_html(escape=False, index=False)
        .replace('<table', '<table style="word-wrap:break-word;white-space:normal;table-layout:fixed;width:100%;"')
        .replace('<td', '<td style="word-wrap:break-word;white-space:normal;"'),
        unsafe_allow_html=True,
    )


# --------------------------- Load & Sidebar ---------------------------
df, src_path = load_data()
st.caption(f"Data source: `{src_path}` • Rows: {len(df):,}")

# Debug panel
with st.expander("Debug: data health", expanded=False):
    st.write({"loaded_file": src_path, "rows": len(df)})
    for col in ["summary", "category", "impact"]:
        if col in df.columns:
            blanks = int(df[col].astype(str).str.strip().eq("").sum())
            st.write(f"{col}: {len(df) - blanks} filled, {blanks} blank")
        else:
            st.write(f"{col}: MISSING COLUMN")
    if st.button("Hard refresh data cache", key="debug_refresh"):
        st.cache_data.clear()
        st.rerun()

# --------------------------- Filter Change Tracking ---------------------------
# Initialize previous filter state for change detection
if "prev_filters" not in st.session_state:
    st.session_state.prev_filters = {}

def log_filter_change(filter_name: str, old_val, new_val):
    """Log filter changes when values differ, with specific details."""
    if old_val != new_val and old_val is not None:
        client_ip = get_client_ip()

        # Format the change message based on filter type
        if isinstance(new_val, (list, tuple)) and isinstance(old_val, (list, tuple)):
            # For multi-select filters, show what was added/removed
            old_set = set(old_val) if old_val else set()
            new_set = set(new_val) if new_val else set()
            added = new_set - old_set
            removed = old_set - new_set

            changes = []
            if added:
                changes.append(f"+{list(added)}")
            if removed:
                changes.append(f"-{list(removed)}")
            change_str = ", ".join(changes) if changes else f"{len(new_val)} selected"
        elif filter_name == "search":
            change_str = f'"{new_val}"' if new_val else "(cleared)"
        elif filter_name == "date_range":
            if new_val and len(new_val) == 2:
                change_str = f"{new_val[0]} to {new_val[1]}"
            else:
                change_str = str(new_val)
        else:
            change_str = str(new_val)

        log_user_action(client_ip, f"filter_{filter_name}", change_str)
        logger.debug(f"Filter '{filter_name}' changed: {old_val} -> {new_val}")

st.sidebar.header("Filters")
companies = sorted([c for c in df["company"].dropna().unique()])
sel_companies = st.sidebar.multiselect("Company", companies, default=companies)

categories = sorted([c for c in df["category"].dropna().unique()])
sel_categories = st.sidebar.multiselect("Category", categories, default=categories)

impacts = ["High", "Medium", "Low"]
if "impact" in df.columns:
    present_impacts = sorted({str(x).title() for x in df["impact"].dropna().unique() if str(x).strip()})
    impacts = [i for i in ["High", "Medium", "Low"] if i in present_impacts] or present_impacts or impacts
sel_impacts = st.sidebar.multiselect("Impact", impacts, default=impacts)

min_date = pd.to_datetime(df["date_ref"].min(), errors="coerce", utc=True)
max_date = pd.to_datetime(df["date_ref"].max(), errors="coerce", utc=True)

# Read date range from URL query params (persists across reloads)
qp = st.query_params
default_from = min_date.date() if pd.notna(min_date) else None
default_to = max_date.date() if pd.notna(max_date) else None

# Parse dates from query params if present
if "date_from" in qp:
    try:
        default_from = pd.to_datetime(qp["date_from"]).date()
    except Exception:
        pass
if "date_to" in qp:
    try:
        default_to = pd.to_datetime(qp["date_to"]).date()
    except Exception:
        pass

date_from, date_to = st.sidebar.date_input(
    "Date range",
    value=(default_from, default_to),
    key="sidebar_date_range",
)

# Sync date range back to URL query params for persistence
if date_from and date_to:
    st.query_params["date_from"] = str(date_from)
    st.query_params["date_to"] = str(date_to)

query = st.sidebar.text_input("Search title/summary...", "")

# Reset date filter button
if st.sidebar.button("Reset date range", key="btn_reset_dates", help="Clear saved date range and show all data"):
    # Remove date params from URL
    if "date_from" in st.query_params:
        del st.query_params["date_from"]
    if "date_to" in st.query_params:
        del st.query_params["date_to"]
    st.rerun()

# Log filter changes
log_filter_change("companies", st.session_state.prev_filters.get("companies"), sel_companies)
log_filter_change("categories", st.session_state.prev_filters.get("categories"), sel_categories)
log_filter_change("impacts", st.session_state.prev_filters.get("impacts"), sel_impacts)
log_filter_change("date_range", st.session_state.prev_filters.get("date_range"), (date_from, date_to))
log_filter_change("search", st.session_state.prev_filters.get("search"), query)

# Update previous filter state
st.session_state.prev_filters = {
    "companies": sel_companies,
    "categories": sel_categories,
    "impacts": sel_impacts,
    "date_range": (date_from, date_to),
    "search": query,
}

# --------------------------- Filtered Frame ---------------------------
f = df.copy()
if sel_companies:
    f = f[f["company"].isin(sel_companies)]
if sel_categories and "category" in f:
    f = f[f["category"].isin(sel_categories)]
if sel_impacts and "impact" in f:
    f = f[f["impact"].astype(str).str.title().isin(sel_impacts)]

# Date range
if pd.api.types.is_datetime64_any_dtype(f["date_ref"]) and date_from and date_to:
    start_utc = pd.Timestamp(date_from).tz_localize("UTC")
    end_utc = pd.Timestamp(date_to).tz_localize("UTC") + pd.Timedelta(days=1)  # inclusive
    f = f[(f["date_ref"] >= start_utc) & (f["date_ref"] < end_utc)]

# Title/summary search
if query.strip():
    q = query.lower()
    hay = (f["title"].fillna("") + " " + f.get("summary", pd.Series([""] * len(f))).fillna(""))
    f = f[hay.str.lower().str.contains(q, regex=False, na=False)]

# =====================================================================
# SETTINGS PAGE (shown when gear icon is clicked)
# =====================================================================
if st.session_state.show_settings:
    import yaml
    import copy

    # Back button
    if st.button("← Back to Dashboard", key="btn_back_to_main", type="primary"):
        st.session_state.show_settings = False
        st.rerun()

    st.title("Settings & Admin Tools")
    st.divider()

    # Create tabs for the settings sections
    settings_tab1, settings_tab2, settings_tab3, settings_tab4 = st.tabs(["⚙️ Configuration", "🏷️ Categories", "📧 Emails", "🔧 Data Quality Tools"])

    # ===================== CONFIGURATION TAB =====================
    with settings_tab1:
        CONFIG_PATH = "config/monitors.yaml"

        def load_yaml_config():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as cfg_file:
                    return yaml.safe_load(cfg_file)
            except Exception as e:
                st.error(f"Failed to load config: {e}")
                return None

        # Initialize session state for config editing
        if "config_competitors" not in st.session_state:
            config = load_yaml_config()
            if config:
                st.session_state.config_competitors = copy.deepcopy(config.get("competitors", []))
            else:
                st.session_state.config_competitors = []

        config = load_yaml_config()

        if config:
            # Global Settings
            st.subheader("Global Settings")

            col1, col2 = st.columns(2)

            with col1:
                current_log_level = config.get("global", {}).get("log_level", "INFO")
                log_level_options = ["DEBUG", "INFO", "WARNING", "ERROR"]
                try:
                    log_level_index = log_level_options.index(current_log_level.upper())
                except ValueError:
                    log_level_index = 1
                new_log_level = st.selectbox(
                    "Log Level",
                    options=log_level_options,
                    index=log_level_index,
                    help="DEBUG: Verbose logging. INFO: Normal operation.",
                    key="settings_log_level"
                )

                current_timeout = config.get("global", {}).get("request_timeout_s", 20)
                new_timeout = st.number_input(
                    "Request Timeout (seconds)",
                    min_value=5,
                    max_value=120,
                    value=int(current_timeout),
                    key="settings_timeout"
                )

            with col2:
                current_max_pages = config.get("global", {}).get("max_pages_per_site", 60)
                new_max_pages = st.number_input(
                    "Max Pages Per Site",
                    min_value=10,
                    max_value=500,
                    value=int(current_max_pages),
                    key="settings_max_pages"
                )

                current_dedupe = config.get("global", {}).get("dedupe_window_days", 365)
                new_dedupe = st.number_input(
                    "Dedupe Window (days)",
                    min_value=30,
                    max_value=730,
                    value=int(current_dedupe),
                    key="settings_dedupe"
                )

            current_ua = config.get("global", {}).get("user_agent", "")
            new_ua = st.text_input(
                "User Agent",
                value=current_ua,
                key="settings_user_agent"
            )

            current_follow = config.get("global", {}).get("follow_within_domain_only", True)
            new_follow = st.checkbox(
                "Follow Within Domain Only",
                value=current_follow,
                key="settings_follow_domain"
            )

            st.divider()

            # Competitors Management
            st.subheader("Monitored Competitors")
            st.caption(f"Currently monitoring {len(st.session_state.config_competitors)} competitors")

            updated_competitors = []
            for i, comp in enumerate(st.session_state.config_competitors):
                with st.container():
                    col1, col2, col3 = st.columns([2, 3, 0.5])
                    with col1:
                        new_name = st.text_input(
                            "Name" if i == 0 else f"Name###{i}",
                            value=comp.get("name", ""),
                            key=f"settings_comp_name_{i}",
                            label_visibility="visible" if i == 0 else "collapsed"
                        )
                    with col2:
                        urls_str = "\n".join(comp.get("start_urls", []))
                        new_urls_str = st.text_area(
                            "Start URLs (one per line)" if i == 0 else f"URLs###{i}",
                            value=urls_str,
                            height=68,
                            key=f"settings_comp_urls_{i}",
                            label_visibility="visible" if i == 0 else "collapsed"
                        )
                    with col3:
                        st.write("")
                        if st.button("🗑️", key=f"settings_del_comp_{i}", help=f"Remove {comp.get('name', 'competitor')}"):
                            st.session_state.config_competitors.pop(i)
                            st.rerun()

                    if new_name.strip():
                        updated_competitors.append({
                            "name": new_name.strip(),
                            "start_urls": [u.strip() for u in new_urls_str.strip().split("\n") if u.strip()]
                        })

            st.session_state.config_competitors = updated_competitors

            # Add new competitor
            st.markdown("**Add New Competitor**")
            new_comp_col1, new_comp_col2 = st.columns([2, 3])
            with new_comp_col1:
                new_comp_name = st.text_input(
                    "New Competitor Name",
                    value="",
                    key="settings_new_comp_name",
                    placeholder="e.g., Acme Corp"
                )
            with new_comp_col2:
                new_comp_urls = st.text_area(
                    "Start URLs (one per line)",
                    value="",
                    key="settings_new_comp_urls",
                    height=68,
                    placeholder="https://example.com/blog"
                )

            if st.button("➕ Add Competitor", key="settings_btn_add_competitor"):
                if new_comp_name.strip() and new_comp_urls.strip():
                    new_urls_list = [u.strip() for u in new_comp_urls.strip().split("\n") if u.strip()]
                    if new_urls_list:
                        # Add to session state
                        st.session_state.config_competitors.append({
                            "name": new_comp_name.strip(),
                            "start_urls": new_urls_list
                        })

                        # Auto-save to YAML file immediately
                        try:
                            updated_config = {
                                "global": config.get("global", {}),
                                "competitors": st.session_state.config_competitors
                            }
                            tmp_path = CONFIG_PATH + ".tmp"
                            with open(tmp_path, "w", encoding="utf-8") as cfg_file:
                                yaml.dump(updated_config, cfg_file, default_flow_style=False, allow_unicode=True, sort_keys=False)
                            os.replace(tmp_path, CONFIG_PATH)
                            log_user_action(get_client_ip(), "config_add_competitor", f"Added competitor: {new_comp_name.strip()}")
                            logger.info(f"Added competitor '{new_comp_name.strip()}' and saved to {CONFIG_PATH}")
                            st.success(f"Added '{new_comp_name.strip()}' and saved to config!")
                        except Exception as e:
                            st.error(f"Added to list but failed to save: {e}")
                            logger.error(f"Failed to save config after adding competitor: {e}")

                        # Clear input fields
                        if "settings_new_comp_name" in st.session_state:
                            del st.session_state["settings_new_comp_name"]
                        if "settings_new_comp_urls" in st.session_state:
                            del st.session_state["settings_new_comp_urls"]
                        st.rerun()
                else:
                    st.warning("Please enter both a name and at least one URL.")

            st.divider()

            # Alert Settings
            with st.expander("Alert Settings", expanded=False):
                current_high_impact = config.get("global", {}).get("high_impact_labels", [])
                new_high_impact = st.text_area(
                    "High Impact Labels (one per line)",
                    value="\n".join(current_high_impact),
                    height=100,
                    key="settings_high_impact"
                )

                current_alert_levels = config.get("global", {}).get("alert_on_impact_levels", ["High"])
                new_alert_levels = st.multiselect(
                    "Alert on Impact Levels",
                    options=["High", "Medium", "Low"],
                    default=[lvl for lvl in current_alert_levels if lvl in ["High", "Medium", "Low"]],
                    key="settings_alert_levels"
                )

            # Save / Reset buttons
            st.divider()
            col_save, col_reset = st.columns([1, 1])

            with col_save:
                if st.button("💾 Save Configuration", type="primary", key="settings_btn_save"):
                    try:
                        updated_config = {
                            "global": {
                                "log_level": new_log_level,
                                "user_agent": new_ua,
                                "request_timeout_s": int(new_timeout),
                                "max_pages_per_site": int(new_max_pages),
                                "follow_within_domain_only": new_follow,
                                "dedupe_window_days": int(new_dedupe),
                                "slack_webhook_env": config.get("global", {}).get("slack_webhook_env", "SLACK_WEBHOOK_URL"),
                                "high_impact_labels": [l.strip() for l in new_high_impact.strip().split("\n") if l.strip()],
                                "alert_on_impact_levels": new_alert_levels,
                            },
                            "competitors": st.session_state.config_competitors
                        }

                        tmp_path = CONFIG_PATH + ".tmp"
                        with open(tmp_path, "w", encoding="utf-8") as cfg_file:
                            yaml.dump(updated_config, cfg_file, default_flow_style=False, allow_unicode=True, sort_keys=False)
                        os.replace(tmp_path, CONFIG_PATH)

                        log_user_action(get_client_ip(), "config_save", f"Saved config: {len(st.session_state.config_competitors)} competitors")
                        logger.info(f"Configuration saved: {len(st.session_state.config_competitors)} competitors")
                        st.success("✅ Configuration saved!")

                        from app.logger import set_log_level
                        set_log_level(new_log_level)

                    except Exception as e:
                        st.error(f"Failed to save: {e}")
                        logger.error(f"Config save failed: {e}")

            with col_reset:
                if st.button("🔄 Reload from File", key="settings_btn_reload"):
                    if "config_competitors" in st.session_state:
                        del st.session_state.config_competitors
                    st.rerun()

            # View Raw YAML
            st.divider()
            with st.expander("📄 View Raw YAML", expanded=False):
                try:
                    with open(CONFIG_PATH, "r", encoding="utf-8") as cfg_file:
                        current_yaml = cfg_file.read()
                    st.code(current_yaml, language="yaml")
                except Exception as e:
                    st.error(f"Could not read config file: {e}")

    # ===================== CATEGORIES TAB =====================
    with settings_tab2:
        CONFIG_PATH = "config/monitors.yaml"

        def load_yaml_config_for_categories():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as cfg_file:
                    return yaml.safe_load(cfg_file)
            except Exception as e:
                st.error(f"Failed to load config: {e}")
                return None

        config_cat = load_yaml_config_for_categories()

        if config_cat:
            classification = config_cat.get("classification", {})

            # Initialize session state for categories
            if "config_categories" not in st.session_state:
                st.session_state.config_categories = classification.get("categories", [
                    "Product/Feature", "Pricing/Plans", "Partnership", "Acquisition/Investment",
                    "Case Study/Customer", "Events/Webinar", "Best Practices/Guides",
                    "Security/Compliance", "Hiring/Leadership", "Company News", "Other"
                ])

            st.subheader("Content Categories")
            st.caption("Categories used by AI to classify competitor content. 'Other' is always included as fallback.")

            # Display current categories with delete buttons
            categories_to_keep = []
            for i, cat in enumerate(st.session_state.config_categories):
                col1, col2 = st.columns([5, 1])
                with col1:
                    st.text(f"  {cat}")
                with col2:
                    # Don't allow deleting "Other" category
                    if cat == "Other":
                        st.text("(required)")
                    else:
                        if st.button("🗑️", key=f"del_cat_{i}", help=f"Delete '{cat}'"):
                            st.session_state.config_categories.remove(cat)
                            st.rerun()

            st.divider()

            # Add new category
            st.markdown("**Add New Category**")
            add_col1, add_col2 = st.columns([4, 1])
            with add_col1:
                new_category = st.text_input(
                    "New Category Name",
                    value="",
                    key="new_category_name",
                    placeholder="e.g., Industry Trends"
                )
            with add_col2:
                st.write("")  # Spacer
                if st.button("➕ Add", key="btn_add_category"):
                    if new_category.strip():
                        if new_category.strip() not in st.session_state.config_categories:
                            # Insert before "Other" if it exists
                            if "Other" in st.session_state.config_categories:
                                other_idx = st.session_state.config_categories.index("Other")
                                st.session_state.config_categories.insert(other_idx, new_category.strip())
                            else:
                                st.session_state.config_categories.append(new_category.strip())
                            st.success(f"Added '{new_category.strip()}'")
                            if "new_category_name" in st.session_state:
                                del st.session_state["new_category_name"]
                            st.rerun()
                        else:
                            st.warning("Category already exists.")
                    else:
                        st.warning("Please enter a category name.")

            st.divider()

            # Impact Rules
            st.subheader("Impact Classification Rules")
            st.caption("Define what triggers High, Medium, or Low impact scores.")

            impact_rules = classification.get("impact_rules", {})

            high_rules = st.text_area(
                "High Impact Triggers (one per line)",
                value="\n".join(impact_rules.get("high", ["pricing change", "major feature GA", "acquisitions", "big partnerships", "security incidents"])),
                height=100,
                key="impact_rules_high",
                help="Content matching these will be marked High impact"
            )

            medium_rules = st.text_area(
                "Medium Impact Triggers (one per line)",
                value="\n".join(impact_rules.get("medium", ["meaningful feature update", "big case study", "notable event announcements"])),
                height=80,
                key="impact_rules_medium"
            )

            low_rules = st.text_area(
                "Low Impact Triggers (one per line)",
                value="\n".join(impact_rules.get("low", ["generic tips", "routine posts"])),
                height=80,
                key="impact_rules_low"
            )

            st.divider()

            # Industry Context
            st.subheader("Industry Context")
            industry_context = st.text_input(
                "Industry Context for AI",
                value=classification.get("industry_context", "membership/club management software"),
                key="industry_context_input",
                help="This context is provided to the AI when classifying content"
            )

            st.divider()

            # Save button
            if st.button("💾 Save Categories & Rules", type="primary", key="btn_save_categories"):
                try:
                    # Ensure "Other" is in categories
                    final_categories = st.session_state.config_categories.copy()
                    if "Other" not in final_categories:
                        final_categories.append("Other")

                    # Build updated config
                    updated_config = config_cat.copy()
                    updated_config["classification"] = {
                        "categories": final_categories,
                        "impact_rules": {
                            "high": [r.strip() for r in high_rules.strip().split("\n") if r.strip()],
                            "medium": [r.strip() for r in medium_rules.strip().split("\n") if r.strip()],
                            "low": [r.strip() for r in low_rules.strip().split("\n") if r.strip()],
                        },
                        "industry_context": industry_context.strip()
                    }

                    tmp_path = CONFIG_PATH + ".tmp"
                    with open(tmp_path, "w", encoding="utf-8") as cfg_file:
                        yaml.dump(updated_config, cfg_file, default_flow_style=False, allow_unicode=True, sort_keys=False)
                    os.replace(tmp_path, CONFIG_PATH)

                    log_user_action(get_client_ip(), "categories_save", f"Saved {len(final_categories)} categories")
                    logger.info(f"Categories saved: {len(final_categories)} categories")
                    st.success("✅ Categories and rules saved!")

                except Exception as e:
                    st.error(f"Failed to save: {e}")
                    logger.error(f"Categories save failed: {e}")

            # Reload button
            if st.button("🔄 Reload from File", key="btn_reload_categories"):
                if "config_categories" in st.session_state:
                    del st.session_state.config_categories
                st.rerun()

    # ===================== EMAILS TAB =====================
    with settings_tab3:
        st.subheader("Email Senders")
        st.write("View email senders and their matched competitors. Emails are received via CloudMailin webhook.")

        # Load data from email_matcher module
        senders_df = get_all_senders()
        emails_df = load_emails_df()

        if senders_df.empty and emails_df.empty:
            st.info("No emails received yet. Configure CloudMailin to send emails to your webhook endpoint.")
        else:
            # Show summary metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                total_received = int(senders_df["emails_received"].sum()) if not senders_df.empty else 0
                st.metric("Total Received", total_received)
            with col2:
                total_processed = int(senders_df["emails_processed"].sum()) if not senders_df.empty else 0
                st.metric("Total Processed", total_processed)
            with col3:
                total_injected = int(senders_df["emails_injected"].sum()) if not senders_df.empty else 0
                st.metric("Total Injected", total_injected)
            with col4:
                unique_senders = len(senders_df)
                st.metric("Unique Senders", unique_senders)

            st.divider()

            # Sender statistics table with assignment capability
            st.subheader("Sender Statistics")

            if not senders_df.empty:
                # Display table
                display_df = senders_df[["from_address", "emails_received", "emails_processed", "emails_injected", "assigned_company", "last_seen"]].copy()
                display_df.columns = ["Email Address", "Received", "Processed", "Injected", "Assigned Company", "Last Seen"]

                def highlight_unassigned(val):
                    if not val or str(val).lower() == "nan" or val == "":
                        return "background-color: #fff3cd"
                    return ""

                styled_df = display_df.style.applymap(highlight_unassigned, subset=["Assigned Company"])
                st.dataframe(styled_df, use_container_width=True, hide_index=True)

                # Assignment section
                st.markdown("**Assign Sender to Company**")
                st.caption("Select a sender and assign them to a competitor. Future emails from that sender will auto-match.")

                competitor_options = ["(unassigned)"] + get_competitor_names()
                sender_options = senders_df["from_address"].tolist()

                col1, col2, col3 = st.columns([3, 2, 1])
                selected_sender = col1.selectbox("Sender", sender_options, key="assign_sender_select", label_visibility="collapsed", placeholder="Select sender...")

                # Get current assignment for selected sender
                current = senders_df[senders_df["from_address"] == selected_sender]["assigned_company"].values
                current_val = current[0] if len(current) > 0 and current[0] else ""
                default_idx = competitor_options.index(current_val) if current_val in competitor_options else 0

                selected_company = col2.selectbox("Company", competitor_options, index=default_idx, key="assign_company_select", label_visibility="collapsed")

                if col3.button("Save Assignment", key="save_sender_assignment"):
                    company_to_save = "" if selected_company == "(unassigned)" else selected_company
                    set_sender_assigned_company(selected_sender, company_to_save)
                    log_user_action("admin", "sender_assigned", f"{selected_sender} -> {company_to_save or 'unassigned'}")
                    st.success(f"Assigned: {selected_sender} → {selected_company}")
                    st.rerun()

                # Delete unassigned senders section
                st.markdown("**Delete Unassigned Sender**")
                st.caption("Remove senders that have no company assigned. This only deletes the sender record, not the emails.")

                # Filter to only unassigned senders
                unassigned_senders = senders_df[
                    (senders_df["assigned_company"].isna()) |
                    (senders_df["assigned_company"].astype(str).str.strip() == "") |
                    (senders_df["assigned_company"].astype(str).str.lower() == "nan")
                ]["from_address"].tolist()

                if unassigned_senders:
                    del_col1, del_col2 = st.columns([4, 1])
                    sender_to_delete = del_col1.selectbox(
                        "Sender to delete",
                        unassigned_senders,
                        key="delete_sender_select",
                        label_visibility="collapsed",
                        placeholder="Select unassigned sender..."
                    )
                    if del_col2.button("Delete Sender", key="delete_sender_btn", type="secondary"):
                        if delete_sender(sender_to_delete):
                            log_user_action("admin", "sender_deleted", sender_to_delete)
                            st.success(f"Deleted sender: {sender_to_delete}")
                            st.rerun()
                        else:
                            st.error("Failed to delete sender")
                else:
                    st.info("No unassigned senders to delete.")

            st.divider()

            # Recent emails table
            st.subheader("Recent Emails")
            if not emails_df.empty:
                from urllib.parse import quote

                # Filter out deleted emails
                if "status" in emails_df.columns:
                    inbox_emails = emails_df[emails_df["status"] != "deleted"]
                else:
                    inbox_emails = emails_df

                recent = inbox_emails.sort_values("received_at", ascending=False).head(20)
                display_cols = ["json_file", "from_address", "subject", "matched_company", "injected", "received_at"]
                display_cols = [c for c in display_cols if c in recent.columns]
                recent_display = recent[display_cols].copy()

                # Create clickable link to email viewer from json_file
                if "json_file" in recent_display.columns:
                    config_path = Path("config/monitors.yaml")
                    webhook_port = 8001
                    if config_path.exists():
                        try:
                            with open(config_path, "r", encoding="utf-8") as cfg_file:
                                cfg = yaml.safe_load(cfg_file) or {}
                                webhook_port = cfg.get("global", {}).get("webhook_port", 8001)
                        except Exception:
                            pass

                    def make_email_view_url(json_file):
                        if not json_file or pd.isna(json_file):
                            return ""
                        # Strip .json extension to get email_id
                        email_id = str(json_file).replace(".json", "")
                        email_id_encoded = quote(email_id, safe="")
                        return f"http://localhost:{webhook_port}/email/view/{email_id_encoded}"

                    recent_display["view_url"] = recent_display["json_file"].apply(make_email_view_url)
                    # Keep json_file for delete but don't show it - store separately
                    json_files_for_delete = recent["json_file"].tolist()

                    # Reorder to put view_url first, drop json_file from display
                    recent_display = recent_display.drop(columns=["json_file"])
                    cols_order = ["view_url"] + [c for c in recent_display.columns if c != "view_url"]
                    recent_display = recent_display[cols_order]
                    recent_display.columns = ["View", "From", "Subject", "Matched Company", "Injected", "Received"]

                    st.dataframe(
                        recent_display,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "View": st.column_config.LinkColumn("View", width="small", display_text="Open"),
                        },
                    )

                    # Delete email section
                    st.markdown("**Delete Email**")
                    st.caption("Move email to deleted folder and remove from feed. This cannot be undone.")

                    # Create options with subject for easier identification
                    email_options = []
                    for jf in json_files_for_delete:
                        row = recent[recent["json_file"] == jf].iloc[0]
                        subject = str(row.get("subject", ""))[:50]
                        email_options.append({"json_file": jf, "label": f"{subject}... ({jf[:30]}...)"})

                    if email_options:
                        del_email_col1, del_email_col2 = st.columns([4, 1])
                        selected_email_idx = del_email_col1.selectbox(
                            "Email to delete",
                            range(len(email_options)),
                            format_func=lambda i: email_options[i]["label"],
                            key="delete_email_select",
                            label_visibility="collapsed",
                        )
                        if del_email_col2.button("Delete Email", key="delete_email_btn", type="secondary"):
                            json_file_to_delete = email_options[selected_email_idx]["json_file"]
                            if delete_email(json_file_to_delete):
                                log_user_action("admin", "email_deleted", json_file_to_delete)
                                st.success(f"Deleted email: {email_options[selected_email_idx]['label']}")
                                st.rerun()
                            else:
                                st.error("Failed to delete email")
                else:
                    recent_display.columns = ["File", "From", "Subject", "Matched Company", "Injected", "Received"]
                    st.dataframe(recent_display, use_container_width=True, hide_index=True)
            else:
                st.info("No emails in log yet.")

            # Utility: Rebuild sender stats
            st.divider()
            with st.expander("Maintenance Tools"):
                st.caption("Use these tools to fix data inconsistencies.")
                if st.button("Rebuild Sender Stats", help="Recalculate sender statistics from emails.csv"):
                    rebuild_sender_stats()
                    log_user_action("admin", "rebuild_sender_stats", "Manual rebuild triggered")
                    st.success("Sender statistics rebuilt from emails.csv")
                    st.rerun()

    # ===================== DATA QUALITY TOOLS TAB =====================
    with settings_tab4:
        st.subheader("Enrichment")
        st.write("Run AI enrichment to add summaries, categories, and impact ratings to crawled articles.")

        # Count pending
        def _pending_enrichment_count(df_check: pd.DataFrame) -> int:
            cols = [c for c in ["summary", "category", "impact"] if c in df_check.columns]
            if not cols:
                return len(df_check)
            mask = False
            for c in cols:
                mask = mask | (df_check[c].astype(str).str.strip() == "")
            if "category" in df_check.columns:
                mask = mask & (df_check["category"] != "Uncategorized")
            return int(mask.sum())

        pending_count = _pending_enrichment_count(df) if not df.empty else 0
        st.metric("Articles Pending Enrichment", pending_count)

        if st.button("▶️ Run Enrichment Now", type="primary", key="settings_btn_enrich"):
            client_ip = get_client_ip()
            log_user_action(client_ip, "enrichment_start", "Started enrichment job")
            try:
                with st.spinner("Running enrichment job…"):
                    proc = subprocess.run(
                        [sys.executable, "-m", "jobs.enrich_updates"],
                        text=True,
                        capture_output=True,
                        cwd=os.getcwd(),
                    )
                if proc.returncode == 0:
                    st.success("✅ Enrichment complete!")
                    log_user_action(client_ip, "enrichment_complete", "Completed successfully")
                    if proc.stdout:
                        with st.expander("Output", expanded=False):
                            st.code(proc.stdout[-3000:], language="bash")
                else:
                    st.error("Enrichment failed")
                    log_user_action(client_ip, "enrichment_error", f"Exit code {proc.returncode}")
                    if proc.stderr:
                        st.code(proc.stderr[-3000:], language="bash")
            except Exception as e:
                st.error(f"Error: {e}")
                log_user_action(client_ip, "enrichment_error", str(e))
            finally:
                st.cache_data.clear()

        st.divider()

        st.subheader("QA Sampler")
        st.write("Download a random sample of enriched articles for quality review.")

        # Filter to enriched rows only
        qf = df.copy()
        if not qf.empty:
            for c in ["summary", "category", "impact"]:
                if c in qf.columns:
                    qf[c] = qf[c].astype(str)
            mask = (
                qf.get("summary", pd.Series([""])).str.strip().ne("") &
                qf.get("category", pd.Series([""])).str.strip().ne("") &
                qf.get("impact", pd.Series([""])).str.strip().ne("")
            )
            qf = qf[mask]

        if qf.empty:
            st.info("No enriched articles available for sampling.")
        else:
            st.metric("Enriched Articles Available", len(qf))

            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                fraction = st.slider("Sample %", 5, 30, 10, 1, key="settings_qa_fraction")
            with c2:
                min_rows = st.number_input("Min rows", 5, 100, 15, key="settings_qa_min")
            with c3:
                seed = st.number_input("Seed", 1, 9999, 42, key="settings_qa_seed")

            n = max(int(len(qf) * fraction / 100), int(min_rows))
            sample = qf.sample(n=min(n, len(qf)), random_state=int(seed)).copy()
            qa_cols = [c for c in ["date_ref", "company", "title", "category", "impact", "summary", "source_url"] if c in sample.columns]
            sample = sample[qa_cols]

            st.caption(f"Sample size: {len(sample)} articles")
            qa_fname = f"qa_sample_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%d_%H%M')}.csv"
            st.download_button(
                "📥 Download QA Sample",
                data=sample.to_csv(index=False).encode("utf-8"),
                file_name=qa_fname,
                mime="text/csv",
                key="settings_btn_qa_download",
            )

    # Stop here - don't render the main dashboard
    st.stop()

# =====================================================================
# MAIN DASHBOARD (shown when settings page is not active)
# =====================================================================

# --------------------------- Navigation (Tabs) ---------------------------
tab_dashboard, tab_export, tab_edits, tab_summary = st.tabs([
    "📊 Dashboard",
    "📥 Export",
    "✏️ Manual Edits",
    "📋 Executive Summary",
])

# --------------------------- Tab: Dashboard ---------------------------
with tab_dashboard:
    # KPIs
    col1, col2, col3 = st.columns(3)
    now_utc = pd.Timestamp.now(tz="UTC")
    last7 = f[(f["date_ref"] >= (now_utc - pd.Timedelta(days=7)))]
    highs = f[f.get("impact", "").astype(str).str.title().eq("High")] if "impact" in f else f.iloc[0:0]
    with col1:
        st.metric("New (last 7 days)", len(last7))
    with col2:
        st.metric("High-Impact", len(highs))
    with col3:
        st.metric("Active Competitors", f["company"].nunique())

    st.divider()
    st.subheader("Posts per Quarter by Competitor")

    # Determine available date range from data
    fq_all = f[f["date_ref"].notna()].copy()
    if not fq_all.empty:
        chart_min_date = fq_all["date_ref"].min()
        chart_max_date = fq_all["date_ref"].max()

        # Default to current year to date
        current_year_start = pd.Timestamp(f"{pd.Timestamp.now().year}-01-01", tz="UTC")
        default_start = max(chart_min_date, current_year_start)
        default_end = chart_max_date

        # Date picker for chart range
        chart_date_col1, chart_date_col2 = st.columns(2)
        with chart_date_col1:
            chart_start = st.date_input(
                "From",
                value=default_start.date() if pd.notna(default_start) else None,
                min_value=chart_min_date.date() if pd.notna(chart_min_date) else None,
                max_value=chart_max_date.date() if pd.notna(chart_max_date) else None,
                key="chart_date_from"
            )
        with chart_date_col2:
            chart_end = st.date_input(
                "To",
                value=default_end.date() if pd.notna(default_end) else None,
                min_value=chart_min_date.date() if pd.notna(chart_min_date) else None,
                max_value=chart_max_date.date() if pd.notna(chart_max_date) else None,
                key="chart_date_to"
            )

        # Filter data by selected chart date range
        fq = fq_all.copy()
        if chart_start and chart_end:
            chart_start_utc = pd.Timestamp(chart_start).tz_localize("UTC")
            chart_end_utc = pd.Timestamp(chart_end).tz_localize("UTC") + pd.Timedelta(days=1)
            fq = fq[(fq["date_ref"] >= chart_start_utc) & (fq["date_ref"] < chart_end_utc)]

            # Generate all quarters in the selected date range
            all_quarters = pd.period_range(
                start=pd.Timestamp(chart_start).to_period("Q"),
                end=pd.Timestamp(chart_end).to_period("Q"),
                freq="Q"
            ).astype(str).tolist()
        else:
            all_quarters = []

        # Get all companies from the full dataset for consistent colors
        all_companies = sorted(fq_all["company"].unique().tolist())

        if not fq.empty:
            try:
                fq["date_ref_naive"] = fq["date_ref"].dt.tz_convert("UTC").dt.tz_localize(None)
            except Exception:
                fq["date_ref_naive"] = fq["date_ref"].dt.tz_localize(None)

            fq["quarter"] = fq["date_ref_naive"].dt.to_period("Q").astype(str)
            g = fq.groupby(["quarter", "company"]).size().reset_index(name="posts")

            # Create complete grid of all quarters x all companies with zeros
            if all_quarters and all_companies:
                full_index = pd.MultiIndex.from_product([all_quarters, all_companies], names=["quarter", "company"])
                full_df = pd.DataFrame(index=full_index).reset_index()
                full_df["posts"] = 0
                # Merge actual data
                g = full_df.merge(g, on=["quarter", "company"], how="left", suffixes=("_default", ""))
                g["posts"] = g["posts"].fillna(g["posts_default"]).fillna(0).astype(int)
                g = g[["quarter", "company", "posts"]]

            g["_qsort"] = pd.PeriodIndex(g["quarter"], freq="Q")
            g = g.sort_values(["_qsort", "company"]).drop(columns=["_qsort"])

            try:
                import altair as alt
                chart = alt.Chart(g, height=280).mark_bar().encode(
                    x=alt.X("quarter:N", title="Quarter", sort=all_quarters if all_quarters else list(g["quarter"].unique())),
                    y=alt.Y("posts:Q", title="Posts"),
                    color=alt.Color("company:N", title="Company"),
                    tooltip=["quarter", "company", "posts"],
                )
                st.altair_chart(chart, use_container_width=True)
            except Exception:
                piv = g.pivot_table(index="quarter", columns="company", values="posts", fill_value=0)
                st.bar_chart(piv)
        elif all_quarters:
            # No data but show empty quarters
            st.info(f"No articles found in the selected date range ({all_quarters[0]} to {all_quarters[-1]}).")
        else:
            st.info("No rows in the selected date range.")
    else:
        st.info("No rows with a valid date in the current filter selection.")

    # Feed table
    st.divider()
    st.subheader("Feed")
    st.caption(f"Showing {len(f)} articles")

    show_cols = [c for c in ["date_ref", "company", "title", "category", "impact", "source_url", "summary"] if c in f.columns]
    sorted_f = f.sort_values(by=["date_ref"], ascending=False)
    display = sorted_f[show_cols].copy()

    if "date_ref" in display.columns:
        display["date_ref"] = pd.to_datetime(display["date_ref"], errors="coerce", utc=True).dt.strftime("%m-%d-%Y")

    for c in [c for c in ["category", "summary", "title", "company", "source_url", "impact"] if c in display.columns]:
        display[c] = display[c].astype(object).where(display[c].notna(), "")

    if "category" in display.columns:
        display["category"] = display["category"].apply(lambda s: s if str(s).strip() else "Uncategorized")

    # Transform email:// URLs to actual HTTP links for the email viewer
    if "source_url" in display.columns:
        from urllib.parse import quote
        config_path = Path("config/monitors.yaml")
        webhook_port = 8001
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as cfg_file:
                    cfg = yaml.safe_load(cfg_file) or {}
                    webhook_port = cfg.get("global", {}).get("webhook_port", 8001)
            except Exception:
                pass

        def transform_email_url(url):
            url = str(url).strip()
            if url.startswith("email://"):
                email_id = url.replace("email://", "")
                email_id_encoded = quote(email_id, safe="")
                return f"http://localhost:{webhook_port}/email/view/{email_id_encoded}"
            return url

        display["source_url"] = display["source_url"].apply(transform_email_url)

    # Reorder and prepare columns for display
    ui_cols = [c for c in ["date_ref", "company", "title", "category", "impact", "summary", "source_url"] if c in display.columns]
    display = display[ui_cols]

    # Use st.dataframe with column configuration for proper scrollable table
    st.dataframe(
        display,
        use_container_width=True,
        height=400,
        column_config={
            "date_ref": st.column_config.TextColumn("Date", width="small"),
            "company": st.column_config.TextColumn("Company", width="small"),
            "title": st.column_config.TextColumn("Title", width="medium"),
            "category": st.column_config.TextColumn("Category", width="small"),
            "impact": st.column_config.TextColumn("Impact", width="small"),
            "summary": st.column_config.TextColumn("Summary", width="large"),
            "source_url": st.column_config.LinkColumn("Link", width="small", display_text="Open"),
        },
        hide_index=True,
    )

# --------------------------- Tab: Export ---------------------------
with tab_export:
    st.subheader("Export Current View")
    export_cols = [c for c in ["date_ref","company","title","category","impact","source_url","summary"] if c in f.columns]
    export_df = f.sort_values(by=["date_ref"], ascending=False)[export_cols].copy()
    if "date_ref" in export_df.columns:
        export_df["date_ref"] = pd.to_datetime(export_df["date_ref"], errors="coerce", utc=True).dt.strftime("%m-%d-%Y")
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    fname = f"competitor_updates_{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}.csv"
    if st.download_button("Download filtered rows as CSV", data=csv_bytes, file_name=fname, mime="text/csv", key="btn_export_csv"):
        log_user_action(get_client_ip(), "export_csv", f"Exported {len(export_df)} rows to CSV")

# --------------------------- Tab: Manual Edits ---------------------------
with tab_edits:
    st.subheader("Manual Edit (Summary, Category, Impact)")
    _edit_cols = [c for c in ["summary", "category", "impact"] if c in f.columns]
    _key_cols  = [c for c in ["company", "source_url"] if c in f.columns]

    if len(_key_cols) < 2:
        st.info("Editing is disabled because we need both 'company' and 'source_url' columns to match rows.")
    else:
        edit_view = f[_key_cols + _edit_cols].copy()
        for c in _edit_cols:
            edit_view[c] = edit_view[c].astype(object).where(edit_view[c].notna(), "")

        st.caption("Tip: Filter above first, then edit only the rows you care about. Your changes save back to the enriched CSV.")
        edited = st.data_editor(
            edit_view,
            use_container_width=True,
            num_rows="dynamic",
            key="data_editor_enrichment",
            column_config={
                "impact": st.column_config.SelectboxColumn(
                    "impact",
                    help="Allowed values: High, Medium, Low",
                    options=["High", "Medium", "Low"],
                    required=False,
                ),
            },
        )

        if st.button("Save Edits to Enriched File", type="primary", key="btn_save_edits"):
            client_ip = get_client_ip()
            try:
                ENRICHED_PATH = "data/enriched_updates.csv"
                RAW_PATH = "data/updates.csv"

                base_path = ENRICHED_PATH if os.path.exists(ENRICHED_PATH) else RAW_PATH
                base_df = pd.read_csv(base_path)

                for k in _key_cols:
                    if k not in base_df.columns:
                        base_df[k] = ""
                for c in _edit_cols:
                    if c not in base_df.columns:
                        base_df[c] = ""

                for c in _key_cols + _edit_cols:
                    if c in edited.columns:
                        edited[c] = edited[c].astype(str)

                if "impact" in edited.columns:
                    allowed = {"High", "Medium", "Low", ""}
                    edited["impact"] = edited["impact"].apply(lambda x: x if x in allowed else "")

                left  = base_df.set_index(_key_cols)
                right = edited.set_index(_key_cols)[_edit_cols]
                left.update(right)
                merged_out = left.reset_index()

                tmp_path = ENRICHED_PATH + ".tmp"
                merged_out.to_csv(tmp_path, index=False, encoding="utf-8")
                os.replace(tmp_path, ENRICHED_PATH)

                st.success(f"Saved edits to {ENRICHED_PATH}")
                log_user_action(client_ip, "manual_edit", f"Saved manual edits to {ENRICHED_PATH}")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Failed to save edits: {e}")
                log_user_action(client_ip, "edit_error", f"Failed to save edits: {e}")

# --------------------------- Tab: Executive Summary ---------------------------
with tab_summary:
    # Build date range label from ACTUAL filtered data (not sidebar widget defaults)
    dr_label = ""
    if not f.empty and "date_ref" in f.columns and f["date_ref"].notna().any():
        actual_min = f["date_ref"].min()
        actual_max = f["date_ref"].max()
        if pd.notna(actual_min) and pd.notna(actual_max):
            dr_label = f"{actual_min:%b %d, %Y} – {actual_max:%b %d, %Y}"

    st.subheader("Executive Summary")
    if dr_label:
        st.caption(f"📅 Date range: **{dr_label}** ({len(f)} articles from {f['company'].nunique() if not f.empty else 0} competitors)")

    if "exec_blocks" not in st.session_state:
        st.session_state["exec_blocks"] = None

    cc1, cc2 = st.columns([1, 1])
    with cc1:
        gen_click = st.button("Generate Executive Summary", key="btn_exec_generate")
    with cc2:
        if st.session_state["exec_blocks"]:
            pdf_bytes = exec_blocks_to_pdf(st.session_state["exec_blocks"], dr_label)
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=f"exec_summary_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%d_%H%M')}.pdf",
                mime="application/pdf",
                key="btn_exec_pdf",
            )
        else:
            st.download_button(
                "Download PDF",
                data=b"",
                file_name="exec_summary.pdf",
                mime="application/pdf",
                disabled=True,
                key="btn_exec_pdf_disabled",
            )

    if gen_click:
        # Build blocks from the CURRENT filtered frame (f)
        log_user_action(get_client_ip(), "exec_summary_gen", f"Generating executive summary for {len(f)} rows")

        # Check if there's data to process
        companies = f["company"].nunique() if not f.empty else 0
        if companies == 0:
            st.warning("No data to generate summary from. Try adjusting your filters.")
        else:
            # Show progress bar
            progress_bar = st.progress(0, text="Starting...")
            status_text = st.empty()

            def update_progress(current, total, company_name):
                if total > 0:
                    progress = current / total
                    progress_bar.progress(progress, text=f"Processing {current}/{total} companies...")
                    status_text.text(f"Summarizing: {company_name}")

            blocks = build_exec_blocks(f, max_highlights=3, progress_callback=update_progress)
            st.session_state["exec_blocks"] = blocks

            # Clear progress indicators
            progress_bar.empty()
            status_text.empty()

            log_user_action(get_client_ip(), "exec_summary_done", f"Generated {len(blocks)} company summaries")
            st.success(f"Generated summaries for {len(blocks)} companies!")
            st.rerun()

    if st.session_state["exec_blocks"]:
        for b in st.session_state["exec_blocks"]:
            with st.container():
                st.markdown(f"### {b['company']}")
                st.caption(
                    f"{b['posts']} posts during {dr_label}"
                    if dr_label else f"{b['posts']} posts"
                )
                st.write(
                    f"**Impact mix:** High: {b['impact']['High']} • "
                    f"Medium: {b['impact']['Medium']} • Low: {b['impact']['Low']}"
                )
                if b.get("top_topics"):
                    topics_str = ", ".join(f"{name} ({cnt})" for name, cnt in b["top_topics"])
                    st.write(f"**Top topics:** {topics_str}")
                if b.get("highlights"):
                    st.write("**Highlights:**")
                    for t in b["highlights"]:
                        st.markdown(f"- {t}")

