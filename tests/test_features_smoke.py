import pandas as pd
from pathlib import Path

from churn_mlops.features.build_features import build_features

def test_build_features_creates_file(tmp_path):
    # Use real project processed file if present; otherwise skip
    processed = Path("data/processed/user_daily.csv")
    if not processed.exists():
        return

    out_dir = tmp_path / "features"
    out_path = build_features("data/processed", str(out_dir), windows=[7, 14, 30])

    assert out_path.exists()

    df = pd.read_csv(out_path)
    assert "user_id" in df.columns
    assert "as_of_date" in df.columns
    assert "days_since_last_activity" in df.columns
    assert "active_days_7d" in df.columns
