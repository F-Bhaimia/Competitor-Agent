# Competitor News Monitor

> **Know what your competitors are doing before your customers tell you.**

Most competitive intelligence is reactive. You find out about a competitor's new feature when a prospect mentions it on a sales call. You discover their pricing change when you lose a deal. You learn about their acquisition from LinkedIn.

This tool makes competitive intelligence proactive. It crawls competitor blogs, ingests their newsletters, classifies everything with AI, and surfaces what matters to a dashboard you'll actually use.

## The Problem This Solves

Staying informed about competitors is tedious:

1. **Blogs are scattered.** Each competitor has different URLs, different structures, different publishing cadences.
2. **Newsletters pile up.** They sit unread in a folder, or worse, in someone's personal inbox.
3. **Classification is inconsistent.** What one person calls "high impact" another ignores.
4. **Knowledge is siloed.** The person who reads the newsletter isn't always the person who needs the insight.

This tool solves these problems by automating collection and standardizing classification.

## Quick Start

```bash
git clone https://github.com/F-Bhaimia/Competitor-Agent.git
cd Competitor-Agent

# Set up environment
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -r requirements.txt
playwright install chromium

# Configure
echo "OPENAI_API_KEY=sk-your-key" > .env
# Edit config/monitors.yaml with your competitors

# Run
start_dashboard.bat   # Windows
# or: ./start_dashboard.sh  # Unix
```

Open **http://localhost:8501**. That's it.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                              │
├────────────────────────┬────────────────────────────────────────┤
│   Competitor Blogs     │        Email Newsletters               │
│   (Playwright crawl)   │        (CloudMailin webhook)           │
└───────────┬────────────┴───────────────┬────────────────────────┘
            │                            │
            ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PROCESSING                                  │
│  • Deduplicate (SHA-256 hash of company + URL)                  │
│  • AI classification (GPT-4o-mini)                              │
│  • Impact scoring (High / Medium / Low)                         │
│  • 40-80 word strategic summary                                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       OUTPUT                                     │
│  • Streamlit dashboard with filters and charts                  │
│  • CSV/PDF export                                               │
│  • Executive summary generation                                 │
└─────────────────────────────────────────────────────────────────┘
```

The system has two input channels:

**Blog Crawling** runs daily. Playwright handles JavaScript-rendered sites. The crawler does breadth-first discovery, follows internal links, and extracts article content with BeautifulSoup.

**Newsletter Ingestion** is instant. Point CloudMailin at your webhook, subscribe to competitor newsletters with that address, and emails appear in the dashboard within seconds.

## Configuration

Everything lives in `config/monitors.yaml`:

```yaml
global:
  max_pages_per_site: 60    # Crawl depth limit
  request_timeout_s: 20     # Per-request timeout
  webhook_port: 8001        # Newsletter webhook

competitors:
  - name: "Acme Corp"
    start_urls:
      - "https://acme.com/blog"
      - "https://acme.com/news"

  - name: "Beta Inc"
    start_urls:
      - "https://beta.io/blog/"

classification:
  categories:
    - Product/Feature
    - Pricing/Plans
    - Partnership
    - Acquisition/Investment
    - Security/Compliance
    - Case Study/Customer
    - Events/Webinar
    - Hiring/Leadership
    - Best Practices/Guides
    - Company News
    - Other

  impact_rules:
    high:
      - pricing change
      - major feature launch
      - acquisition
      - security incident
```

Add a competitor by adding to the `competitors` list. Remove one by deleting it. The next scan picks up the changes automatically.

## Newsletter Setup

Newsletters require a webhook to receive forwarded emails:

1. **Get a CloudMailin address** (or use Gmail forwarding to your existing CloudMailin)
2. **Point it at your webhook:** `https://your-domain.com/email`
3. **Subscribe to competitor newsletters** using that email

When an email arrives:

```
RECEIVED  →  MATCHED  →  INJECTED
   │            │           │
   │            │           └─ Added to dashboard, AI enriched
   │            └─ AI identifies which competitor (or manual assignment)
   └─ Saved to disk, logged to CSV
```

