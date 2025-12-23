#!/usr/bin/env bash
set -euo pipefail

# Demo helper: forces HIGH drift by modifying user_features_daily.csv
# Usage:
#   ./scripts/make_high_drift_demo.sh           # default strength=3, in-place
#   ./scripts/make_high_drift_demo.sh 5         # stronger drift

STRENGTH="${1:-3}"

python -m churn_mlops.monitoring.make_high_drift_demo --in-place --strength "$STRENGTH"
python -m churn_mlops.monitoring.run_drift_check
