# Competitor News Monitor

An AI-powered competitive intelligence system that automatically crawls, analyzes, and summarizes competitor blog posts and news articles from the membership and fitness management software industry.

## Overview

This tool monitors competitor websites, extracts relevant content, and uses OpenAI's GPT models to classify and summarize articles by impact level and category. It provides a Streamlit dashboard for reviewing intelligence data.

## Features

- **Automated Web Crawling**: Discovers and crawls competitor blog posts and news articles
- **Smart Content Extraction**: Parses article text from HTML with JavaScript-rendered page support (Playwright)
- **AI Classification**: Categorizes articles (Product/Feature, Pricing, M&A, Security, etc.)
- **Impact Assessment**: Automatically rates articles as High, Medium, or Low impact
- **AI Summarization**: Generates concise 40-80 word summaries of competitor updates
- **Visual Dashboard**: Streamlit-based interface for exploring insights with filtering and PDF export
- **RSS Feed Integration**: Alternative data source via Google News RSS feeds
- **Scheduled Automation**: PowerShell (Windows) and Bash (Linux/macOS) scripts for nightly updates
- **Data Export**: CSV, Excel, JSON formats with quarterly rollups and QA sampling

## Monitored Competitors

| Competitor | Parent Company |
|------------|---------------|
| Kicksite | - |
| Spark Membership | - |
| MyStudio | - |
| ZenPlanner | Daxko |
| GloFox | ABC Fitness |
| ClubOS | Formerly ASF |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ monitors.yaml│────▶│   crawl.py   │────▶│     parse.py         │    │
│  │  (Config)    │     │ (Discovery)  │     │ (Content Extraction) │    │
│  └──────────────┘     └──────────────┘     └──────────┬───────────┘    │
│                                                        │                │
│                       ┌────────────────────────────────┘                │
│                       ▼                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐    │
│  │ fetch_rss.py │────▶│ updates.csv  │────▶│  enrich_updates.py   │    │
│  │ (RSS Feeds)  │     │  (Raw Data)  │     │  (AI Classification) │    │
│  └──────────────┘     └──────────────┘     └──────────┬───────────┘    │
│                                                        │                │
│                       ┌────────────────────────────────┘                │
│                       ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    enriched_updates.csv                           │  │
│  │            (Articles with Summary, Category, Impact)              │  │
│  └───────────────────────────────┬──────────────────────────────────┘  │
│                                  │                                      │
│            ┌─────────────────────┴─────────────────────┐               │
│            ▼                                           ▼               │
│  ┌──────────────┐                           ┌──────────────────────┐   │
│  │  Dashboard   │                           │    Export/Reports    │   │
│  │  (Streamlit) │                           │  (CSV, PDF, XLSX)    │   │
│  └──────────────┘                           └──────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.9+
- OpenAI API key

### Setup

1. Clone the repository:
```bash
git clone https://github.com/F-Bhaimia/Competitor-Agent.git
cd Competitor-Agent
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers (for JavaScript-heavy sites):
```bash
playwright install chromium
```

5. Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

## Configuration

Edit `config/monitors.yaml` to customize:

- **Competitors**: Add or remove competitors and their start URLs
- **Crawl Settings**: Adjust crawl depth, timeout, and domain restrictions
- **Impact Levels**: Define which categories trigger alerts

Example configuration:
```yaml
global:
  user_agent: "MS-CompetitorBot/1.0 (+contact: ci@membersolutions.com)"
  request_timeout_s: 20
  max_pages_per_site: 60
  follow_within_domain_only: true
  high_impact_labels: ["Pricing", "M&A", "Security", "Product Update (GA)"]

competitors:
  - name: "Kicksite"
    start_urls:
      - "https://kicksite.com/blog"
```

## Usage

### Run the Full Pipeline

The pipeline crawls, parses, classifies, and saves results to `data/`:

```bash
# Full daily update (fetches RSS + enriches)
python -m jobs.update_daily

# Just the enrichment step
python -m jobs.enrich_updates

