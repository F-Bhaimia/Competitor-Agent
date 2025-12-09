# streamlit_app/Home.py
import os
import sys
import subprocess
import signal
import time
from html import escape
import re
from collections import Counter
from io import BytesIO

import pandas as pd
import streamlit as st
from openai import OpenAI

from app.logger import (
    get_system_logger,
    log_startup,
    log_user_action,
    init_client_ip,
    get_client_ip,
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

# --------------------------- Header with Scan Button ---------------------------
header_col1, header_col2 = st.columns([4, 1])

with header_col1:
    st.title("Competitor Analysis")

with header_col2:
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
@st.cache_data(show_spinner=False)
def load_data():
    """Load enriched if present, else raw; normalize timestamps and required cols."""
    path = DATA_ENRICHED if os.path.exists(DATA_ENRICHED) else DATA_RAW
    df = pd.read_csv(path)

    # Normalize datetimes as UTC-aware
    for col in ["published_at", "collected_at"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

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

    # Unified reference date: prefer published_at, fallback to collected_at
    pub = df.get("published_at")
    col = df.get("collected_at")
    if pub is not None or col is not None:
        df["date_ref"] = pd.to_datetime(
            (pub.where(pub.notna(), col) if pub is not None else col),
            errors="coerce",
            utc=True,
        )
    else:
        df["date_ref"] = pd.NaT

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
    t = escape((title or "").strip() or "View")
    u = (url or "").strip()
    if not u:
        return t
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

def summarize_point(text: str, max_words: int = 50) -> str:
    """Uses GPT to generate a clean 1–2 sentence summary (~50 words)."""
    text = (text or "").strip()
    if not text:
        return ""
    prompt = (
        f"Summarize the following news or blog content in a single concise paragraph "
        f"of about {max_words} words. Make it clear, factual, and self-contained:\n\n{text}"
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            max_tokens=120,
            messages=[
                {"role": "system", "content": "You are a professional business summarizer."},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("Summarization failed:", e)
        return text[:300]  # fallback

def build_exec_blocks(filtered_df: pd.DataFrame, max_highlights: int = 3):
    """Create structured summary blocks from the current filtered data."""
    blocks = []
    if filtered_df.empty:
        return blocks

    for company, g in filtered_df.groupby("company"):
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
date_from, date_to = st.sidebar.date_input(
    "Date range",
    value=(min_date.date() if pd.notna(min_date) else None,
           max_date.date() if pd.notna(max_date) else None),
)

query = st.sidebar.text_input("Search title/summary...", "")

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

# --------------------------- Navigation (Menu) ---------------------------
SECTION_LABELS = [
    "Posts by Competitor",  # KPIs + chart + feed
    "Export",               # Download filtered CSV
    "Manual Edits",         # editable grid
    "Executive Summary",    # Generate + Download PDF
    "Data Quality Tools",   # Enrichment + QA together
    "Config",               # Configuration settings
]

# Track previous menu selection
if "prev_menu" not in st.session_state:
    st.session_state.prev_menu = None

menu = st.radio(
    "Navigation",
    SECTION_LABELS,
    horizontal=True,
    key="top_menu_radio",
)

# Log navigation changes
if st.session_state.prev_menu != menu:
    if st.session_state.prev_menu is not None:  # Don't log initial load
        log_user_action(get_client_ip(), "navigation", f"Navigated to: {menu}")
        logger.debug(f"Navigation: {st.session_state.prev_menu} -> {menu}")
    st.session_state.prev_menu = menu

# --------------------------- Section: Posts by Competitor ---------------------------
if menu == "Posts by Competitor":
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

    fq = f.copy()
    fq = fq[fq["date_ref"].notna()].copy()
    if not fq.empty:
        try:
            fq["date_ref_naive"] = fq["date_ref"].dt.tz_convert("UTC").dt.tz_localize(None)
        except Exception:
            fq["date_ref_naive"] = fq["date_ref"].dt.tz_localize(None)

        fq["quarter"] = fq["date_ref_naive"].dt.to_period("Q").astype(str)
        g = fq.groupby(["quarter", "company"]).size().reset_index(name="posts")
        g["_qsort"] = pd.PeriodIndex(g["quarter"], freq="Q")
        g = g.sort_values(["_qsort", "company"]).drop(columns=["_qsort"])

        try:
            import altair as alt
            base = alt.Chart(g, height=280)
            view_mode = st.radio("View", ("Grouped", "Stacked"), horizontal=True, key="view_mode_chart")
            if view_mode == "Grouped":
                chart = base.mark_bar().encode(
                    x=alt.X("company:N", title="Company"),
                    y=alt.Y("posts:Q", title="Posts"),
                    color=alt.Color("company:N", title="Company"),
                    column=alt.Column("quarter:N", title="Quarter", header=alt.Header(labelAngle=0)),
                )
            else:
                chart = base.mark_bar().encode(
                    x=alt.X("quarter:N", title="Quarter", sort=list(g["quarter"].unique())),
                    y=alt.Y("posts:Q", title="Posts"),
                    color=alt.Color("company:N", title="Company"),
                    tooltip=["quarter", "company", "posts"],
                )
            st.altair_chart(chart, use_container_width=True)
        except Exception:
            piv = g.pivot_table(index="quarter", columns="company", values="posts", fill_value=0)
            st.bar_chart(piv)
    else:
        st.info("No rows with a valid date in the current filter selection.")

    # Feed table
    st.divider()
    st.subheader("Feed")
    st.write("Click a title to open the source; summaries appear if enrichment is complete.")

    show_cols = [c for c in ["date_ref", "company", "title", "category", "impact", "source_url", "summary"] if c in f.columns]
    sorted_f = f.sort_values(by=["date_ref"], ascending=False)
    display = sorted_f[show_cols].copy()

    if "date_ref" in display.columns:
        display["date_ref"] = pd.to_datetime(display["date_ref"], errors="coerce", utc=True).dt.strftime("%m-%d-%Y")

    for c in [c for c in ["category", "summary", "title", "company", "source_url", "impact"] if c in display.columns]:
        display[c] = display[c].astype(object).where(display[c].notna(), "")

    if "category" in display.columns:
        display["category"] = display["category"].apply(lambda s: s if str(s).strip() else "Uncategorized")

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

    if "impact" in display.columns:
        display["impact"] = display["impact"].apply(impact_badge)

    st.markdown(
        display.to_html(escape=False, index=False)
        .replace('<table', '<table style="word-wrap:break-word;white-space:normal;table-layout:fixed;width:100%;"')
        .replace('<td', '<td style="word-wrap:break-word;white-space:normal;"'),
        unsafe_allow_html=True,
    )

# --------------------------- Section: Export ---------------------------
elif menu == "Export":
    st.subheader("Export Current View")
    export_cols = [c for c in ["date_ref","company","title","category","impact","source_url","summary"] if c in f.columns]
    export_df = f.sort_values(by=["date_ref"], ascending=False)[export_cols].copy()
    if "date_ref" in export_df.columns:
        export_df["date_ref"] = pd.to_datetime(export_df["date_ref"], errors="coerce", utc=True).dt.strftime("%m-%d-%Y")
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    fname = f"competitor_updates_{pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d')}.csv"
    if st.download_button("Download filtered rows as CSV", data=csv_bytes, file_name=fname, mime="text/csv", key="btn_export_csv"):
        log_user_action(get_client_ip(), "export_csv", f"Exported {len(export_df)} rows to CSV")

# --------------------------- Section: Data Quality Tools (Advanced) ---------------------------
elif menu == "Data Quality Tools":
    st.subheader("Data Quality Tools")

    with st.expander("Enrichment", expanded=False):
        def _pending_enrichment_count(df_disp: pd.DataFrame) -> int:
            cols = [c for c in ["summary", "category", "impact"] if c in df_disp.columns]
            if not cols:
                return len(df_disp)
            mask = False
            for c in cols:
                mask = mask | (df_disp[c].astype(str).str.strip() == "")
            # don't count defaulted Uncategorized as pending
            if "category" in df_disp.columns:
                mask = mask & (df_disp["category"] != "Uncategorized")
            return int(mask.sum())

        # Build a minimal display to count pending
        show_cols = [c for c in ["date_ref", "company", "title", "category", "impact", "source_url", "summary"] if c in f.columns]
        sorted_f = f.sort_values(by=["date_ref"], ascending=False)
        display = sorted_f[show_cols].copy() if show_cols else sorted_f.copy()

        st.caption(f"Pending in current view: {_pending_enrichment_count(display) if not display.empty else 0}")

        if st.button("Run Enrichment Now", type="primary", key="btn_enrich_now_adv"):
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
                    st.success("Enrichment complete")
                    log_user_action(client_ip, "enrichment_complete", "Enrichment completed successfully")
                    if proc.stdout:
                        st.code(proc.stdout[-3000:], language="bash")
                else:
                    st.error("Enrichment failed")
                    log_user_action(client_ip, "enrichment_error", f"Enrichment failed: exit code {proc.returncode}")
                    if proc.stderr:
                        st.code(proc.stderr[-3000:], language="bash")
            except Exception as e:
                st.error(f"Error launching enrichment: {e}")
                log_user_action(client_ip, "enrichment_error", f"Error launching enrichment: {e}")
            finally:
                st.cache_data.clear()
                st.rerun()

    with st.expander("QA Sampler", expanded=False):
        qf = f.copy()
        if not qf.empty:
            for c in ["summary", "category", "impact", "title", "company", "source_url"]:
                if c in qf.columns:
                    qf[c] = qf[c].astype(str)

            mask = (
                qf.get("summary", "").str.strip().ne("") &
                qf.get("category", "").str.strip().ne("") &
                qf.get("impact", "").str.strip().ne("")
            )
            qf = qf[mask]

        if qf.empty:
            st.info("No enriched rows in the current filters.")
        else:
            c1, c2, c3 = st.columns([1, 1, 1])
            with c1:
                fraction = st.slider("Fraction", 0.05, 0.30, 0.10, 0.01, key="qa_fraction")
            with c2:
                min_rows = st.number_input("Min rows", 5, 100, 15, key="qa_min_rows")
            with c3:
                seed = st.number_input("Seed", 1, 9999, 42, key="qa_seed")

            n = max(int(len(qf) * fraction), int(min_rows))
            sample = qf.sample(n=min(n, len(qf)), random_state=int(seed)).copy()
            qa_cols = [c for c in ["date_ref","company","title","category","impact","summary","source_url"] if c in sample.columns]
            sample = sample[qa_cols]
            st.caption(f"Sample size: {len(sample)}")
            qa_fname = f"qa_sample_{pd.Timestamp.now(tz='UTC').strftime('%Y%m%d_%H%M')}.csv"
            st.download_button(
                "Download QA sample",
                data=sample.to_csv(index=False).encode("utf-8"),
                file_name=qa_fname,
                mime="text/csv",
                key="btn_qa_csv_adv",
            )

# --------------------------- Section: Manual Edits ---------------------------
elif menu == "Manual Edits":
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

# --------------------------- Section: Executive Summary ---------------------------
elif menu == "Executive Summary":
    st.subheader("Executive Summary")

    if "exec_blocks" not in st.session_state:
        st.session_state["exec_blocks"] = None

    cc1, cc2 = st.columns([1, 1])
    with cc1:
        gen_click = st.button("Generate Executive Summary", key="btn_exec_generate")
    with cc2:
        if st.session_state["exec_blocks"]:
            dr_label = ""
            if date_from and date_to:
                dr_label = f"{pd.Timestamp(date_from):%b %d, %Y} – {pd.Timestamp(date_to):%b %d, %Y}"
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
        blocks = build_exec_blocks(f, max_highlights=3)
        st.session_state["exec_blocks"] = blocks
        log_user_action(get_client_ip(), "exec_summary_done", f"Generated {len(blocks)} company summaries")

    if st.session_state["exec_blocks"]:
        for b in st.session_state["exec_blocks"]:
            with st.container():
                st.markdown(f"### {b['company']}")
                st.caption(
                    f"{b['posts']} posts during "
                    f"{pd.Timestamp(date_from):%b %d, %Y} – {pd.Timestamp(date_to):%b %d, %Y}"
                    if (date_from and date_to) else f"{b['posts']} posts"
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

# --------------------------- Section: Config ---------------------------
elif menu == "Config":
    import yaml
    import copy

    st.subheader("Configuration Settings")
    st.caption("Edit application settings stored in `config/monitors.yaml`")

    CONFIG_PATH = "config/monitors.yaml"

    # Load config from file (no caching - always fresh)
    def load_yaml_config():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            st.error(f"Failed to load config: {e}")
            return None

    # Initialize session state for config editing
    if "config_competitors" not in st.session_state:
        config = load_yaml_config()
        if config:
            st.session_state.config_competitors = copy.deepcopy(config.get("competitors", []))
            st.session_state.config_loaded = True
        else:
            st.session_state.config_competitors = []
            st.session_state.config_loaded = False

    config = load_yaml_config()

    if config:
        # Global Settings
        with st.expander("Global Settings", expanded=True):
            st.markdown("**Logging & Crawl Settings**")

            col1, col2 = st.columns(2)

            with col1:
                # Log level
                current_log_level = config.get("global", {}).get("log_level", "INFO")
                log_level_options = ["DEBUG", "INFO", "WARNING", "ERROR"]
                try:
                    log_level_index = log_level_options.index(current_log_level.upper())
                except ValueError:
                    log_level_index = 1  # Default to INFO
                new_log_level = st.selectbox(
                    "Log Level",
                    options=log_level_options,
                    index=log_level_index,
                    help="DEBUG: Verbose logging for troubleshooting. INFO: Normal operation.",
                    key="cfg_log_level"
                )

                # Request timeout
                current_timeout = config.get("global", {}).get("request_timeout_s", 20)
                new_timeout = st.number_input(
                    "Request Timeout (seconds)",
                    min_value=5,
                    max_value=120,
                    value=int(current_timeout),
                    help="How long to wait for a page to load before giving up.",
                    key="cfg_timeout"
                )

            with col2:
                # Max pages per site
                current_max_pages = config.get("global", {}).get("max_pages_per_site", 60)
                new_max_pages = st.number_input(
                    "Max Pages Per Site",
                    min_value=10,
                    max_value=500,
                    value=int(current_max_pages),
                    help="Maximum number of pages to crawl per competitor.",
                    key="cfg_max_pages"
                )

                # Dedupe window
                current_dedupe = config.get("global", {}).get("dedupe_window_days", 365)
                new_dedupe = st.number_input(
                    "Dedupe Window (days)",
                    min_value=30,
                    max_value=730,
                    value=int(current_dedupe),
                    help="Days to look back for duplicate detection.",
                    key="cfg_dedupe"
                )

            # User agent
            current_ua = config.get("global", {}).get("user_agent", "")
            new_ua = st.text_input(
                "User Agent",
                value=current_ua,
                help="The user agent string sent when crawling websites.",
                key="cfg_user_agent"
            )

            # Follow within domain only
            current_follow = config.get("global", {}).get("follow_within_domain_only", True)
            new_follow = st.checkbox(
                "Follow Within Domain Only",
                value=current_follow,
                help="Only follow links that stay within the competitor's domain.",
                key="cfg_follow_domain"
            )

        # Competitors Management
        with st.expander("Competitors", expanded=True):
            st.markdown("**Monitored Competitors**")
            st.caption(f"Currently monitoring {len(st.session_state.config_competitors)} competitors")

            # Build list of competitors from session state with editable fields
            updated_competitors = []
            for i, comp in enumerate(st.session_state.config_competitors):
                with st.container():
                    col1, col2, col3 = st.columns([2, 3, 0.5])
                    with col1:
                        new_name = st.text_input(
                            "Name" if i == 0 else f"Name {i+1}",
                            value=comp.get("name", ""),
                            key=f"comp_name_{i}",
                            label_visibility="visible" if i == 0 else "collapsed"
                        )
                    with col2:
                        urls_str = "\n".join(comp.get("start_urls", []))
                        new_urls_str = st.text_area(
                            "Start URLs (one per line)" if i == 0 else f"URLs {i+1}",
                            value=urls_str,
                            height=68,
                            key=f"comp_urls_{i}",
                            label_visibility="visible" if i == 0 else "collapsed"
                        )
                    with col3:
                        st.write("")  # Spacing
                        if st.button("🗑️", key=f"del_comp_{i}", help=f"Remove {comp.get('name', 'competitor')}"):
                            st.session_state.config_competitors.pop(i)
                            st.rerun()

                    # Update the competitor data
                    if new_name.strip():
                        updated_competitors.append({
                            "name": new_name.strip(),
                            "start_urls": [u.strip() for u in new_urls_str.strip().split("\n") if u.strip()]
                        })
                    st.divider()

            # Update session state with edited values
            st.session_state.config_competitors = updated_competitors

            # Add new competitor section
            st.markdown("**Add New Competitor**")
            new_comp_col1, new_comp_col2 = st.columns([2, 3])
            with new_comp_col1:
                new_comp_name = st.text_input(
                    "New Competitor Name",
                    value="",
                    key="new_comp_name",
                    placeholder="e.g., Acme Corp"
                )
            with new_comp_col2:
                new_comp_urls = st.text_area(
                    "Start URLs (one per line)",
                    value="",
                    key="new_comp_urls",
                    height=68,
                    placeholder="https://example.com/blog"
                )

            if st.button("➕ Add Competitor", key="btn_add_competitor"):
                if new_comp_name.strip() and new_comp_urls.strip():
                    new_urls_list = [u.strip() for u in new_comp_urls.strip().split("\n") if u.strip()]
                    if new_urls_list:
                        st.session_state.config_competitors.append({
                            "name": new_comp_name.strip(),
                            "start_urls": new_urls_list
                        })
                        st.success(f"Added '{new_comp_name}' - click Save Configuration to persist changes")
                        st.rerun()
                else:
                    st.warning("Please enter both a name and at least one URL.")

        # Alert Settings
        with st.expander("Alert Settings", expanded=False):
            st.markdown("**Impact & Alert Configuration**")

            # High impact labels
            current_high_impact = config.get("global", {}).get("high_impact_labels", [])
            new_high_impact = st.text_area(
                "High Impact Labels (one per line)",
                value="\n".join(current_high_impact),
                height=100,
                help="Categories considered high impact.",
                key="cfg_high_impact"
            )

            # Alert on impact levels
            current_alert_levels = config.get("global", {}).get("alert_on_impact_levels", ["High"])
            new_alert_levels = st.multiselect(
                "Alert on Impact Levels",
                options=["High", "Medium", "Low"],
                default=[lvl for lvl in current_alert_levels if lvl in ["High", "Medium", "Low"]],
                help="Which impact levels should trigger alerts.",
                key="cfg_alert_levels"
            )

        # Save Configuration
        st.divider()
        col_save, col_reset = st.columns([1, 1])

        with col_save:
            if st.button("💾 Save Configuration", type="primary", key="btn_save_config"):
                try:
                    # Build updated config from current form values
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

                    # Write to file with atomic replace
                    tmp_path = CONFIG_PATH + ".tmp"
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        yaml.dump(updated_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                    os.replace(tmp_path, CONFIG_PATH)

                    log_user_action(get_client_ip(), "config_save", f"Saved config: {len(st.session_state.config_competitors)} competitors")
                    logger.info(f"Configuration saved: log_level={new_log_level}, max_pages={new_max_pages}, competitors={len(st.session_state.config_competitors)}")

                    st.success(f"Configuration saved to {CONFIG_PATH}!")

                    # Reload log level dynamically
                    from app.logger import set_log_level
                    set_log_level(new_log_level)

                except Exception as e:
                    st.error(f"Failed to save configuration: {e}")
                    logger.error(f"Config save failed: {e}")
                    log_user_action(get_client_ip(), "config_error", f"Failed to save: {e}")

        with col_reset:
            if st.button("🔄 Reload from File", key="btn_reload_config"):
                # Clear session state and reload from file
                if "config_competitors" in st.session_state:
                    del st.session_state.config_competitors
                st.rerun()

        # View Raw YAML (current file on disk)
        with st.expander("View Raw YAML (current file)", expanded=False):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    current_yaml = f.read()
                st.code(current_yaml, language="yaml")
            except Exception as e:
                st.error(f"Could not read config file: {e}")

render_feed(f)
