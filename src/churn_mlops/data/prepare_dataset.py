import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


@dataclass
class PrepareSettings:
    raw_dir: str
    processed_dir: str


def _read_raw(raw_dir: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    raw_path = Path(raw_dir)
    users = pd.read_csv(raw_path / "users.csv")
    events = pd.read_csv(raw_path / "events.csv")
    return users, events


def _clean_users(users: pd.DataFrame) -> pd.DataFrame:
    u = users.copy()

    u["user_id"] = pd.to_numeric(u["user_id"], errors="coerce").astype("Int64")
    u["signup_date"] = pd.to_datetime(u["signup_date"], errors="coerce").dt.date

    # Normalize plan
    u["plan"] = u["plan"].astype(str).str.lower().str.strip()

    # Ensure is_paid matches plan if inconsistent
    if "is_paid" in u.columns:
        u["is_paid"] = pd.to_numeric(u["is_paid"], errors="coerce").fillna(0).astype(int)
    else:
        u["is_paid"] = (u["plan"] == "paid").astype(int)

    # Optional synthetic column
    if "engagement_score" in u.columns:
        u["engagement_score"] = pd.to_numeric(u["engagement_score"], errors="coerce")

    # Drop rows with missing critical identity
    u = u.dropna(subset=["user_id", "signup_date", "plan"])

    # De-dup
    u = u.drop_duplicates(subset=["user_id"]).reset_index(drop=True)
    return u


def _clean_events(events: pd.DataFrame) -> pd.DataFrame:
    e = events.copy()

    e["event_id"] = pd.to_numeric(e["event_id"], errors="coerce").astype("Int64")
    e["user_id"] = pd.to_numeric(e["user_id"], errors="coerce").astype("Int64")
    e["event_time"] = pd.to_datetime(e["event_time"], errors="coerce")

    e["event_type"] = e["event_type"].astype(str).str.lower().str.strip()

    # Ensure numeric columns
    e["watch_minutes"] = pd.to_numeric(e.get("watch_minutes", 0), errors="coerce").fillna(0.0)
    e["quiz_score"] = pd.to_numeric(e.get("quiz_score", np.nan), errors="coerce")
    e["amount"] = pd.to_numeric(e.get("amount", np.nan), errors="coerce")

    e["event_date"] = e["event_time"].dt.date

    # Drop rows with missing critical fields
    e = e.dropna(subset=["event_id", "user_id", "event_time", "event_type", "event_date"])

    # De-dup
    e = e.drop_duplicates(subset=["event_id"]).reset_index(drop=True)
    return e


def _build_user_day_grid(users: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """
    Create a full grid: user_id x date_range
    Fill missing activity with zeros.
    """
    if events.empty:
        # fallback to a minimal single-day range using signup min
        min_day = pd.to_datetime(users["signup_date"].min())
        max_day = min_day
    else:
        min_day = pd.to_datetime(events["event_date"].min())
        max_day = pd.to_datetime(events["event_date"].max())

    date_range = pd.date_range(min_day, max_day, freq="D")

    # Cartesian product
    grid = (
        pd.MultiIndex.from_product([users["user_id"].astype(int).tolist(), date_range], names=["user_id", "as_of_date"])
        .to_frame(index=False)
    )
    grid["as_of_date"] = pd.to_datetime(grid["as_of_date"]).dt.date
    return grid


def _daily_aggregates(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(
            columns=[
                "user_id",
                "as_of_date",
                "logins_count",
                "enroll_count",
                "watch_minutes_sum",
                "quiz_attempts_count",
                "quiz_avg_score",
                "payment_success_count",
                "payment_failed_count",
                "support_ticket_count",
                "total_events",
            ]
        )

    e = events.copy()
    e["user_id"] = e["user_id"].astype(int)
    e["as_of_date"] = pd.to_datetime(e["event_date"]).dt.date

    def _count_type(df: pd.DataFrame, etype: str) -> int:
        return int((df["event_type"] == etype).sum())

    grouped = []
    for (uid, day), df in e.groupby(["user_id", "as_of_date"]):
        grouped.append(
            {
                "user_id": uid,
                "as_of_date": day,
                "logins_count": _count_type(df, "login"),
                "enroll_count": _count_type(df, "course_enroll"),
                "watch_minutes_sum": float(df.loc[df["event_type"] == "video_watch", "watch_minutes"].sum()),
                "quiz_attempts_count": _count_type(df, "quiz_attempt"),
                "quiz_avg_score": float(df.loc[df["event_type"] == "quiz_attempt", "quiz_score"].mean())
                if (df["event_type"] == "quiz_attempt").any()
                else np.nan,
                "payment_success_count": _count_type(df, "payment_success"),
                "payment_failed_count": _count_type(df, "payment_failed"),
                "support_ticket_count": _count_type(df, "support_ticket"),
                "total_events": int(len(df)),
            }
        )

    out = pd.DataFrame(grouped)
    return out


def build_user_daily(users: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    grid = _build_user_day_grid(users, events)
    daily = _daily_aggregates(events)

    merged = grid.merge(daily, on=["user_id", "as_of_date"], how="left")

    # Fill missing counts with 0
    count_cols = [
        "logins_count",
        "enroll_count",
        "watch_minutes_sum",
        "quiz_attempts_count",
        "payment_success_count",
        "payment_failed_count",
        "support_ticket_count",
        "total_events",
    ]
    for c in count_cols:
        merged[c] = merged[c].fillna(0)

    # quiz_avg_score can stay NaN when no quiz attempts
    merged["quiz_avg_score"] = pd.to_numeric(merged["quiz_avg_score"], errors="coerce")

    # Add user attributes
    u_small = users[
        ["user_id", "signup_date", "plan", "is_paid", "country", "marketing_source"]
        + (["engagement_score"] if "engagement_score" in users.columns else [])
    ].copy()
    u_small["user_id"] = u_small["user_id"].astype(int)

    merged = merged.merge(u_small, on="user_id", how="left")

    # Derived helpful columns
    merged["signup_date"] = pd.to_datetime(merged["signup_date"])
    merged["as_of_date_dt"] = pd.to_datetime(merged["as_of_date"])
    merged["days_since_signup"] = (merged["as_of_date_dt"] - merged["signup_date"]).dt.days
    merged["days_since_signup"] = merged["days_since_signup"].clip(lower=0)

    merged["is_active_day"] = (merged["total_events"] > 0).astype(int)

    # Clean helper date columns
    merged["signup_date"] = merged["signup_date"].dt.date
    merged = merged.drop(columns=["as_of_date_dt"])

    # Order columns nicely
    ordered = [
        "user_id",
        "as_of_date",
        "signup_date",
        "days_since_signup",
        "plan",
        "is_paid",
        "country",
        "marketing_source",
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
    if "engagement_score" in merged.columns:
        ordered.insert(8, "engagement_score")

    # Keep any extra columns at the end
    final_cols = ordered + [c for c in merged.columns if c not in ordered]
    merged = merged[final_cols]

    return merged


def write_processed(users: pd.DataFrame, events: pd.DataFrame, user_daily: pd.DataFrame, processed_dir: str):
    out_dir = ensure_dir(processed_dir)

    users.to_csv(Path(out_dir) / "users_clean.csv", index=False)
    events.to_csv(Path(out_dir) / "events_clean.csv", index=False)
    user_daily.to_csv(Path(out_dir) / "user_daily.csv", index=False)


def parse_args() -> PrepareSettings:
    cfg = load_config()
    parser = argparse.ArgumentParser(description="Prepare processed churn datasets")
    parser.add_argument("--raw-dir", type=str, default=cfg["paths"]["raw"])
    parser.add_argument("--processed-dir", type=str, default=cfg["paths"]["processed"])
    args = parser.parse_args()
    return PrepareSettings(raw_dir=args.raw_dir, processed_dir=args.processed_dir)


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()

    logger.info("Reading raw data...")
    users, events = _read_raw(settings.raw_dir)

    logger.info("Cleaning users...")
    users_clean = _clean_users(users)

    logger.info("Cleaning events...")
    events_clean = _clean_events(events)

    # Filter events to known users only
    known_users = set(users_clean["user_id"].astype(int).tolist())
    events_clean = events_clean[events_clean["user_id"].astype(int).isin(known_users)].reset_index(drop=True)

    logger.info("Building user_daily activity table...")
    user_daily = build_user_daily(users_clean, events_clean)

    logger.info("Writing processed outputs...")
    write_processed(users_clean, events_clean, user_daily, settings.processed_dir)

    logger.info("Done ✅")
    logger.info("users_clean: %s", Path(settings.processed_dir) / "users_clean.csv")
    logger.info("events_clean: %s", Path(settings.processed_dir) / "events_clean.csv")
    logger.info("user_daily: %s", Path(settings.processed_dir) / "user_daily.csv")
    logger.info("Rows: users=%d events=%d user_daily=%d", len(users_clean), len(events_clean), len(user_daily))


if __name__ == "__main__":
    main()
