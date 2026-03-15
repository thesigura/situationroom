#!/usr/bin/env bash
set -euo pipefail
python -m src.intel.preview --db data/intel.db --out-dir preview --hours 24 --limit 30
