#!/usr/bin/env bash
set -euo pipefail
python -m streamlit run src/intel/ui.py --server.port "${PORT:-8501}" --server.address 0.0.0.0
