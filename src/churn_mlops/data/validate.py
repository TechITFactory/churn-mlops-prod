import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


EVENT_TYPES: Set[str] = {
    "login",
    "course_enroll",
    "video_watch",
    "quiz_attempt",
    "payment_success",
    "payment_failed",
    "support_ticket",
}


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str]


def _require_columns(df: pd.DataFrame, required: List[str], name: str) -> List[str]:
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [f"{name}: missing columns: {missing}"]
    return []


def _as_date(series: pd.Series, col: str, name: str) -> Tuple[Optional[pd.Series], List[str]]:
    try:
        s = pd.to_datetime(series, errors="raise").dt.date
        return s, []
    except Exception:
        return None, [f"{name}: invalid date values in '{col}'"]


def _as_datetime(series: pd.Series, col: str, name: str) -> Tuple[Optional[pd.Series], List[str]]:
    try:
        s = pd.to_datetime(series, errors="raise")
        return s, []
    except Exception:
        return None, [f"{name}: invalid datetime values in '{col}'"]


def validate_users(users: pd.DataFrame) -> ValidationResult:
    errors: List[str] = []
    name = "users"

    required = ["user_id", "signup_date", "plan", "is_paid", "country", "marketing_source"]
    errors += _require_columns(users, required, name)
    if errors:
        return ValidationResult(False, errors)

    # user_id unique + integer-like
    if users["user_id"].isna().any():
        errors.append("users: 'user_id' has nulls")

    if users["user_id"].duplicated().any():
        errors.append("users: duplicate 'user_id' found")

    # signup_date parseable
    _, e = _as_date(users["signup_date"], "signup_date", name)
    errors += e

    # plan values
    bad_plan = users.loc[~users["plan"].isin(["free", "paid"]), "plan"].unique().tolist()
    if bad_plan:
        errors.append(f"users: invalid plan values: {bad_plan}")

    # is_paid must be 0/1
    bad_paid = users.loc[~users["is_paid"].isin([0, 1]), "is_paid"].unique().tolist()
    if bad_paid:
        errors.append(f"users: invalid is_paid values: {bad_paid}")

    # Optional synthetic-only column checks (safe if missing)
    if "engagement_score" in users.columns:
        es = users["engagement_score"]
        if es.isna().any():
            errors.append("users: 'engagement_score' has nulls")
        if ((es < 0) | (es > 1)).any():
            errors.append("users: 'engagement_score' must be between 0 and 1")

    return ValidationResult(ok=len(errors) == 0, errors=errors)


def validate_events(events: pd.DataFrame, users: pd.DataFrame) -> ValidationResult:
    errors: List[str] = []
    name = "events"

    required = [
        "event_id",
        "user_id",
        "event_time",
        "event_type",
        "course_id",
        "watch_minutes",
        "quiz_score",
        "amount",
    ]
    errors += _require_columns(events, required, name)
    if errors:
        return ValidationResult(False, errors)

    # event_id unique
    if events["event_id"].isna().any():
        errors.append("events: 'event_id' has nulls")

    if events["event_id"].duplicated().any():
        errors.append("events: duplicate 'event_id' found")

    # user_id must exist in users
    user_ids = set(users["user_id"].dropna().astype(int).tolist())
    bad_users = sorted(set(events["user_id"].dropna().astype(int).tolist()) - user_ids)
    if bad_users:
        errors.append(f"events: unknown user_id(s) not in users: {bad_users[:20]}")

    # event_time parseable
    _, e = _as_datetime(events["event_time"], "event_time", name)
    errors += e

    # event_type allowed
    bad_types = events.loc[~events["event_type"].isin(EVENT_TYPES), "event_type"].unique().tolist()
    if bad_types:
        errors.append(f"events: invalid event_type values: {bad_types}")

    # watch_minutes constraint
    wm = pd.to_numeric(events["watch_minutes"], errors="coerce").fillna(0)
    if (wm < 0).any():
        errors.append("events: watch_minutes must be >= 0")

    # quiz_score constraint (if present)
    qs = pd.to_numeric(events["quiz_score"], errors="coerce")
    bad_qs = qs.dropna().loc[(qs < 0) | (qs > 100)]
    if not bad_qs.empty:
        errors.append("events: quiz_score must be between 0 and 100")

    # amount logic:
    # - For payment_success/payment_failed: amount must be > 0
    # - For other events: amount should be null or 0 (we won't fail hard, just warn-level error)
    amt = pd.to_numeric(events["amount"], errors="coerce")

    pay_mask = events["event_type"].isin(["payment_success", "payment_failed"])
    nonpay_mask = ~pay_mask

    if pay_mask.any():
        bad_pay_amt = amt.loc[pay_mask].dropna().loc[amt.loc[pay_mask] <= 0]
        if not bad_pay_amt.empty:
            errors.append("events: payment events must have amount > 0")

    # Soft constraint: non-payment amount should be empty
    # If too many violations, raise as error
    nonpay_amt_present = amt.loc[nonpay_mask].dropna()
    if len(nonpay_amt_present) > 0:
        ratio = len(nonpay_amt_present) / max(1, len(events))
        if ratio > 0.02:
            errors.append("events: too many non-payment events with amount value (possible data contamination)")

    return ValidationResult(ok=len(errors) == 0, errors=errors)


def validate_all(raw_dir: str) -> ValidationResult:
    raw_path = Path(raw_dir)
    users_path = raw_path / "users.csv"
    events_path = raw_path / "events.csv"

    errors: List[str] = []
    if not users_path.exists():
        errors.append(f"raw: missing {users_path}")
    if not events_path.exists():
        errors.append(f"raw: missing {events_path}")
    if errors:
        return ValidationResult(False, errors)

    users = pd.read_csv(users_path)
    events = pd.read_csv(events_path)

    ru = validate_users(users)
    re = validate_events(events, users)

    all_errors = ru.errors + re.errors
    return ValidationResult(ok=len(all_errors) == 0, errors=all_errors)


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    raw_dir = cfg["paths"]["raw"]

    result = validate_all(raw_dir)

    if result.ok:
        logger.info("RAW DATA VALIDATION PASSED ✅")
        sys.exit(0)

    logger.error("RAW DATA VALIDATION FAILED ❌")
    for err in result.errors:
        logger.error(" - %s", err)

    sys.exit(1)


if __name__ == "__main__":
    main()
