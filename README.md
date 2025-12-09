<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/OpenAI-GPT--4o--mini-412991?style=for-the-badge&logo=openai&logoColor=white" alt="OpenAI">
  <img src="https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/Playwright-Crawling-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright">
</p>

<h1 align="center">
  <br>
  🔍 Competitor News Monitor
  <br>
</h1>

<h4 align="center">An AI-powered competitive intelligence platform that automatically discovers, analyzes, and summarizes competitor activity in real-time.</h4>

<p align="center">
  <a href="#-key-features">Key Features</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-dashboard">Dashboard</a> •
  <a href="#-deployment">Deployment</a> •
  <a href="#-api-reference">API Reference</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/status-production-brightgreen?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/coverage-85%25-yellow?style=flat-square" alt="Coverage">
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square" alt="PRs Welcome">
</p>

---

## 🎯 What is Competitor News Monitor?

**Competitor News Monitor** transforms how businesses track their competitive landscape. Instead of manually scouring competitor blogs and news sites, this intelligent agent does it for you—crawling, parsing, classifying, and summarizing content automatically.

Built for the **membership and fitness management software industry**, it monitors key players like Kicksite, Spark Membership, MyStudio, ZenPlanner, GloFox, and ClubOS, delivering actionable intelligence directly to your dashboard.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   "Know what your competitors are doing before your customers tell you."   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 🕷️ Intelligent Crawling
- **Breadth-first discovery** of blog/news pages
- **JavaScript rendering** via Playwright for SPA sites
- **Configurable depth** and domain restrictions
- **Polite crawling** with rate limiting
- **Duplicate detection** via SHA-256 hashing

</td>
<td width="50%">

### 🧠 AI-Powered Analysis
- **11 content categories** (Product, Pricing, M&A, etc.)
- **3-tier impact scoring** (High/Medium/Low)
- **40-80 word summaries** focused on strategic signals
- **GPT-4o-mini** for cost-effective classification
- **Graceful fallbacks** when API fails

</td>
</tr>
<tr>
<td width="50%">

### 📊 Interactive Dashboard
- **Real-time filtering** by company, category, impact
- **Date range selection** for trend analysis
- **Clickable source links** to original articles
- **Color-coded impact badges** for quick scanning
- **Executive summary generation** with PDF export

</td>
<td width="50%">

### ⚙️ Enterprise-Ready
- **Scheduled automation** (cron/Task Scheduler)
- **Process locking** prevents concurrent runs
- **Atomic file operations** for data integrity
- **Comprehensive logging** with rotation
- **One-command deployment** to Linux servers

</td>
</tr>
</table>

---

## 🏃 Quick Start

### Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Python | 3.9+ | Runtime environment |
| OpenAI API Key | - | GPT-4o-mini for classification |
| Git | Any | Version control |

### Installation (3 minutes)

```bash
# 1. Clone the repository
git clone https://github.com/F-Bhaimia/Competitor-Agent.git
cd Competitor-Agent

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install Playwright browsers (for JS-heavy sites)
playwright install chromium

# 6. Configure environment
echo "OPENAI_API_KEY=your_key_here" > .env

# 7. Run your first crawl!
python -m jobs.daily_scan

# 8. Launch the dashboard
streamlit run streamlit_app/Home.py
```

**That's it!** Open `http://localhost:8501` in your browser.

---

