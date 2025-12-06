import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


@dataclass
class FeatureSettings:
    processed_dir: str
    features_dir: str
    windows: List[int]


DEFAULT_WINDOWS = [7, 14, 30]


def _get_windows(cfg: Dict[str, Any]) -> List[int]:
    w = cfg.get("features", {}).get("windows_days")
    if isinstance(w, list) and all(isinstance(x, int) for x in w):
        return w
    return DEFAULT_WINDOWS


def _read_user_daily(processed_dir: str) -> pd.DataFrame:
    path = Path(processed_dir) / "user_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _prep_base(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()

    d["user_id"] = pd.to_numeric(d["user_id"], errors="coerce").astype(int)
    d["as_of_date"] = pd.to_datetime(d["as_of_date"], errors="coerce")

    numeric_cols = [
        "total_events",
        "logins_count",
        "enroll_count",
        "watch_minutes_sum",
        "quiz_attempts_count",
        "payment_success_count",
        "payment_failed_count",
        "support_ticket_count",
        "is_active_day",
        "days_since_signup",
    ]
    for c in numeric_cols:
        if c not in d.columns:
            d[c] = 0

    if "quiz_avg_score" not in d.columns:
        d["quiz_avg_score"] = np.nan

    for c in numeric_cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)

    d["quiz_avg_score"] = pd.to_numeric(d["quiz_avg_score"], errors="coerce")

    d = d.sort_values(["user_id", "as_of_date"]).reset_index(drop=True)
    return d


def _add_days_since_last_activity(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()

    x["last_active_dt"] = np.where(
        x["is_active_day"] > 0,
        x["as_of_date"].values.astype("datetime64[ns]"),
        np.datetime64("NaT"),
    )
    x["last_active_dt"] = pd.to_datetime(x["last_active_dt"], errors="coerce")

    x["last_active_dt"] = x.groupby("user_id")["last_active_dt"].ffill()

    delta = (x["as_of_date"] - x["last_active_dt"]).dt.days
    x["days_since_last_activity"] = delta.fillna(x["days_since_signup"]).clip(lower=0)

    return x.drop(columns=["last_active_dt"])


def _add_rolling_features(d: pd.DataFrame, windows: List[int]) -> pd.DataFrame:
    x = d.copy()

    base_sum_cols = [
        "is_active_day",
        "total_events",
        "logins_count",
        "enroll_count",
        "watch_minutes_sum",
        "quiz_attempts_count",
        "payment_success_count",
        "payment_failed_count",
        "support_ticket_count",
    ]

    for w in windows:
        for col in base_sum_cols:
            if col == "is_active_day":
                out_col = f"active_days_{w}d"
            elif col == "total_events":
                out_col = f"events_{w}d"
            elif col == "watch_minutes_sum":
                out_col = f"watch_minutes_{w}d"
            elif col.endswith("_count"):
                out_col = f"{col.replace('_count', '')}_{w}d"
            else:
                out_col = f"{col}_{w}d"

            rolled = (
                x.groupby("user_id")[col]
                .rolling(window=w, min_periods=1)
                .sum()
                .reset_index(level=0, drop=True)
            )
            x[out_col] = rolled.astype(float)

        # Rolling mean quiz score
        rolled_mean = (
            x.groupby("user_id")["quiz_avg_score"]
            .rolling(window=w, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        x[f"quiz_avg_score_{w}d"] = rolled_mean

    # Payment fail rate (use 30d if exists, else largest window)
    w_ref = 30 if 30 in windows else max(windows)
    fail_col = f"payment_failed_{w_ref}d"
    succ_col = f"payment_success_{w_ref}d"
    if fail_col in x.columns and succ_col in x.columns:
        denom = x[fail_col] + x[succ_col]
        x[f"payment_fail_rate_{w_ref}d"] = np.where(denom > 0, x[fail_col] / denom, 0.0)

    return x


def build_features(processed_dir: str, features_dir: str, windows: List[int]) -> Path:
    df = _read_user_daily(processed_dir)
    df = _prep_base(df)
    df = _add_days_since_last_activity(df)
    df = _add_rolling_features(df, windows)

    keep_static = [
        "user_id",
        "as_of_date",
        "signup_date",
        "days_since_signup",
        "plan",
        "is_paid",
        "country",
        "marketing_source",
    ]
    if "engagement_score" in df.columns:
        keep_static.append("engagement_score")

    engineered = [
        c for c in df.columns if c.endswith("d") or c.startswith("days_since_last_activity")
    ]
    engineered = sorted(set(engineered))

    base_daily = [
        "is_active_day",
        "total_events",
        "logins_count",
        "enroll_count",
        "watch_minutes_sum",
        "quiz_attempts_count",
        "quiz_avg_score",
        "payment_success_count",
        "payment_failed_count",
        "support_ticket_count",
    ]
    base_daily = [c for c in base_daily if c in df.columns]

    final_cols: List[str] = []
    for c in keep_static + base_daily + engineered:
        if c in df.columns and c not in final_cols:
            final_cols.append(c)

    out_df = df[final_cols].copy()

    out_dir = ensure_dir(features_dir)
    out_path = Path(out_dir) / "user_features_daily.csv"
    out_df.to_csv(out_path, index=False)

    return out_path


def parse_args() -> FeatureSettings:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Build churn features from user_daily table")
    parser.add_argument("--processed-dir", type=str, default=cfg["paths"]["processed"])
    parser.add_argument("--features-dir", type=str, default=cfg["paths"]["features"])

    args = parser.parse_args()
    windows = _get_windows(cfg)

    return FeatureSettings(
        processed_dir=args.processed_dir,
        features_dir=args.features_dir,
        windows=windows,
    )


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()

    logger.info("Building features with windows=%s", settings.windows)
    out_path = build_features(settings.processed_dir, settings.features_dir, settings.windows)

    logger.info("Features written ✅ -> %s", out_path)


if __name__ == "__main__":
    main()
