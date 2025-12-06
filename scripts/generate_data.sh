#!/usr/bin/env bash
set -euo pipefail

# Activate venv if present
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

python -m churn_mlops.data.generate_synthetic \
  --n-users 2000 \
  --days 120 \
  --start-date 2025-01-01 \
  --seed 42 \
  --paid-ratio 0.35 \
  --churn-base-rate 0.35