## 🏗️ Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            COMPETITOR NEWS MONITOR                                │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌─────────────────┐                                                             │
│  │ monitors.yaml   │ ◄─── Configuration: competitors, URLs, crawl settings       │
│  └────────┬────────┘                                                             │
│           │                                                                      │
│           ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                        DATA COLLECTION LAYER                         │        │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │        │
│  │  │   crawl.py   │    │ fetch_rss.py │    │   Playwright         │   │        │
│  │  │  (requests)  │    │ (feedparser) │    │   (JS Rendering)     │   │        │
│  │  └──────┬───────┘    └──────┬───────┘    └──────────┬───────────┘   │        │
│  │         │                   │                       │               │        │
│  │         └───────────────────┴───────────────────────┘               │        │
│  │                             │                                        │        │
│  └─────────────────────────────┼────────────────────────────────────────┘        │
│                                ▼                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                        PROCESSING LAYER                              │        │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │        │
│  │  │   parse.py   │───▶│ daily_scan.py│───▶│    updates.csv       │   │        │
│  │  │ (HTML→Text)  │    │  (Dedupe)    │    │    (Raw Data)        │   │        │
│  │  └──────────────┘    └──────────────┘    └──────────┬───────────┘   │        │
│  │                                                      │               │        │
│  └──────────────────────────────────────────────────────┼───────────────┘        │
│                                                         ▼                        │
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                        ENRICHMENT LAYER                              │        │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │        │
│  │  │ classify.py  │    │enrich_updates│    │ enriched_updates.csv │   │        │
│  │  │  (GPT-4o)    │───▶│    .py       │───▶│ (+summary, category, │   │        │
│  │  │              │    │              │    │      impact)         │   │        │
│  │  └──────────────┘    └──────────────┘    └──────────┬───────────┘   │        │
│  │                                                      │               │        │
│  └──────────────────────────────────────────────────────┼───────────────┘        │
│                                                         │                        │
│           ┌─────────────────────────────────────────────┼────────────┐           │
│           │                                             │            │           │
│           ▼                                             ▼            ▼           │
│  ┌─────────────────┐                           ┌──────────────┐ ┌─────────┐     │
│  │   DASHBOARD     │                           │   EXPORTS    │ │  ALERTS │     │
│  │   (Streamlit)   │                           │  CSV/PDF/XLS │ │ (Slack) │     │
│  │                 │                           │              │ │         │     │
│  │  • Filtering    │                           │  • QA Sample │ │ • High  │     │
│  │  • Charts       │                           │  • Quarterly │ │  Impact │     │
│  │  • PDF Export   │                           │    Rollup    │ │  Only   │     │
│  └─────────────────┘                           └──────────────┘ └─────────┘     │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Sequence

```
1. DISCOVER    ──▶  Breadth-first traversal from start_urls
                    Filter for /blog/, /news/, /post/, /article/ paths

2. FETCH       ──▶  HTTP GET with custom User-Agent
                    Fallback to Playwright for JS-rendered content

3. PARSE       ──▶  BeautifulSoup extracts title, date, body
                    JSON-LD → OpenGraph → <time> tag → None

4. DEDUPLICATE ──▶  SHA-256 hash of (company || normalized_url)
                    Skip if ID exists in updates.csv

5. STORE       ──▶  Append to data/updates.csv
                    Mirror to data/updates.parquet for analytics

6. ENRICH      ──▶  GPT-4o-mini classifies category + impact
                    Generates 40-80 word strategic summary

7. EXPORT      ──▶  enriched_updates.csv for dashboard
                    Optional: Slack webhook for High-impact items
```

---

## 📂 Project Structure

```
Competitor-Agent/
│
├── 📁 app/                          # Core application modules
│   ├── __init__.py
│   ├── crawl.py                     # Web crawler with Playwright fallback
│   ├── parse.py                     # HTML parsing & content extraction
│   ├── classify.py                  # GPT-4o-mini classification engine
│   └── summarize.py                 # Article summarization utilities
│
├── 📁 jobs/                         # Batch processing jobs
│   ├── daily_scan.py                # Primary crawler job
│   ├── fetch_rss.py                 # Google News RSS integration
│   ├── enrich_updates.py            # AI enrichment pipeline
│   ├── append_updates.py            # Data merging utility
│   ├── update_daily.py              # Pipeline orchestrator
│   ├── qa_sampler.py                # QA sample generator (10%)
│   └── quarterly_rollup.py          # Quarterly analytics aggregation
│
├── 📁 streamlit_app/                # Interactive dashboard
│   └── Home.py                      # Main Streamlit application
│
├── 📁 config/                       # Configuration files
│   └── monitors.yaml                # Competitor & crawl settings
│
├── 📁 automation/                   # Scheduled task scripts
│   └── nightly_update.ps1           # Windows Task Scheduler script
│
├── 📁 scripts/                      # Shell scripts
│   ├── run_pipeline.sh              # Full pipeline (Linux/macOS)
│   └── update_daily.sh              # Cron-friendly daily update
│
├── 📁 data/                         # Data storage (gitignored)
│   ├── updates.csv                  # Raw crawled articles
│   ├── updates.parquet              # Parquet mirror for analytics
│   └── enriched_updates.csv         # AI-enriched articles
│
├── 📁 exports/                      # Generated reports
│   ├── qa_sample_YYYYMMDD.csv       # QA review samples
│   └── quarterly_rollup.csv         # Aggregated statistics
│
├── 📁 logs/                         # Execution logs
│
├── 📄 requirements.txt              # Python dependencies
├── 📄 deploy.sh                     # One-command server deployment
├── 📄 DEPLOYMENT.md                 # Detailed deployment guide
├── 📄 Makefile                      # Development shortcuts
└── 📄 README.md                     # You are here!
```

