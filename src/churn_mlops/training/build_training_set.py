import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


@dataclass
class TrainingSetSettings:
    processed_dir: str
    features_dir: str
    output_dir: str


def _read_features(features_dir: str) -> pd.DataFrame:
    path = Path(features_dir) / "user_features_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _read_labels(processed_dir: str) -> pd.DataFrame:
    path = Path(processed_dir) / "labels_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def build_training_set(processed_dir: str, features_dir: str, output_dir: str) -> Path:
    features = _read_features(features_dir)
    labels = _read_labels(processed_dir)

    features["user_id"] = pd.to_numeric(features["user_id"], errors="coerce").astype(int)
    labels["user_id"] = pd.to_numeric(labels["user_id"], errors="coerce").astype(int)

    features["as_of_date"] = pd.to_datetime(features["as_of_date"], errors="coerce").dt.date
    labels["as_of_date"] = pd.to_datetime(labels["as_of_date"], errors="coerce").dt.date

    df = features.merge(labels[["user_id", "as_of_date", "churn_label"]], on=["user_id", "as_of_date"], how="inner")

    # Drop obvious non-feature columns if present
    drop_cols = {"future_active_days"}
    for c in drop_cols:
        if c in df.columns:
            df = df.drop(columns=[c])

    # Ensure label is int
    df["churn_label"] = pd.to_numeric(df["churn_label"], errors="coerce").fillna(0).astype(int)

    out_dir = ensure_dir(output_dir)
    out_path = Path(out_dir) / "training_dataset.csv"
    df.to_csv(out_path, index=False)

    return out_path


def parse_args() -> TrainingSetSettings:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Build training dataset by joining features and labels")
    parser.add_argument("--processed-dir", type=str, default=cfg["paths"]["processed"])
    parser.add_argument("--features-dir", type=str, default=cfg["paths"]["features"])
    parser.add_argument("--output-dir", type=str, default=cfg["paths"]["features"])
    args = parser.parse_args()

    return TrainingSetSettings(
        processed_dir=args.processed_dir,
        features_dir=args.features_dir,
        output_dir=args.output_dir,
    )


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()

    logger.info("Building training dataset...")
    out_path = build_training_set(settings.processed_dir, settings.features_dir, settings.output_dir)

    df = pd.read_csv(out_path)
    logger.info("Training dataset written ✅ -> %s", out_path)
    logger.info("Rows=%d | Users=%d | Churn rate=%.4f", len(df), df["user_id"].nunique(), df["churn_label"].mean() if len(df) else 0.0)


if __name__ == "__main__":
    main()
