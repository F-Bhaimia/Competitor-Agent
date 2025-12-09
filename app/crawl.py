# app/crawl.py
from __future__ import annotations
import os
import time
import urllib.parse as urlparse
from dataclasses import dataclass
from typing import Iterable, List, Set, Tuple
import requests
from bs4 import BeautifulSoup
import yaml

from app.logger import get_system_logger, log_scan_error

logger = get_system_logger(__name__)

@dataclass
class GlobalConfig:
    user_agent: str
    request_timeout_s: int
    max_pages_per_site: int
    follow_within_domain_only: bool

@dataclass
class Competitor:
    name: str
    start_urls: List[str]

@dataclass
class Page:
    company: str
    url: str
    html: str

def load_config(path: str = "config/monitors.yaml") -> Tuple[GlobalConfig, List[Competitor]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found at {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError(f"Config at {path} is empty or invalid YAML")

    if "global" not in cfg or "competitors" not in cfg:
        raise KeyError("Config must contain 'global' and 'competitors' keys")

    g = cfg["global"]
    global_cfg = GlobalConfig(
        user_agent=g.get("user_agent", "MS-CompetitorBot/1.0"),
        request_timeout_s=int(g.get("request_timeout_s", 20)),
        max_pages_per_site=int(g.get("max_pages_per_site", 50)),
        follow_within_domain_only=bool(g.get("follow_within_domain_only", True)),
    )

    comps_raw = cfg.get("competitors") or []
    if not isinstance(comps_raw, list) or not comps_raw:
        raise ValueError("Config 'competitors' must be a non-empty list")

    comps = []
    for c in comps_raw:
        name = c.get("name")
        urls = c.get("start_urls") or []
        if not name or not urls:
            # skip invalid competitor blocks but keep going
            continue
        comps.append(Competitor(name=name, start_urls=urls))

    if not comps:
        raise ValueError("No valid competitors found in config")

    return global_cfg, comps

def _session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s

def _is_same_domain(seed: str, candidate: str) -> bool:
    a = urlparse.urlparse(seed)
    b = urlparse.urlparse(candidate)
    return a.netloc == b.netloc

def _normalize_url(base: str, link: str) -> str:
    return urlparse.urljoin(base, link.split("#")[0])

def discover_article_links(html: str, base_url: str) -> Set[str]:
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.find_all("a", href=True):
        href = _normalize_url(base_url, a["href"])
        if any(x in href.lower() for x in ["/blog/", "/news", "/post", "/article", "/resources", "/insights"]):
            links.add(href)
    return links

def fetch_html(session: requests.Session, url: str, timeout: int) -> str | None:
    """
    Try fetching HTML normally (fast path), then fallback to Playwright (slow but JS-aware).
    """
    try:
        r = session.get(url, timeout=timeout)
        if r.status_code == 200 and "text/html" in (r.headers.get("Content-Type") or ""):
            text = r.text.strip()
            if len(text) > 500:
                logger.debug(f"Fetched {url} ({len(text)} bytes)")
                return text
        else:
            logger.debug(f"HTTP {r.status_code} for {url}")
    except requests.RequestException as e:
        logger.debug(f"Request failed for {url}: {e}")

    # If the normal request fails or returns too little content, try Playwright
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)
            page.goto(url, wait_until="load")
            # wait a bit for JS-heavy sites
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            if html and len(html.strip()) > 500:
                logger.info(f"[Playwright] Rendered {url}")
                return html
    except Exception as e:
        logger.warning(f"Playwright failed for {url}: {e}")

    return None



def crawl_competitor(comp: Competitor, cfg: GlobalConfig) -> Iterable[Page]:
    logger.info(f"Starting crawl for {comp.name} ({len(comp.start_urls)} start URLs)")
    logger.debug(f"[{comp.name}] Start URLs: {comp.start_urls}")
    logger.debug(f"[{comp.name}] Max pages: {cfg.max_pages_per_site}, Timeout: {cfg.request_timeout_s}s")

    session = _session(cfg.user_agent)
    visited: Set[str] = set()
    queue: List[str] = list(comp.start_urls)
    pages_yielded = 0
    fetch_errors = 0

    while queue and len(visited) < cfg.max_pages_per_site:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        logger.debug(f"[{comp.name}] Fetching ({len(visited)}/{cfg.max_pages_per_site}): {url}")

        html = fetch_html(session, url, cfg.request_timeout_s)
        if not html:
            fetch_errors += 1
            logger.debug(f"[{comp.name}] Failed to fetch: {url}")
            continue

        # current page might itself be an article
        if any(x in url.lower() for x in ["/blog/", "/news", "/post", "/article", "/resources", "/insights"]):
            pages_yielded += 1
            logger.debug(f"[{comp.name}] Article found: {url}")
            yield Page(company=comp.name, url=url, html=html)

        # discover more links on the page
        new_links = 0
        for link in discover_article_links(html, url):
            if cfg.follow_within_domain_only:
                if any(_is_same_domain(seed, link) for seed in comp.start_urls):
                    if link not in visited and link not in queue:
                        queue.append(link)
                        new_links += 1
            else:
                if link not in visited and link not in queue:
                    queue.append(link)
                    new_links += 1

        if new_links > 0:
            logger.debug(f"[{comp.name}] Discovered {new_links} new links, queue size: {len(queue)}")

        time.sleep(0.5)

    logger.info(f"Finished {comp.name}: visited {len(visited)} pages, yielded {pages_yielded} articles, {fetch_errors} errors")

def crawl_all() -> Iterable[Page]:
    cfg, comps = load_config()
    logger.info(f"Crawl started: {len(comps)} competitors, max {cfg.max_pages_per_site} pages/site")
    for comp in comps:
        yield from crawl_competitor(comp, cfg)
    logger.info("Crawl iteration complete")
