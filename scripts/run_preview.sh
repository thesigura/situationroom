#!/usr/bin/env bash
set -euo pipefail
python -m src.intel.preview --db data/intel.db --out preview/situation_room_preview.html --hours 24 --limit 30
