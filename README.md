# Competitor News Monitor

**AI-powered competitive intelligence that runs on autopilot.**

Crawls competitor blogs, ingests newsletters via email, classifies content with GPT-4o-mini, and surfaces actionable insights to your dashboard.

```
Blogs + Newsletters  →  AI Classification  →  Dashboard + Alerts
```

## Quick Start

```bash
git clone https://github.com/F-Bhaimia/Competitor-Agent.git && cd Competitor-Agent
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
echo "OPENAI_API_KEY=sk-xxx" > .env

# Launch everything
start_dashboard.bat
```

Open **http://localhost:8501**

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│  Competitor     │     │  CloudMailin    │
│  Blogs          │     │  (newsletters)  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  daily_scan.py  │     │ webhook_server  │
│  (Playwright)   │     │  (FastAPI)      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │              ┌────────▼────────┐
         │              │ email_matcher   │
         │              │ (AI matching)   │
         │              └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────┐
│            updates.csv                  │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│         enrich_updates.py               │
│   (GPT-4o-mini classification)          │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│         Streamlit Dashboard             │
│   Filters • Charts • PDF Export         │
└─────────────────────────────────────────┘
```

---

## How It Works

| Step | What Happens |
|------|--------------|
| **Crawl** | Breadth-first discovery of blog posts. Playwright handles JS-rendered sites. |
| **Ingest** | Webhook receives newsletters, AI matches sender to competitor, immediately adds to pipeline. |
| **Dedupe** | SHA-256 hash of `company + URL/message-id` prevents duplicates. |
| **Classify** | GPT-4o-mini assigns category, impact level, and 40-80 word strategic summary. |
| **Display** | Dashboard with filters, quarterly trends, and one-click export. |

---

## Services

| Service | Command | Port | Purpose |
|---------|---------|------|---------|
| **Dashboard** | `streamlit run streamlit_app/Home.py` | 8501 | Web UI |
| **Webhook** | `python -m app.webhook_server` | 8001 | Newsletter ingestion |

**Startup script:** `start_dashboard.bat` launches both.

---

## Newsletter Ingestion

Emails flow through a 3-stage pipeline with full tracking:

```
Newsletter arrives
       │
       ▼
POST /email (port 8001)
       │
       ▼
┌──────────────────────────────────────────────────┐
│ STAGE 1: RECEIVED                                │
│ • Saved to data/emails/ as JSON                  │
│ • Logged to emails.csv                           │
│ • Sender "received" count incremented            │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│ STAGE 2: PROCESSED                               │
│ • AI matches sender to competitor                │
│ • (or uses manual assignment if set)             │
│ • Sender "processed" count incremented           │
└──────────────────────────────────────────────────┘
       │
       ├─── No match → stops here (logged only)
       │
       ▼
┌──────────────────────────────────────────────────┐
│ STAGE 3: INJECTED                                │
│ • Added to updates.csv                           │
│ • Sender "injected" count incremented            │
│ • JSON moved to emails/processed/                │
│ • Background enrichment triggered                │
└──────────────────────────────────────────────────┘
```

**Setup:**
1. Create a [CloudMailin](https://cloudmailin.com) address
2. Point webhook to `https://your-domain/email`
3. Subscribe to competitor newsletters

**Tracking files:**
- `emails.csv` — One row per email (unique by filename)
- `email_senders.csv` — Aggregated stats per sender address

Unmatched senders can be manually assigned in the dashboard (Settings → Emails tab). Future emails from assigned senders skip AI matching.

---

## Dashboard Features

**Main View**
- Filter by company, category, impact, date range
- Quarterly trend charts
- Inline editing of enriched data
- CSV and PDF export

**Settings (⚙️)**

| Tab | Function |
|-----|----------|
| **Configuration** | Add/remove competitors, edit URLs, global settings |
| **Categories** | Define AI classification categories and impact rules |
| **Emails** | View newsletter senders, reassign matches |
| **Data Quality** | Run enrichment, QA sampling tools |

---

## Project Structure

```
app/
  ├── crawl.py           # Web crawler with Playwright fallback
  ├── parse.py           # HTML content extraction
  ├── classify.py        # GPT-4o-mini classification
  ├── webhook_server.py  # FastAPI email endpoint
  ├── email_matcher.py   # AI sender-to-competitor matching
  └── logger.py          # Centralized logging

jobs/
  ├── daily_scan.py      # Crawl all competitors
  ├── enrich_updates.py  # AI classification batch job
  └── process_emails.py  # Batch newsletter processing

streamlit_app/
  └── Home.py            # Dashboard application

config/
  └── monitors.yaml      # Competitors, categories, rules

data/                    # CSV + Parquet storage (gitignored)
  ├── updates.csv        # All competitor content
  ├── enriched_updates.csv
  ├── emails.csv         # Email log (one row per email)
  ├── email_senders.csv  # Sender stats (received/processed/injected counts)
  └── emails/            # Raw email JSON files
      └── processed/     # Emails injected into pipeline
```

---

## Commands

| Command | Description |
|---------|-------------|
| `start_dashboard.bat` | Launch dashboard + webhook |
| `python -m jobs.daily_scan` | Crawl all competitors |
| `python -m jobs.enrich_updates` | Run AI classification |
| `python -m jobs.process_emails` | Reprocess emails in `data/emails/` through full pipeline |
| `python -m app.webhook_server` | Webhook server only |

---

## Configuration

**config/monitors.yaml**
```yaml
global:
  max_pages_per_site: 60
  request_timeout_s: 20
  webhook_port: 8001

classification:
  categories:
    - Product/Feature
    - Pricing/Plans
    - Partnership
    - Acquisition/Investment
    # ... 11 total
  impact_rules:
    high:
      - pricing change
      - major feature GA
      - acquisitions

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

## Classification

| Category | High Impact Triggers |
|----------|---------------------|
| Product/Feature | GA releases, major updates |
| Pricing/Plans | Any pricing change |
| Acquisition/Investment | Always high |
| Security/Compliance | Incidents, certifications |
| Partnership | Strategic alliances |
| Case Study/Customer | Large customer wins |
| Events/Webinar | Industry conferences |
| Hiring/Leadership | Executive changes |
| Best Practices/Guides | — |
| Company News | — |
| Other | — |

---

## Tech Stack

| Layer | Tech |
|-------|------|
| Crawling | requests, Playwright, BeautifulSoup |
| AI | OpenAI GPT-4o-mini |
| Webhook | FastAPI, uvicorn |
| Dashboard | Streamlit |
| Data | pandas, Parquet |

---

## Troubleshooting

<details>
<summary><b>Port already in use</b></summary>

```bash
# Windows
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
<summary><b>Email not matching competitor</b></summary>

Check the Emails tab in Settings. You can manually assign senders to competitors. Future emails from that sender will auto-match.
</details>

---

## License

Internal use only.

---

<p align="center"><i>Know what your competitors are doing before your customers tell you.</i></p>