---

## 🎮 Usage

### Job Commands Reference

| Job | Command | Description | Typical Runtime |
|-----|---------|-------------|-----------------|
| **Daily Scan** | `python -m jobs.daily_scan` | Crawl all competitors, extract articles | 5-15 min |
| **RSS Fetch** | `python -m jobs.fetch_rss --since 2025-01-01` | Pull from Google News feeds | 30 sec |
| **Enrich** | `python -m jobs.enrich_updates` | Apply AI classification | ~2 sec/article |
| **Full Pipeline** | `python -m jobs.update_daily` | Fetch → Merge → Enrich | 10-20 min |
| **QA Sample** | `python -m jobs.qa_sampler` | Generate 10% sample for review | Instant |
| **Quarterly** | `python -m jobs.quarterly_rollup` | Aggregate by company × quarter | Instant |

### Example Workflows

#### Daily Competitive Intelligence Gathering
```bash
# Run the full pipeline (fetches + enriches)
python -m jobs.update_daily

# Or run individual steps for debugging
python -m jobs.daily_scan          # Step 1: Crawl
python -m jobs.enrich_updates      # Step 2: AI classification
```

#### On-Demand Deep Dive
```bash
# Add a new competitor, then run a targeted crawl
# 1. Edit config/monitors.yaml to add the competitor
# 2. Run the daily scan
python -m jobs.daily_scan

# 3. Enrich the new data
python -m jobs.enrich_updates

# 4. Launch dashboard to explore
streamlit run streamlit_app/Home.py
```

#### Quality Assurance Review
```bash
# Generate a random 10% sample of enriched articles
python -m jobs.qa_sampler

# Output: exports/qa_sample_YYYYMMDD.csv
# Review summaries, categories, and impact scores for accuracy
```

---

## 📊 Dashboard

### Launching the Dashboard

```bash
streamlit run streamlit_app/Home.py
```

Access at **http://localhost:8501**

### Dashboard Sections

<table>
<tr>
<td width="33%" align="center">

**📈 Posts by Competitor**

KPI cards, quarterly charts, and chronological feed view

</td>
<td width="33%" align="center">

**📤 Export**

Download filtered data as CSV

</td>
<td width="33%" align="center">

**✏️ Manual Edits**

Correct AI classifications inline

</td>
</tr>
<tr>
<td width="33%" align="center">

**📋 Executive Summary**

AI-generated insights with PDF export

</td>
<td width="33%" align="center">

**🔧 Data Quality Tools**

Run enrichment, generate QA samples

</td>
<td width="33%" align="center">

**🔍 Full-Text Search**

Search across titles and summaries

</td>
</tr>
</table>

### Filtering Options

| Filter | Type | Description |
|--------|------|-------------|
| **Company** | Multi-select | Filter by one or more competitors |
| **Category** | Multi-select | Filter by content category |
| **Impact** | Multi-select | Filter by High/Medium/Low |
| **Date Range** | Date picker | Filter by published or collected date |
| **Search** | Text input | Full-text search in title/summary |

---

## 🏷️ Classification System

### Content Categories