# Using shell scripts
./scripts/run_pipeline.sh        # macOS/Linux
./scripts/update_daily.sh        # macOS/Linux
```

### Individual Job Modules

| Module | Command | Description |
|--------|---------|-------------|
| `daily_scan` | `python -m jobs.daily_scan` | Crawl all competitors, store raw articles |
| `fetch_rss` | `python -m jobs.fetch_rss` | Fetch articles from Google News RSS feeds |
| `enrich_updates` | `python -m jobs.enrich_updates` | Apply AI classification to raw articles |
| `append_updates` | `python -m jobs.append_updates` | Merge new updates into main dataset |
| `qa_sampler` | `python -m jobs.qa_sampler` | Generate 10% sample for QA review |
| `quarterly_rollup` | `python -m jobs.quarterly_rollup` | Aggregate statistics by quarter |

### Launch the Dashboard

View and analyze collected intelligence:

```bash
streamlit run streamlit_app/Home.py
```

The dashboard will open in your browser at `http://localhost:8501`

**Dashboard Features:**
- Date range filtering (by published or collected date)
- Company multi-select filtering
- Impact level and category filters
- Sortable data table with clickable source links
- Color-coded impact badges
- PDF export with executive summaries
- AI-generated natural language insights

### Scheduled Updates

#### Windows (PowerShell)
```powershell
# Run the automation script
.\automation\nightly_update.ps1
```

Set up Windows Task Scheduler to run this script nightly.

#### macOS/Linux (Bash)
```bash
# Run the daily update script
./scripts/update_daily.sh
```

Set up a cron job:
```bash
# Run every day at 2 AM
0 2 * * * /path/to/project/scripts/update_daily.sh
```

## Project Structure

```
competitor_news_monitor/
├── app/                          # Core application modules
│   ├── crawl.py                  # Web crawling and page discovery
│   ├── parse.py                  # HTML parsing and content extraction
│   ├── classify.py               # AI-powered article classification (GPT-4o-mini)
│   └── summarize.py              # Article summarization
├── jobs/                         # Batch processing jobs
│   ├── daily_scan.py             # Raw data collection from websites
│   ├── fetch_rss.py              # RSS feed integration
│   ├── enrich_updates.py         # AI classification and enrichment
│   ├── append_updates.py         # Data merging utility
│   ├── update_daily.py           # Pipeline orchestration
│   ├── qa_sampler.py             # QA sample generation
│   └── quarterly_rollup.py       # Quarterly analytics
├── config/
│   └── monitors.yaml             # Competitor and crawl configuration
├── automation/
│   └── nightly_update.ps1        # Windows automation script
├── scripts/
│   ├── run_pipeline.sh           # Main pipeline executor (Linux/macOS)
│   └── update_daily.sh           # Daily update script (Linux/macOS)
├── streamlit_app/
│   └── Home.py                   # Streamlit dashboard
├── data/                         # Output directory
│   ├── updates.csv               # Raw crawled articles
│   └── enriched_updates.csv      # AI-enriched articles
├── exports/                      # Exported reports
│   ├── qa_sample_YYYYMMDD.csv    # QA review samples
│   └── quarterly_rollup.csv      # Aggregated statistics
├── logs/                         # Automation logs
├── requirements.txt              # Python dependencies
├── DEPLOYMENT.md                 # Server deployment guide
└── README.md
```

## How It Works

1. **Crawl**: The system starts from configured URLs and discovers article links using breadth-first traversal
2. **Parse**: Extracts article title, publish date, and body text from HTML (with Playwright fallback for JS-heavy sites)
3. **Deduplicate**: Uses SHA-256 hashing on `(company, normalized_url)` to prevent duplicates
4. **Classify**: Uses GPT-4o-mini to categorize and assess impact (11 categories, 3 impact levels)
5. **Summarize**: Generates concise 40-80 word summaries focusing on strategic signals
6. **Store**: Saves structured data to CSV in `data/`
7. **Visualize**: Dashboard displays trends, insights, and enables PDF export

## Article Classification

