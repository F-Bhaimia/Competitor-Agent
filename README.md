# Competitor News Monitor

**AI-powered competitive intelligence that runs on autopilot.**

Crawls competitor blogs, ingests newsletters, classifies content with GPT-4o-mini, and delivers actionable insights to your dashboard.

```
Blogs + Newsletters  →  AI Classification  →  Dashboard + Alerts
```

## Quick Start

```bash
git clone https://github.com/F-Bhaimia/Competitor-Agent.git && cd Competitor-Agent
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -r requirements.txt
playwright install chromium
echo "OPENAI_API_KEY=sk-xxx" > .env

# Run it
python -m jobs.daily_scan      # Crawl competitors
python -m jobs.enrich_updates  # AI classification
start_dashboard.bat            # Launch dashboard + webhook
```

Open **http://localhost:8501**

---

## How It Works

| Step | What Happens |
|------|--------------|
| **Crawl** | Breadth-first discovery of blog posts with Playwright fallback for JS sites |
| **Ingest** | Webhook receives newsletters via CloudMailin (or any email-to-webhook service) |
| **Dedupe** | SHA-256 hash of `company + URL` prevents duplicates |
| **Classify** | GPT-4o-mini assigns category, impact level, and 40-80 word summary |
| **Display** | Streamlit dashboard with filters, charts, and PDF export |

---

## Features

**Data Collection**
- Web crawling with JS rendering (Playwright)
- Newsletter ingestion via webhook
- RSS feed support
- Configurable per-competitor URLs

**AI Analysis**
- 11 content categories (Product, Pricing, M&A, Security, etc.)
- 3-tier impact scoring (High/Medium/Low)
- Strategic summaries focused on competitive signals

**Dashboard**
- Filter by company, category, impact, date
- Quarterly trend charts
- One-click CSV/PDF export
- Settings page for config management

---

## Project Structure

```
app/                    # Core modules
  ├── crawl.py          # Web crawler
  ├── parse.py          # HTML extraction
  ├── classify.py       # GPT-4o-mini classification
  ├── webhook_server.py # Email ingestion endpoint
  └── logger.py         # Centralized logging

jobs/                   # Batch jobs
  ├── daily_scan.py     # Main crawler
  ├── enrich_updates.py # AI enrichment
  └── process_emails.py # Newsletter processing

streamlit_app/Home.py   # Dashboard
config/monitors.yaml    # Competitor configuration
data/                   # CSV + Parquet storage (gitignored)
```

---

## Commands

| Command | Description |
|---------|-------------|
| `python -m jobs.daily_scan` | Crawl all competitors |
| `python -m jobs.enrich_updates` | Run AI classification |
| `python -m jobs.process_emails` | Process received newsletters |
| `python -m jobs.update_daily` | Full pipeline (crawl + enrich) |
| `start_dashboard.bat` | Launch dashboard + webhook server |
| `start_webhook.bat` | Webhook server only |

---

## Configuration

**config/monitors.yaml**
```yaml
global:
  max_pages_per_site: 60
  request_timeout_s: 20
  webhook_port: 8001

competitors:
  - name: "Kicksite"
    start_urls:
      - "https://kicksite.com/blog"
  - name: "ZenPlanner (Daxko)"
    start_urls:
      - "https://zenplanner.com/blog/"
      - "https://www.daxko.com/blog"
```

**.env**
```
OPENAI_API_KEY=sk-your-key
SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # optional
```

---

## Newsletter Ingestion

Receive competitor newsletters via email:

1. Sign up for [CloudMailin](https://cloudmailin.com) (or similar)
2. Point webhook to `https://your-domain/email/`
3. Subscribe to competitor newsletters with your CloudMailin address
4. Emails auto-save to `data/emails/` and process into the pipeline

```
Newsletter → CloudMailin → Webhook (port 8001) → data/emails/ → process_emails → updates.csv
```

---

## Deployment

**One-liner for Ubuntu:**
```bash
curl -O https://raw.githubusercontent.com/F-Bhaimia/Competitor-Agent/main/deploy.sh && chmod +x deploy.sh && ./deploy.sh
```

Sets up: Python venv, Playwright, systemd services, nginx proxy, UFW firewall, daily cron.

See [DEPLOYMENT.md](DEPLOYMENT.md) for manual setup.

---

## Classification Categories

| Category | Triggers High Impact |
|----------|---------------------|
| Product/Feature | GA releases, major updates |
| Pricing/Plans | Any pricing change |
| Acquisition/M&A | Always |
| Security/Compliance | Incidents, certifications |
| Partnership | Strategic alliances |
| Case Study | Large customer wins |
| Events/Webinar | Industry conferences |
| Hiring/Leadership | Executive changes |
| Best Practices | — |
| Company News | — |
| Other | — |

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Crawling | requests, Playwright, BeautifulSoup |
| AI | OpenAI GPT-4o-mini |
| Webhook | FastAPI + uvicorn |
| Dashboard | Streamlit |
| Data | pandas, Parquet |
| Scheduling | cron (Linux), Task Scheduler (Windows) |

---

## Troubleshooting

<details>
<summary><b>Port already in use</b></summary>

```bash
# Windows - find and kill process on port
netstat -ano | findstr :8501
taskkill /F /PID <pid>
```
</details>

<details>
<summary><b>Playwright not working</b></summary>

```bash
playwright install chromium
playwright install-deps  # Linux only
```
</details>

<details>
<summary><b>OpenAI rate limits</b></summary>

Reduce `BATCH_SIZE` in `jobs/enrich_updates.py` or increase `SLEEP_BETWEEN`.
</details>

---

## License

Internal use only.

---

<p align="center">
<i>Know what your competitors are doing before your customers tell you.</i>
</p>
