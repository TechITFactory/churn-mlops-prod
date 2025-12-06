from pathlib import Path
import pandas as pd

from churn_mlops.training.build_labels import build_labels

def test_build_labels_basic():
    path = Path("data/processed/user_daily.csv")
    if not path.exists():
        return

    ud = pd.read_csv(path)
    labels = build_labels(ud, churn_window_days=30)

    assert set(["user_id", "as_of_date", "churn_label"]).issubset(labels.columns)
