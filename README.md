# Situation Room — Phase 1 Build

This repository includes a runnable Phase-1 pipeline for:

1. Building a geopolitical watchlist
2. Ingesting posts/replies/reposts into SQLite
3. Producing a basic daily markdown report

## Files

- `src/intel/watchlist.py` — watchlist accounts and categories
- `src/intel/db.py` — SQLite schema + helpers
- `src/intel/ingest.py` — ingestion CLI (`mock`, `snscrape`, and `xapi` sources)
- `src/intel/report.py` — daily markdown report generator
- `scripts/run_ingest.sh` — convenient ingestion wrapper
- `scripts/run_report.sh` — convenient reporting wrapper
- `scripts/run_ui.sh` — launch the Situation Room web interface
- `scripts/run_preview.sh` — generate static HTML preview
- `src/intel/ui.py` — Streamlit dashboard for live monitoring
- `src/intel/preview.py` — static HTML preview generator

## Quickstart

```bash
# Ingest mock data (works offline and validates pipeline end-to-end)
./scripts/run_ingest.sh mock

# Generate the daily report
./scripts/run_report.sh

# Launch the Situation Room interface
./scripts/run_ui.sh

# Generate static preview (no Streamlit required)
./scripts/run_preview.sh
```

Outputs:

- Database: `data/intel.db`
- Report: `reports/daily_report.md`

## Live ingestion option A: snscrape (public scraping)

```bash
python -m pip install -r requirements.txt
python -m src.intel.ingest --source snscrape --db data/intel.db --lookback-hours 24 --limit-per-account 100
```

If you see `snscrape is required...` while installed, make sure you installed with the **same interpreter** (`python -m pip ...`) used to run ingestion.

## Live ingestion option B: official X API (recommended fallback)

Set a bearer token and run with `xapi` source:

```bash
export X_BEARER_TOKEN='YOUR_TOKEN'
python -m src.intel.ingest --source xapi --db data/intel.db --lookback-hours 24 --limit-per-account 100
```

Incremental mode is on by default (`crawl_state` table). Use `--no-resume-state` to force lookback-only crawling.

## What you were missing for robust X crawling

The earlier version worked, but these are the critical production pieces to avoid gaps:

- **Incremental checkpoints** per account so each run resumes from the last seen post (`crawl_state` table).
- **Per-account failure isolation** so one handle failing does not kill the entire run (`crawl_errors` table).
- **Deduplicated upserts** with stable post IDs (already done via `INSERT OR REPLACE`).
- **Operational scheduling** (cron) and logs.
- **Source fallback plan** if X blocks scraping (official API fallback now supported via `source=xapi`).

### Important platform limitations

- `snscrape` can break when X changes anti-bot behavior.
- High-engagement comments and full repost/reply graphs are often incomplete via public scraping.
- For high reliability, prefer official API access for core accounts and keep `snscrape` as secondary.

## Suggested cron schedule

```cron
*/20 * * * * cd /workspace/situationroom && ./scripts/run_ingest.sh snscrape >> logs/ingest.log 2>&1
35 6 * * * cd /workspace/situationroom && ./scripts/run_report.sh >> logs/report.log 2>&1
```


## Situation Room Interface

The UI includes:
- KPI cards (accounts, captured items, active accounts, crawler errors)
- Live feed with post/reply/repost filters
- Account activity table by category and priority
- Crawler health tab (checkpoints + recent errors)
- Report preview tab showing top engagement rows

Open: `http://localhost:8501` after running `./scripts/run_ui.sh`.


## Preview

If you want a quick shareable snapshot without running Streamlit, generate:

```bash
./scripts/run_preview.sh
```

Output: `preview/situation_room_preview.html`
