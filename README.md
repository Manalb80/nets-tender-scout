# NETS Tender Scout

Presales tender intelligence system for NETS International.
Automatically discovers, scores, and manages tenders from the Sindh Bank portal.

## What it does

1. **Scrapes** the Sindh Bank tenders portal every morning (05:47 UK time)
2. **Scores** each tender against 15 NETS solution categories
3. **Stores** only qualified tenders (score 70+) in the database
4. **Displays** a live intelligence dashboard with pipeline funnel, discovery feed, and tender detail panels
5. **Generates** technical proposals using past NETS work as reference (when connected to the RAG agent)
6. **Audits** proposals for compliance before human review

## Quick start

### Option A: Docker (recommended for deployment)

```bash
docker-compose up -d
```

Open http://localhost:8000 in your browser.

### Option B: Run directly (for development)

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (first time only)
playwright install chromium

# Start the server
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000

## Project structure

```
nets-tender-scout/
  backend/
    main.py          # FastAPI server, scheduler, API endpoints
    models.py        # Database models (SQLAlchemy ORM)
    scorer.py        # NETS solution scoring engine
    scraper.py       # Sindh Bank portal scraper (Playwright)
  frontend/
    index.html       # Dashboard (single-page app)
  scripts/
    seed_data.py     # Import data from Claude Artifact DB export
  data/
    tender_scout.db  # SQLite database (created on first run)
  Dockerfile
  docker-compose.yml
  requirements.txt
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tenders` | List all qualified tenders |
| GET | `/api/tenders/{id}` | Get one tender |
| GET | `/api/scans` | Scan history |
| GET | `/api/proposals` | Generated proposals |
| GET | `/api/solutions` | NETS solution taxonomy |
| GET | `/api/health` | System health check |
| POST | `/api/scan/trigger` | Manually trigger a scan |
| GET | `/` | Dashboard UI |

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./tender_scout.db` | Database connection string |
| `SCAN_HOUR` | `5` | Hour (24h) for daily scan (UK time) |
| `SCAN_MINUTE` | `47` | Minute for daily scan |

### Using PostgreSQL instead of SQLite

```bash
# In docker-compose.yml, uncomment the postgres service, then:
DATABASE_URL=postgresql://nets:changeme@postgres:5432/tender_scout
```

## Deployment to NETS enterprise portal

1. Copy this folder to the deployment server
2. Install Docker and Docker Compose
3. Run `docker-compose up -d`
4. Configure your reverse proxy (nginx/IIS) to point to port 8000
5. Add the NETS logo as `frontend/assets/nets-logo.png`

For IIS deployment (Windows Server):
- Install Python 3.12+ and the requirements
- Run with `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- Set up as a Windows Service using NSSM or similar

## Architecture

```
Browser (Dashboard)
    |
    | fetch("/api/...")
    v
FastAPI Server (port 8000)
    |
    |-- APScheduler (cron: 05:47 UK daily)
    |       |
    |       v
    |   Playwright scraper --> sindhbank.com.pk/tenders
    |
    |-- SQLAlchemy ORM
    |       |
    |       v
    |   SQLite / PostgreSQL
    |
    v
Static files (frontend/index.html)
```
