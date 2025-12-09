"""
Centralized logging configuration for Competitor News Monitor.

Two log files:
- system.log: Application startup, scanning activity, job execution
- usage.log: User interactions with the Streamlit dashboard (IP-identified)

Log level is configurable via config/monitors.yaml:
  global:
    log_level: "INFO"  # or "DEBUG" for verbose output
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import yaml

# Log directory setup
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Config file path
CONFIG_PATH = Path(__file__).parent.parent / "config" / "monitors.yaml"

# Log file paths
SYSTEM_LOG_FILE = LOG_DIR / "system.log"
USAGE_LOG_FILE = LOG_DIR / "usage.log"

# Log format strings
SYSTEM_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
USAGE_FORMAT = "%(asctime)s | %(levelname)-8s | %(ip)-15s | %(action)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Max log file size (10MB) and backup count
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5


def _get_log_level_from_config() -> int:
    """
    Read log level from config/monitors.yaml.

    Returns logging.INFO by default, or logging.DEBUG if configured.
    Valid values: DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            if cfg and "global" in cfg:
                level_str = cfg["global"].get("log_level", "INFO").upper()
                return getattr(logging, level_str, logging.INFO)
    except Exception:
        pass
    return logging.INFO


# Cache the log level at module load time
_CONFIG_LOG_LEVEL = _get_log_level_from_config()


def get_current_log_level() -> str:
    """Return the current log level name (e.g., 'INFO', 'DEBUG')."""
    return logging.getLevelName(_CONFIG_LOG_LEVEL)


def set_log_level(level: str) -> None:
    """
    Change the log level at runtime.

    Args:
        level: One of 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'

    Note: This only affects new log messages. To persist the change,
    update config/monitors.yaml.
    """
    global _CONFIG_LOG_LEVEL
    new_level = getattr(logging, level.upper(), logging.INFO)
    _CONFIG_LOG_LEVEL = new_level

    # Update existing handlers if logger is already initialized
    if _system_logger is not None:
        for handler in _system_logger.handlers:
            handler.setLevel(new_level)
        _system_logger.info(f"Log level changed to {level.upper()}")


def _create_handler(
    log_file: Path,
    formatter: logging.Formatter,
    level: int = logging.INFO
) -> RotatingFileHandler:
    """Create a rotating file handler with the specified settings."""
    handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8"
    )
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler


# =============================================================================
# SYSTEM LOGGER
# =============================================================================

_system_logger: Optional[logging.Logger] = None


def get_system_logger(name: str = "system") -> logging.Logger:
    """
    Get the system logger for application events.

    Log level is controlled by config/monitors.yaml:
      global:
        log_level: "INFO"  # or "DEBUG"

    Usage:
        from app.logger import get_system_logger
        logger = get_system_logger(__name__)
        logger.info("Starting daily scan")
        logger.error("Failed to fetch URL", exc_info=True)

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance
    """
    global _system_logger

    # Create root system logger if not exists
    if _system_logger is None:
        _system_logger = logging.getLogger("competitor_agent")
        _system_logger.setLevel(logging.DEBUG)  # Capture all, filter at handler level

        # File handler - uses configured log level
        file_formatter = logging.Formatter(SYSTEM_FORMAT, DATE_FORMAT)
        file_handler = _create_handler(SYSTEM_LOG_FILE, file_formatter, level=_CONFIG_LOG_LEVEL)
        _system_logger.addHandler(file_handler)

        # Console handler - uses configured log level
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(file_formatter)
        console_handler.setLevel(_CONFIG_LOG_LEVEL)
        _system_logger.addHandler(console_handler)

        # Prevent propagation to root logger
        _system_logger.propagate = False

        # Log the current configuration
        level_name = logging.getLevelName(_CONFIG_LOG_LEVEL)
        _system_logger.info(f"Logging initialized at {level_name} level")

    # Return child logger with the given name
    return logging.getLogger(f"competitor_agent.{name}")


# =============================================================================
# USAGE LOGGER (with IP tracking)
# =============================================================================

class UsageLogAdapter(logging.LoggerAdapter):
    """Custom adapter that adds IP and action context to log records."""

    def process(self, msg, kwargs):
        # Get IP and action from extra, with defaults
        extra = kwargs.get("extra", {})
        extra["ip"] = extra.get("ip", "unknown")
        extra["action"] = extra.get("action", "general")
        kwargs["extra"] = extra
        return msg, kwargs


class UsageFormatter(logging.Formatter):
    """Custom formatter for usage logs with IP and action fields."""

    def format(self, record):
        # Ensure ip and action attributes exist
        if not hasattr(record, "ip"):
            record.ip = "unknown"
        if not hasattr(record, "action"):
            record.action = "general"
        return super().format(record)


_usage_logger: Optional[logging.Logger] = None