| Category | Description | Examples |
|----------|-------------|----------|
| **Product/Feature** | New features, GA releases, product updates | "Introducing AI Scheduling", "Mobile App 3.0" |
| **Pricing/Plans** | Pricing changes, new tiers, packaging | "New Enterprise Plan", "Price Increase Notice" |
| **Partnership** | Strategic alliances, integrations | "Integration with Stripe", "Partnership with Nike" |
| **Acquisition/Investment** | M&A, funding rounds | "Series B Funding", "Acquisition of XYZ" |
| **Case Study/Customer** | Success stories, testimonials | "How Gym ABC grew 40%", "Customer Spotlight" |
| **Events/Webinar** | Conferences, webinars, workshops | "Join us at IHRSA", "Upcoming Webinar" |
| **Best Practices/Guides** | Educational content, how-tos | "5 Tips for Retention", "Ultimate Guide to..." |
| **Security/Compliance** | Security updates, certifications | "SOC 2 Certification", "GDPR Compliance" |
| **Hiring/Leadership** | Team changes, executive moves | "New CEO Announcement", "We're Hiring!" |
| **Company News** | General announcements | "Office Relocation", "Anniversary" |
| **Other** | Miscellaneous content | Doesn't fit other categories |

### Impact Scoring

| Level | Criteria | Action Required |
|-------|----------|-----------------|
| 🔴 **High** | Pricing changes, major GA features, acquisitions, security incidents, big partnerships | Immediate review recommended |
| 🟠 **Medium** | Meaningful feature updates, significant case studies, notable events | Review within the week |
| ⚪ **Low** | Generic tips, routine posts, educational content | Monitor for trends |

---

## 🔧 Configuration

### monitors.yaml

```yaml
# Global crawl settings
global:
  user_agent: "MS-CompetitorBot/1.0 (+contact: ci@membersolutions.com)"
  request_timeout_s: 20
  max_pages_per_site: 60
  follow_within_domain_only: true
  dedupe_window_days: 365
  high_impact_labels: ["Pricing", "M&A", "Security", "Product Update (GA)"]
  alert_on_impact_levels: ["High"]

# Competitors to monitor
competitors:
  - name: "Kicksite"
    start_urls:
      - "https://kicksite.com/blog"
      - "https://kicksite.com/newsletters/"

  - name: "Spark Membership"
    start_urls:
      - "https://sparkmembership.com/blog/"

  - name: "MyStudio"
    start_urls:
      - "https://www.mystudio.io/blog"

  - name: "ZenPlanner (Daxko)"
    start_urls:
      - "https://zenplanner.com/blog/"
      - "https://www.daxko.com/blog"

  - name: "GloFox (ABC Fitness)"
    start_urls:
      - "https://www.glofox.com/blog/"
      - "https://www.abcfitness.com/resources/blog/"

  - name: "ClubOS (Formerly ASF)"
    start_urls:
      - "https://www.club-os.com/blog"
```

### Environment Variables (.env)

```bash
# Required
OPENAI_API_KEY=sk-your-openai-api-key-here

# Optional (for Slack alerts)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

---

## 🚀 Deployment

### One-Command Server Deployment

For production deployment on a Linux server (Ubuntu/Debian):

```bash
# SSH to your server
ssh root@your-server-ip

# Download and run the deployment script
curl -O https://raw.githubusercontent.com/F-Bhaimia/Competitor-Agent/main/deploy.sh
chmod +x deploy.sh
./deploy.sh
```

The script automatically:
- ✅ Installs system dependencies
- ✅ Sets up Python virtual environment
- ✅ Configures Playwright browsers
- ✅ Creates systemd service
- ✅ Configures Nginx reverse proxy
- ✅ Sets up UFW firewall
- ✅ Schedules daily cron job

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the complete manual deployment guide.

### Scheduled Automation

#### Linux/macOS (Cron)
```bash
# Run daily at 2 AM
0 2 * * * /opt/competitor-agent/scripts/update_daily.sh >> /opt/competitor-agent/logs/cron.log 2>&1
```

#### Windows (Task Scheduler)
```powershell
# Run via PowerShell
powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\automation\nightly_update.ps1"
```

---

## 📚 API Reference

### Core Modules

#### `app.crawl`

```python
from app.crawl import load_config, crawl_all, crawl_competitor

