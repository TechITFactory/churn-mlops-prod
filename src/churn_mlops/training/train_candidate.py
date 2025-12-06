import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import HistGradientBoostingClassifier

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


@dataclass
class TrainSettings:
    features_dir: str
    models_dir: str
    metrics_dir: str
    test_size: float
    random_state: int


def _read_training_dataset(features_dir: str) -> pd.DataFrame:
    path = Path(features_dir) / "training_dataset.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _time_split(df: pd.DataFrame, test_size: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if "as_of_date" not in df.columns:
        raise ValueError("training_dataset must contain 'as_of_date' for time-aware split")

    d = df.copy()
    d["as_of_date"] = pd.to_datetime(d["as_of_date"], errors="coerce")
    d = d.dropna(subset=["as_of_date"]).reset_index(drop=True)

    dates = sorted(d["as_of_date"].dt.date.unique().tolist())

    if len(dates) < 5:
        d = d.sort_values("as_of_date")
        cutoff_idx = int(len(d) * (1 - test_size))
        return d.iloc[:cutoff_idx].copy(), d.iloc[cutoff_idx:].copy()

    cut_at = int(len(dates) * (1 - test_size))
    cut_at = max(1, min(cut_at, len(dates) - 1))
    cutoff_date = dates[cut_at - 1]

    train_df = d[d["as_of_date"].dt.date <= cutoff_date].copy()
    test_df = d[d["as_of_date"].dt.date > cutoff_date].copy()
    return train_df, test_df


def _select_feature_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    if "churn_label" not in df.columns:
        raise ValueError("training_dataset must contain 'churn_label'")

    y = pd.to_numeric(df["churn_label"], errors="coerce").fillna(0).astype(int)

    drop_cols = {"churn_label", "user_id", "as_of_date", "signup_date"}
    X = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    return X, y


def _infer_column_types(X: pd.DataFrame) -> Tuple[List[str], List[str]]:
    cat_cols, num_cols = [], []
    for col in X.columns:
        if pd.api.types.is_numeric_dtype(X[col]):
            num_cols.append(col)
        else:
            cat_cols.append(col)
    return cat_cols, num_cols


def _build_pipeline(cat_cols: List[str], num_cols: List[str], random_state: int) -> Pipeline:
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value=0.0)),
        ]
    )

    pre = ColumnTransformer(
        transformers=[
            ("cat", categorical, cat_cols),
            ("num", numeric, num_cols),
        ],
        remainder="drop",
    )

    # Strong candidate model
    clf = HistGradientBoostingClassifier(
        random_state=random_state,
        learning_rate=0.08,
        max_depth=6,
        max_iter=250,
    )

    return Pipeline(steps=[("preprocess", pre), ("model", clf)])


def _evaluate(model: Pipeline, X_test: pd.DataFrame, y_test: pd.Series) -> Dict[str, Any]:
    proba = model.predict_proba(X_test)[:, 1]

    pr_auc = float(average_precision_score(y_test, proba))
    roc_auc = float(roc_auc_score(y_test, proba)) if len(np.unique(y_test)) > 1 else 0.0

    y_pred = (proba >= 0.5).astype(int)

    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred).tolist()

    precisions, recalls, _ = precision_recall_curve(y_test, proba)
    pr_curve_sample = {
        "precision_head": [float(x) for x in precisions[:10]],
        "recall_head": [float(x) for x in recalls[:10]],
    }

    return {
        "pr_auc": pr_auc,
        "roc_auc": roc_auc,
        "confusion_matrix": cm,
        "classification_report": report,
        "pr_curve_sample": pr_curve_sample,
    }


def _artifact_names(prefix: str = "candidate_hgb") -> Tuple[str, str]:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}.joblib", f"{prefix}_{stamp}.json"


def train_candidate(settings: TrainSettings) -> Tuple[Path, Path, Dict[str, Any]]:
    df = _read_training_dataset(settings.features_dir)

    train_df, test_df = _time_split(df, settings.test_size)

    X_train, y_train = _select_feature_columns(train_df)
    X_test, y_test = _select_feature_columns(test_df)

    cat_cols, num_cols = _infer_column_types(X_train)

    model = _build_pipeline(cat_cols, num_cols, random_state=settings.random_state)
    model.fit(X_train, y_train)

    metrics = _evaluate(model, X_test, y_test)

    models_dir = ensure_dir(settings.models_dir)
    metrics_dir = ensure_dir(settings.metrics_dir)

    model_file, metrics_file = _artifact_names()

    model_path = Path(models_dir) / model_file
    metrics_path = Path(metrics_dir) / metrics_file

    joblib.dump(
        {
            "model": model,
            "cat_cols": cat_cols,
            "num_cols": num_cols,
            "settings": settings.__dict__,
        },
        model_path,
    )

    meta = {
        "model_type": "hist_gradient_boosting",
        "artifact": model_file,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "churn_rate_train": float(pd.Series(y_train).mean()) if len(y_train) else 0.0,
        "churn_rate_test": float(pd.Series(y_test).mean()) if len(y_test) else 0.0,
        "metrics": metrics,
    }

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return model_path, metrics_path, meta


def parse_args() -> TrainSettings:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Train candidate churn model (HistGradientBoosting)")
    parser.add_argument("--features-dir", type=str, default=cfg["paths"]["features"])
    parser.add_argument("--models-dir", type=str, default=cfg["paths"]["models"])
    parser.add_argument("--metrics-dir", type=str, default=cfg["paths"]["metrics"])
    args = parser.parse_args()

    return TrainSettings(
        features_dir=args.features_dir,
        models_dir=args.models_dir,
        metrics_dir=args.metrics_dir,
        test_size=float(cfg.get("training", {}).get("test_size", 0.2)),
        random_state=int(cfg.get("training", {}).get("random_state", 42)),
    )


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()

    logger.info("Training candidate model with time-aware split...")
    model_path, metrics_path, meta = train_candidate(settings)

    logger.info("Model saved ✅ -> %s", model_path)
    logger.info("Metrics saved ✅ -> %s", metrics_path)
    logger.info("PR-AUC: %.4f | ROC-AUC: %.4f", meta["metrics"]["pr_auc"], meta["metrics"]["roc_auc"])


if __name__ == "__main__":
    main()
