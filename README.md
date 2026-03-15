# Situation Room — Phase 1 Build

This repository now includes a minimal implementation for:

1. Building a geopolitical watchlist
2. Ingesting posts/replies/reposts into SQLite
3. Producing a basic daily markdown report

## Files

- `src/intel/watchlist.py` — watchlist accounts and categories
- `src/intel/db.py` — SQLite schema + helpers
- `src/intel/ingest.py` — ingestion CLI (`mock` and `snscrape` sources)
- `src/intel/report.py` — daily markdown report generator
- `scripts/run_ingest.sh` — convenient ingestion wrapper
- `scripts/run_report.sh` — convenient reporting wrapper

## Quickstart

```bash
# Ingest mock data (works offline and validates pipeline end-to-end)
./scripts/run_ingest.sh mock

# Generate the daily report
./scripts/run_report.sh
```

Outputs:

- Database: `data/intel.db`
- Report: `reports/daily_report.md`

## Live ingestion with snscrape

If you want live public data from X, install `snscrape` and run:

```bash
python -m src.intel.ingest --source snscrape --db data/intel.db --lookback-hours 24 --limit-per-account 100
```

## Suggested cron schedule

```cron
*/20 * * * * cd /workspace/situationroom && ./scripts/run_ingest.sh snscrape >> logs/ingest.log 2>&1
35 6 * * * cd /workspace/situationroom && ./scripts/run_report.sh >> logs/report.log 2>&1
```