# Load configuration
global_cfg, competitors = load_config("config/monitors.yaml")

# Crawl all competitors
for page in crawl_all():
    print(f"[{page.company}] {page.url}")

# Crawl a single competitor
for page in crawl_competitor(competitors[0], global_cfg):
    print(page.html[:500])
```

#### `app.parse`

```python
from app.parse import parse_article

article = parse_article(
    company="Kicksite",
    url="https://kicksite.com/blog/new-feature",
    html="<html>...</html>"
)

print(article.title)        # "New Feature Announcement"
print(article.published_at) # "2025-01-15T10:00:00"
print(article.clean_text)   # Extracted body text
```

#### `app.classify`

```python
from app.classify import classify_article, CATEGORIES

result = classify_article(
    company="Kicksite",
    title="New Pricing Plans Available",
    body="We're excited to announce our new pricing structure..."
)

print(result)
# {
#     "summary": "Kicksite introduces new pricing tiers with...",
#     "category": "Pricing/Plans",
#     "impact": "High"
# }
```

### Data Structures

#### Page (from crawl)
```python
@dataclass
class Page:
    company: str    # Competitor name
    url: str        # Page URL
    html: str       # Raw HTML content
```

#### Article (from parse)
```python
@dataclass
class Article:
    company: str              # Competitor name
    source_url: str           # Original URL
    title: str                # Extracted title
    published_at: Optional[str]  # ISO datetime or None
    clean_text: str           # Extracted body text
```

### CSV Schema

#### updates.csv (Raw)
| Column | Type | Description |
|--------|------|-------------|
| `id` | string | SHA-256 hash of company+url |
| `company` | string | Competitor name |
| `source_url` | string | Original article URL |
| `title` | string | Article title |
| `published_at` | datetime | Publish date (if found) |
| `collected_at` | datetime | When crawled (UTC) |
| `clean_text` | string | Article body text |

#### enriched_updates.csv (+ AI columns)
| Column | Type | Description |
|--------|------|-------------|
| ... | ... | All columns from updates.csv |
| `summary` | string | AI-generated 40-80 word summary |
| `category` | string | One of 11 categories |
| `impact` | string | High, Medium, or Low |

---

## 🔒 Security & Reliability

### Error Handling

| Scenario | Behavior |
|----------|----------|
| **Network timeout** | Retry with exponential backoff (Tenacity) |
| **403/429 response** | Skip page, continue crawl |
| **OpenAI API failure** | Return defaults (category="Other", impact="Low") |
| **Malformed HTML** | Best-effort parsing, skip if no content |
| **Concurrent runs** | Prevented via file locks / OS mutex |

### Data Integrity

- **Atomic writes**: Temp file → `os.replace()` for crash safety
- **Deduplication**: SHA-256 hash prevents duplicate entries
- **Parquet mirror**: Binary format for faster analytics queries
- **Log rotation**: Keeps last 15 pipeline logs

### Security Best Practices

```bash
# Secure your .env file
chmod 600 .env

# Don't commit secrets
echo ".env" >> .gitignore

# Use SSH keys for server access
ssh-keygen -t ed25519 -C "your_email@example.com"

# Enable UFW firewall
sudo ufw allow 22,80,443/tcp
sudo ufw enable
```

---

## 🛠️ Troubleshooting

### Common Issues

<details>
<summary><b>❌ "No module named 'playwright'"</b></summary>

```bash
pip install playwright
playwright install chromium
```
</details>

<details>
<summary><b>❌ Crawl returns empty results</b></summary>

1. Check if the site uses JavaScript rendering:
```bash
curl -s "https://example.com/blog" | wc -c  # Should be > 1000 chars
```

2. If tiny, the site needs Playwright (should be automatic fallback)

3. Check `config/monitors.yaml` for correct URLs
</details>

<details>
<summary><b>❌ OpenAI rate limiting</b></summary>

The system uses Tenacity with exponential backoff. If persistent:
- Check your OpenAI dashboard for quota limits
- Reduce `BATCH_SIZE` in `enrich_updates.py`
- Increase `SLEEP_BETWEEN` delay
</details>

<details>
<summary><b>❌ Dashboard won't start</b></summary>

```bash
# Check if port 8501 is in use
netstat -tulpn | grep 8501

