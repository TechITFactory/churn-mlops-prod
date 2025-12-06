import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


@dataclass
class LabelSettings:
    processed_dir: str
    churn_window_days: int


def _read_user_daily(processed_dir: str) -> pd.DataFrame:
    path = Path(processed_dir) / "user_daily.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path)


def _compute_future_active_sum(active: np.ndarray, window: int) -> np.ndarray:
    """
    For each index i, compute sum(active[i+1 : i+window+1]).
    Uses cumulative sum for O(n).
    """
    n = len(active)
    cs = np.zeros(n + 1, dtype=np.int64)
    cs[1:] = np.cumsum(active.astype(np.int64))

    out = np.zeros(n, dtype=np.int64)
    # future window ends at i+window (inclusive), slice is (i+1 .. i+window)
    for i in range(n):
        start = i + 1
        end = min(n, i + window + 1)
        if start >= n:
            out[i] = 0
        else:
            out[i] = cs[end] - cs[start]
    return out


def build_labels(user_daily: pd.DataFrame, churn_window_days: int) -> pd.DataFrame:
    d = user_daily.copy()

    d["user_id"] = pd.to_numeric(d["user_id"], errors="coerce").astype(int)
    d["as_of_date"] = pd.to_datetime(d["as_of_date"], errors="coerce")

    if "is_active_day" not in d.columns:
        raise ValueError("user_daily must contain 'is_active_day'")

    d["is_active_day"] = pd.to_numeric(d["is_active_day"], errors="coerce").fillna(0).astype(int)

    d = d.sort_values(["user_id", "as_of_date"]).reset_index(drop=True)

    labels = []
    for uid, g in d.groupby("user_id", sort=False):
        active = g["is_active_day"].to_numpy()
        future_sum = _compute_future_active_sum(active, churn_window_days)

        tmp = g[["user_id", "as_of_date"]].copy()
        tmp["future_active_days"] = future_sum

        # Label rule:
        # churn=1 if next window has zero active days
        tmp["churn_label"] = (tmp["future_active_days"] == 0).astype(int)

        # We only trust labels where the full future window is available.
        # So drop the last 'window' days for each user.
        if len(tmp) > churn_window_days:
            tmp = tmp.iloc[:-churn_window_days]
        else:
            tmp = tmp.iloc[0:0]

        labels.append(tmp)

    out = pd.concat(labels, ignore_index=True) if labels else pd.DataFrame(
        columns=["user_id", "as_of_date", "future_active_days", "churn_label"]
    )

    out["as_of_date"] = pd.to_datetime(out["as_of_date"]).dt.date

    return out


def write_labels(labels: pd.DataFrame, processed_dir: str) -> Path:
    out_dir = ensure_dir(processed_dir)
    out_path = Path(out_dir) / "labels_daily.csv"
    labels.to_csv(out_path, index=False)
    return out_path


def _get_churn_window(cfg: Dict[str, Any]) -> int:
    return int(cfg.get("churn", {}).get("window_days", 30))


def parse_args() -> LabelSettings:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Build daily churn labels from user_daily")
    parser.add_argument("--processed-dir", type=str, default=cfg["paths"]["processed"])
    parser.add_argument("--window-days", type=int, default=_get_churn_window(cfg))
    args = parser.parse_args()

    return LabelSettings(
        processed_dir=args.processed_dir,
        churn_window_days=args.window_days,
    )


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()

    logger.info("Reading user_daily...")
    user_daily = _read_user_daily(settings.processed_dir)

    logger.info("Building churn labels with window=%dd...", settings.churn_window_days)
    labels = build_labels(user_daily, settings.churn_window_days)

    out_path = write_labels(labels, settings.processed_dir)
    logger.info("Labels written ✅ -> %s", out_path)
    logger.info("Label rows: %d | churn rate (mean): %.4f", len(labels), labels["churn_label"].mean() if len(labels) else 0.0)


if __name__ == "__main__":
    main()
