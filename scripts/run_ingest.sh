#!/usr/bin/env bash
set -euo pipefail
python -m src.intel.ingest --db data/intel.db --source "${1:-mock}" --lookback-hours 24 --limit-per-account 100