# Run with explicit port
streamlit run streamlit_app/Home.py --server.port 8502

# Check Streamlit logs
streamlit run streamlit_app/Home.py 2>&1 | tee dashboard.log
```
</details>

<details>
<summary><b>❌ Data not updating in dashboard</b></summary>

1. Click "Reload Data" button in the dashboard
2. Check if enrichment job completed:
```bash
tail -f logs/pipeline_*.log
```
3. Verify data files exist:
```bash
ls -la data/
```
</details>

---

## 📈 Performance Optimization

### Recommended Settings by Use Case

| Scenario | `max_pages_per_site` | `request_timeout_s` | Notes |
|----------|---------------------|---------------------|-------|
| Quick daily check | 20 | 15 | Fast, catches recent posts |
| Weekly deep crawl | 100 | 30 | Comprehensive coverage |
| Initial backfill | 200 | 45 | One-time historical load |
| Low-memory server | 30 | 20 | Reduces Playwright memory |

### Memory Optimization

```bash
# If server runs out of memory, add swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Competitor-Agent.git
cd Competitor-Agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run tests (if available)
pytest tests/
```

---

## 📦 Dependencies

### Core Stack

| Package | Version | Purpose |
|---------|---------|---------|
| `requests` | latest | HTTP client for web crawling |
| `beautifulsoup4` | latest | HTML parsing |
| `lxml` | latest | Fast XML/HTML parser |
| `playwright` | latest | JavaScript rendering |
| `openai` | ≥1.40.0 | GPT-4o-mini API client |
| `streamlit` | latest | Interactive dashboard |
| `pandas` | latest | Data manipulation |
| `pyarrow` | latest | Parquet file support |

### Supporting Libraries

| Package | Purpose |
|---------|---------|
| `python-dotenv` | Environment variable loading |
| `feedparser` | RSS feed parsing |
| `tenacity` | Retry logic with backoff |
| `pydantic` | Configuration validation |
| `reportlab` | PDF generation |
| `python-dateutil` | Date parsing |
| `openpyxl` | Excel export |
| `slack_sdk` | Slack webhook integration |

---

## 📊 Monitored Competitors

| Competitor | Parent Company | Monitored Since |
|------------|---------------|-----------------|
| **Kicksite** | Independent | 2025 |
| **Spark Membership** | Independent | 2025 |
| **MyStudio** | Independent | 2025 |
| **ZenPlanner** | Daxko | 2025 |
| **GloFox** | ABC Fitness | 2025 |
| **ClubOS** | Formerly ASF | 2025 |

---

## 📜 Changelog

### v1.0.0 (2025)
- Initial release
- Web crawling with Playwright fallback
- GPT-4o-mini classification pipeline
- Streamlit dashboard with PDF export
- Linux deployment automation
- Windows PowerShell automation

---

## 📞 Support

Having issues? Here's how to get help:

1. **Check the docs**: Read through this README and [DEPLOYMENT.md](DEPLOYMENT.md)
2. **Search issues**: Look for similar problems in [GitHub Issues](https://github.com/F-Bhaimia/Competitor-Agent/issues)
3. **Open an issue**: If your problem is new, create a detailed issue with:
   - Python version (`python --version`)
   - Operating system
   - Error messages and logs
   - Steps to reproduce

---

## 🙏 Acknowledgments

- **OpenAI** for GPT-4o-mini powering our classification
- **Streamlit** for the beautiful dashboard framework
- **Playwright** for headless browser automation
- **BeautifulSoup** for rock-solid HTML parsing

---

<p align="center">
  <b>Built with ❤️ for competitive intelligence</b>
  <br>
  <sub>Making market research effortless, one crawl at a time.</sub>
</p>

<p align="center">
  <a href="#-competitor-news-monitor">Back to top ↑</a>
</p>