Unmatched emails aren't lost—they sit in `data/emails/` waiting for you to manually assign the sender in Settings → Emails.

## The Dashboard

Four tabs:

| Tab | What It Does |
|-----|--------------|
| **Dashboard** | KPIs, quarterly trend chart, filterable feed |
| **Export** | Download current filtered view as CSV |
| **Manual Edits** | Fix AI mistakes inline |
| **Executive Summary** | Generate PDF briefing with AI highlights |

Plus a Settings gear (⚙️) with:

- **Configuration** — Edit competitors, URLs, global settings
- **Categories** — Customize classification taxonomy
- **Emails** — Manage sender assignments, view/delete emails
- **Data Quality** — Run enrichment, rebuild stats, QA tools

## Classification Logic

The AI classifies every article into a category and impact level:

| Impact | Triggers |
|--------|----------|
| **High** | Pricing changes, GA releases, acquisitions, security incidents, executive changes |
| **Medium** | Beta features, partnerships, large customer wins |
| **Low** | Blog posts, webinars, thought leadership |

You can tune this in `config/monitors.yaml` under `impact_rules`.

## Project Layout

```
app/
  crawl.py           # Playwright crawler
  parse.py           # Content extraction
  classify.py        # GPT-4o-mini classification
  webhook_server.py  # FastAPI email endpoint
  email_matcher.py   # Sender-to-competitor matching
  logger.py          # Centralized logging

jobs/
  daily_scan.py      # Crawl orchestrator
  enrich_updates.py  # Batch AI classification
  process_emails.py  # Reprocess email backlog

streamlit_app/
  Home.py            # The dashboard

config/
  monitors.yaml      # All configuration

data/                # Gitignored
  updates.csv        # Raw collected content
  enriched_updates.csv
  emails/            # Email JSON files
    processed/       # Injected to pipeline
    deleted/         # Soft-deleted

logs/                # Gitignored, timestamped per session
  system_*.log
  webhook_*.log
  usage_*.log
```

## Running in Production

For scheduled crawling, add a cron job (or Windows Task Scheduler):

```bash
# Daily at 6am
0 6 * * * cd /path/to/Competitor-Agent && python -m jobs.daily_scan

# Enrichment every 4 hours
0 */4 * * * cd /path/to/Competitor-Agent && python -m jobs.enrich_updates
```

For the webhook, run it as a systemd service or use a process manager like PM2.

## Design Decisions

A few choices worth explaining:

**CSV over database.** For a system with thousands of rows, not millions, CSV is good enough. It's portable, debuggable with Excel, and eliminates a dependency. Parquet is used for dashbaord performance.

**GPT-4o-mini over larger models.** Classification and summarization don't need GPT-4. Mini is 10x cheaper and fast enough for batch processing.

**Soft delete over hard delete.** Deleted emails move to `deleted/` folder rather than being destroyed. Storage is cheap; regret is expensive.

**Session-timestamped logs.** Each service start creates new log files (`system_20251211_140000.log`). Makes debugging specific runs easier than one giant file.

## Troubleshooting

**Port 8501 already in use**
```bash
# Windows
netstat -ano | findstr :8501
taskkill /F /PID <pid>
```

**Playwright fails to launch**
```bash
playwright install chromium
playwright install-deps  # Linux only
```

**Emails not matching competitors**

Go to Settings → Emails. Find the sender and manually assign them to a competitor. All future emails from that sender will auto-match.

**Classification seems wrong**

Use the Manual Edits tab to fix individual rows. Consider adjusting the prompts in `config/monitors.yaml` under `prompts.classify`.

## Contributing

This is an internal tool, but the patterns are reusable:

- The crawler handles JavaScript-heavy sites gracefully
- The webhook pattern works for any email-to-pipeline use case
- The classification prompts can be adapted for other domains

## License

Internal use only.

---

<p align="center">
<i>Competitive intelligence shouldn't require a full-time analyst.<br/>
It should be a dashboard you check with your morning coffee.</i>
</p>
