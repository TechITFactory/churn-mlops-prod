from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging


DRIFT_FEATURE_COLS = [
    "sessions_7d",
    "watch_minutes_7d",
    "watch_minutes_14d",
    "watch_minutes_30d",
    "quiz_attempts_7d",
    "quiz_avg_score_7d",
]


def _apply_high_drift(df: pd.DataFrame, strength: float, seed: int) -> tuple[pd.DataFrame, Dict[str, float]]:
    """Apply a deterministic distribution shift to known drift-check columns."""

    rng = np.random.default_rng(seed)
    out = df.copy()
    changes: Dict[str, float] = {}

    # Multiplicative + additive shifts that strongly change distributions.
    # Strength ~ 1.0 is mild, 3.0+ is usually enough to trigger PSI FAIL.
    mult = max(1.0, float(strength))

    def _shift_nonneg(col: str, mul: float, add: float, jitter_scale: float = 0.0) -> None:
        if col not in out.columns:
            return
        x = pd.to_numeric(out[col], errors="coerce").fillna(0.0).astype(float)
        if jitter_scale > 0:
            jitter = rng.normal(loc=0.0, scale=jitter_scale, size=len(x))
        else:
            jitter = 0.0
        y = x * mul + add + jitter
        out[col] = np.clip(y, 0.0, None)
        changes[col] = float(mul)

    # Sessions: make users "much more active"
    _shift_nonneg("sessions_7d", mul=1.0 + 0.8 * mult, add=3.0 * mult, jitter_scale=0.5 * mult)

    # Watch minutes: significantly heavier usage
    _shift_nonneg("watch_minutes_7d", mul=1.0 + 2.0 * mult, add=50.0 * mult, jitter_scale=10.0 * mult)
    _shift_nonneg("watch_minutes_14d", mul=1.0 + 2.2 * mult, add=120.0 * mult, jitter_scale=15.0 * mult)
    _shift_nonneg("watch_minutes_30d", mul=1.0 + 2.5 * mult, add=220.0 * mult, jitter_scale=20.0 * mult)

    # Quiz attempts: more attempts, more variance
    _shift_nonneg("quiz_attempts_7d", mul=1.0 + 1.5 * mult, add=1.0 * mult, jitter_scale=0.4 * mult)

    # Quiz score: shift down (different distribution direction)
    if "quiz_avg_score_7d" in out.columns:
        q = pd.to_numeric(out["quiz_avg_score_7d"], errors="coerce").astype(float)
        # Keep NaNs as NaNs; only shift non-null.
        mask = q.notna()
        jitter = rng.normal(loc=0.0, scale=6.0 * mult, size=int(mask.sum()))
        shifted = (q[mask] - (12.0 * mult) + jitter).clip(lower=0.0, upper=100.0)
        out.loc[mask, "quiz_avg_score_7d"] = shifted
        changes["quiz_avg_score_7d"] = -float(12.0 * mult)

    return out, changes


def main() -> None:
    cfg = load_config()
    logger = setup_logging(cfg)

    parser = argparse.ArgumentParser(
        description="Modify user_features_daily.csv to simulate HIGH drift for demo purposes."
    )
    parser.add_argument(
        "--strength",
        type=float,
        default=3.0,
        help="How strong the shift is. 3.0+ usually triggers PSI FAIL.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=7,
        help="Random seed for deterministic jitter.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite user_features_daily.csv. If not set, writes user_features_daily_drifted.csv.",
    )

    args = parser.parse_args()

    features_dir = Path(cfg["paths"]["features"])
    src = features_dir / "user_features_daily.csv"
    if not src.exists():
        raise FileNotFoundError(
            f"Missing {src}. Run feature build first: python -m churn_mlops.features.build_features"
        )

    df = pd.read_csv(src)

    # Only touch columns used by drift check; leave the rest unchanged.
    out, changes = _apply_high_drift(df, strength=args.strength, seed=args.seed)

    dst = src if args.in_place else (features_dir / "user_features_daily_drifted.csv")
    out.to_csv(dst, index=False)

    logger.info("High-drift demo written -> %s", dst)
    logger.info("Changed columns (strength=%s): %s", args.strength, ", ".join(sorted(changes.keys())))
    logger.info("Drift-check columns: %s", ", ".join(DRIFT_FEATURE_COLS))


if __name__ == "__main__":
    main()