### Categories
| Category | Description |
|----------|-------------|
| Product/Feature | New features, product updates, GA releases |
| Pricing/Plans | Pricing changes, new plans, packaging |
| Partnership | Strategic partnerships, integrations |
| Acquisition/Investment | M&A activity, funding rounds |
| Case Study/Customer | Customer success stories, testimonials |
| Events/Webinar | Conferences, webinars, workshops |
| Best Practices/Guides | Educational content, how-to guides |
| Security/Compliance | Security updates, certifications |
| Hiring/Leadership | Team changes, executive announcements |
| Company News | General company announcements |
| Other | Miscellaneous content |

### Impact Levels
| Level | Criteria |
|-------|----------|
| **High** | Pricing changes, major GA features, acquisitions, big partnerships, security incidents |
| **Medium** | Meaningful feature updates, significant case studies, notable events |
| **Low** | Generic tips, routine posts, educational content |

## Data Output

### Data Files

| File | Description | Columns |
|------|-------------|---------|
| `data/updates.csv` | Raw crawled articles | id, company, source_url, title, published_at, collected_at, clean_text |
| `data/enriched_updates.csv` | AI-enriched articles | + summary, category, impact |

### Export Formats
- **CSV**: Standard data exports
- **Excel (XLSX)**: Formatted spreadsheets
- **JSON**: API-friendly format
- **PDF**: Executive summaries with company logo

## Dependencies

### Core Libraries
| Library | Purpose |
|---------|---------|
| `requests` & `beautifulsoup4` | Web scraping and HTML parsing |
| `playwright` | JavaScript-rendered page support |
| `openai` | GPT-4o-mini for classification/summarization |
| `streamlit` | Interactive dashboard |
| `pandas` | Data manipulation |
| `feedparser` | RSS feed parsing |
| `tenacity` | Retry logic with exponential backoff |
| `pydantic` | Configuration validation |
| `python-dotenv` | Environment variable loading |
| `reportlab` | PDF generation |

See `requirements.txt` for the complete list.

## Deployment

For production deployment on a Linux server (Ubuntu/Debian), see **[DEPLOYMENT.md](DEPLOYMENT.md)** which covers:

- Vultr server setup
- System dependencies for Playwright
- Nginx reverse proxy configuration
- Systemd service for the dashboard
- UFW firewall rules
- Cron job automation
- SSL with Let's Encrypt
- Monitoring and maintenance

## Development

### Adding New Competitors
1. Edit `config/monitors.yaml`
2. Add competitor name and start URLs
3. Run the pipeline

### Customizing Classification
Edit the `SYSTEM` prompt in `app/classify.py` to adjust:
- Categories
- Impact criteria
- Summary style

### Running Quality Checks
```bash
# Generate QA sample (10% of enriched data)
python -m jobs.qa_sampler

# Generate quarterly analytics
python -m jobs.quarterly_rollup
```

## Troubleshooting

### Crawl Issues
- **403/429 errors**: Adjust `request_timeout_s` or add delays between requests
- **Empty content**: Some sites require Playwright (JS rendering) - check the logs
- **Rate limiting**: Reduce `max_pages_per_site` or add longer delays

### API Errors
- **OpenAI rate limits**: The system uses Tenacity for automatic retries with exponential backoff
- **Quota exceeded**: Check your OpenAI usage dashboard
- **API failures**: Graceful fallback returns "Other" category and "Low" impact

### Data Issues
- **Duplicates**: System deduplicates by `(company, source_url)` with SHA-256 hashing
- **Missing dates**: Falls back from JSON-LD → OpenGraph → None
- **Encoding issues**: Text is normalized and cleaned during parsing

## Error Handling & Resilience

- **API Failures**: Graceful fallback with default values
- **Rate Limiting**: Tenacity retry logic with exponential backoff
- **Timeout Handling**: Configurable timeouts with Playwright fallback
- **Duplicate Prevention**: SHA-256 hash-based deduplication
- **Process Locking**: File locks and OS-level mutexes prevent concurrent runs
- **Data Atomicity**: Temporary file writes with atomic replace

## Future Updates

*Coming soon*

## Contributing

Contributions welcome! Please submit pull requests or open issues for bugs and feature requests.