def get_usage_logger() -> UsageLogAdapter:
    """
    Get the usage logger for tracking user interactions.

    Usage:
        from app.logger import get_usage_logger
        usage_log = get_usage_logger()
        usage_log.info("Viewed dashboard", extra={"ip": "192.168.1.1", "action": "page_view"})
        usage_log.info("Started scan", extra={"ip": client_ip, "action": "scan_start"})

    Returns:
        Logger adapter with IP/action context support
    """
    global _usage_logger

    if _usage_logger is None:
        _usage_logger = logging.getLogger("competitor_agent_usage")
        _usage_logger.setLevel(logging.INFO)

        # File handler with custom formatter
        formatter = UsageFormatter(USAGE_FORMAT, DATE_FORMAT)
        file_handler = _create_handler(USAGE_LOG_FILE, formatter)
        _usage_logger.addHandler(file_handler)

        # Prevent propagation
        _usage_logger.propagate = False

    return UsageLogAdapter(_usage_logger, {})


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def log_startup(component: str, version: str = "1.0.0"):
    """Log application component startup."""
    logger = get_system_logger("startup")
    logger.info("=" * 60)
    logger.info(f"STARTUP: {component} v{version}")
    logger.info(f"PID: {os.getpid()}")
    logger.info(f"Log directory: {LOG_DIR}")
    logger.info("=" * 60)


def log_scan_start(competitor_count: int, config: dict = None):
    """Log the start of a scanning job."""
    logger = get_system_logger("scan")
    logger.info(f"Scan started: {competitor_count} competitors to process")
    if config:
        logger.info(f"Config: max_pages={config.get('max_pages_per_site', 'N/A')}, "
                   f"timeout={config.get('request_timeout_s', 'N/A')}s")


def log_scan_progress(company: str, pages_found: int, articles_new: int):
    """Log progress during a scan."""
    logger = get_system_logger("scan")
    logger.info(f"[{company}] Found {pages_found} pages, {articles_new} new articles")


def log_scan_complete(total_articles: int, new_articles: int, duration_seconds: float):
    """Log scan completion with summary."""
    logger = get_system_logger("scan")
    logger.info(f"Scan complete: {new_articles}/{total_articles} new articles "
               f"in {duration_seconds:.1f}s")


def log_scan_error(company: str, url: str, error: Exception):
    """Log a scan error."""
    logger = get_system_logger("scan")
    logger.error(f"[{company}] Error fetching {url}: {error}", exc_info=True)


def log_enrichment_start(article_count: int):
    """Log enrichment job start."""
    logger = get_system_logger("enrich")
    logger.info(f"Enrichment started: {article_count} articles to process")


def log_enrichment_progress(processed: int, total: int, article_title: str = None):
    """Log enrichment progress."""
    logger = get_system_logger("enrich")
    if article_title:
        logger.debug(f"Enriched [{processed}/{total}]: {article_title[:50]}...")
    else:
        logger.info(f"Enrichment progress: {processed}/{total}")


def log_enrichment_complete(processed: int, duration_seconds: float):
    """Log enrichment completion."""
    logger = get_system_logger("enrich")
    logger.info(f"Enrichment complete: {processed} articles in {duration_seconds:.1f}s")


def log_api_call(service: str, endpoint: str, status: str, duration_ms: float = None):
    """Log external API calls."""
    logger = get_system_logger("api")
    msg = f"{service} {endpoint}: {status}"
    if duration_ms:
        msg += f" ({duration_ms:.0f}ms)"
    logger.info(msg)


def log_user_action(ip: str, action: str, details: str = ""):
    """
    Log a user action with IP address.

    Args:
        ip: User's IP address
        action: Action type (page_view, scan_start, export, filter, etc.)
        details: Additional details about the action
    """
    usage_log = get_usage_logger()
    usage_log.info(details or action, extra={"ip": ip, "action": action})


# =============================================================================
# IP EXTRACTION HELPERS (for Streamlit)
# =============================================================================

def get_client_ip() -> str:
    """
    Extract client IP from Streamlit context headers.

    Returns the client IP if available, otherwise 'unknown'.
    Works with Streamlit's st.context.headers (1.37+).
    """
    try:
        import streamlit as st

        # Use st.context.headers (Streamlit 1.37+)
        headers = st.context.headers
        if headers:
            # Check for forwarded IP (behind proxy/nginx)
            forwarded = headers.get("X-Forwarded-For", "")
            if forwarded:
                # X-Forwarded-For can contain multiple IPs, take the first
                return forwarded.split(",")[0].strip()

            # Check for real IP header
            real_ip = headers.get("X-Real-IP", "")
            if real_ip:
                return real_ip.strip()

            # Check for host as last resort
            host = headers.get("Host", "")
            if host and ":" in host:
                return host.split(":")[0]

        # Fallback: try to get from session state if stored
        if hasattr(st, "session_state") and "client_ip" in st.session_state:
            return st.session_state.client_ip

    except Exception:
        pass

    return "unknown"


def init_client_ip():
    """
    Initialize and cache the client IP in Streamlit session state.
    Call this at the start of your Streamlit app.
    """
    try:
        import streamlit as st
        if "client_ip" not in st.session_state:
            st.session_state.client_ip = get_client_ip()
    except Exception:
        pass
