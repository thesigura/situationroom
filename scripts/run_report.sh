#!/usr/bin/env bash
set -euo pipefail
python -m src.intel.report --db data/intel.db --out reports/daily_report.md --hours 24
