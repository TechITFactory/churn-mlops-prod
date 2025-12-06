import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


@dataclass
class BatchScoreSettings:
    features_dir: str
    models_dir: str
    predictions_dir: str
    as_of_date: Optional[str]
    top_k: int


def _read_features(features_dir: str) -> pd.DataFrame:
    path = Path(features_dir) / "user_features_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _load_production_model(models_dir: str):
    prod_path = Path(models_dir) / "production_latest.joblib"
    if not prod_path.exists():
        raise FileNotFoundError(
            f"Missing production model alias: {prod_path}. "
            f"Run ./scripts/promote_model.sh first."
        )

    blob = joblib.load(prod_path)

    # Our saved format is a dict with "model"
    if isinstance(blob, dict) and "model" in blob:
        return blob["model"], blob

    # fallback if someone saved only estimator
    return blob, {"model": blob}


def _pick_as_of_date(df: pd.DataFrame, as_of_date: Optional[str]) -> str:
    if "as_of_date" not in df.columns:
        raise ValueError("Features must contain 'as_of_date'")

    d = df.copy()
    d["as_of_date"] = pd.to_datetime(d["as_of_date"], errors="coerce")

    if as_of_date:
        target = pd.to_datetime(as_of_date).date()
        if target not in set(d["as_of_date"].dt.date.unique()):
            raise ValueError(
                f"Requested as_of_date={as_of_date} not found in features. "
                f"Available range: {d['as_of_date'].min().date()} -> {d['as_of_date'].max().date()}"
            )
        return target.isoformat()

    # default to latest available date
    latest = d["as_of_date"].max().date()
    return latest.isoformat()


def _prepare_scoring_frame(features: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    f = features.copy()
    f["as_of_date"] = pd.to_datetime(f["as_of_date"], errors="coerce").dt.date

    day_df = f[f["as_of_date"] == pd.to_datetime(as_of_date).date()].copy()
    if day_df.empty:
        raise ValueError(f"No feature rows found for as_of_date={as_of_date}")

    return day_df


def _split_X(day_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return:
    - X for model
    - meta columns for output
    """
    meta_cols = [c for c in [
        "user_id",
        "as_of_date",
        "plan",
        "is_paid",
        "country",
        "marketing_source",
        "days_since_signup",
        "days_since_last_activity",
    ] if c in day_df.columns]

    meta = day_df[meta_cols].copy()

    drop_cols = {"user_id", "as_of_date", "signup_date"}
    X = day_df.drop(columns=[c for c in drop_cols if c in day_df.columns], errors="ignore")

    # If someone accidentally left label in features, drop it
    if "churn_label" in X.columns:
        X = X.drop(columns=["churn_label"])

    return X, meta


def _write_predictions(
    meta: pd.DataFrame,
    proba: pd.Series,
    predictions_dir: str,
    as_of_date: str,
    top_k: int,
) -> Path:
    out_dir = ensure_dir(predictions_dir)

    out = meta.copy()
    out["churn_risk"] = proba.astype(float)

    # Rank high risk first
    out = out.sort_values("churn_risk", ascending=False).reset_index(drop=True)
    out["risk_rank"] = out.index + 1

    # Helpful output slices
    if top_k > 0:
        top_preview = out.head(top_k)
        # Keep a small preview file too (nice for demos)
        preview_path = Path(out_dir) / f"churn_top_{top_k}_{as_of_date}.csv"
        top_preview.to_csv(preview_path, index=False)

    out_path = Path(out_dir) / f"churn_predictions_{as_of_date}.csv"
    out.to_csv(out_path, index=False)

    return out_path


def batch_score(settings: BatchScoreSettings) -> Path:
    features = _read_features(settings.features_dir)
    model, _ = _load_production_model(settings.models_dir)

    chosen_date = _pick_as_of_date(features, settings.as_of_date)
    day_df = _prepare_scoring_frame(features, chosen_date)

    X, meta = _split_X(day_df)

    # predict_proba must exist for our models
    proba = model.predict_proba(X)[:, 1]

    out_path = _write_predictions(
        meta=meta,
        proba=pd.Series(proba),
        predictions_dir=settings.predictions_dir,
        as_of_date=chosen_date,
        top_k=settings.top_k,
    )
    return out_path


def parse_args() -> BatchScoreSettings:
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Batch churn scoring using production_latest model")
    parser.add_argument("--features-dir", type=str, default=cfg["paths"]["features"])
    parser.add_argument("--models-dir", type=str, default=cfg["paths"]["models"])

    # Safe default even if config doesn't include predictions path
    default_pred = cfg.get("paths", {}).get("predictions", "data/predictions")
    parser.add_argument("--predictions-dir", type=str, default=default_pred)

    parser.add_argument("--as-of-date", type=str, default=None, help="YYYY-MM-DD; default=latest available")
    parser.add_argument("--top-k", type=int, default=50, help="also writes a small top-K file")

    args = parser.parse_args()

    return BatchScoreSettings(
        features_dir=args.features_dir,
        models_dir=args.models_dir,
        predictions_dir=args.predictions_dir,
        as_of_date=args.as_of_date,
        top_k=args.top_k,
    )


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()

    logger.info("Running batch scoring...")
    out_path = batch_score(settings)

    logger.info("Predictions written ✅ -> %s", out_path)


if __name__ == "__main__":
    main()
