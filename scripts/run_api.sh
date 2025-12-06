#!/usr/bin/env bash
set -euo pipefail

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

# Make sure package is installed in editable mode
pip install -e . >/dev/null

uvicorn churn_mlops.api.app:app --host 0.0.0.0 --port 8000
