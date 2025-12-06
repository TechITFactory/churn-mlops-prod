import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from churn_mlops.common.config import load_config
from churn_mlops.common.logging import setup_logging
from churn_mlops.common.utils import ensure_dir


EVENT_TYPES = [
    "login",
    "course_enroll",
    "video_watch",
    "quiz_attempt",
    "payment_success",
    "payment_failed",
    "support_ticket",
]

COURSE_POOL = [
    "k8s-mastery",
    "devops-warrior",
    "mlops-foundation",
    "argo-cd",
    "terraform",
    "linux-pro",
    "observability",
]


@dataclass
class GeneratorSettings:
    n_users: int
    days: int
    start_date: str
    seed: int
    paid_ratio: float
    churn_base_rate: float
    output_dir: str


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _random_choice(rng: np.random.Generator, items: List[str], size: int) -> List[str]:
    idx = rng.integers(0, len(items), size=size)
    return [items[i] for i in idx]


def _build_users(rng: np.random.Generator, settings: GeneratorSettings) -> pd.DataFrame:
    start_dt = _parse_date(settings.start_date)
    signup_spread_days = max(30, settings.days // 3)

    user_ids = np.arange(1, settings.n_users + 1)

    signup_offsets = rng.integers(0, signup_spread_days, size=settings.n_users)
    signup_dates = [start_dt - timedelta(days=int(x)) for x in signup_offsets]

    is_paid = rng.random(settings.n_users) < settings.paid_ratio
    plan = np.where(is_paid, "paid", "free")

    countries = _random_choice(rng, ["IN", "US", "UK", "CA", "AU", "SG"], settings.n_users)
    sources = _random_choice(rng, ["organic", "referral", "ads", "youtube", "community"], settings.n_users)

    # A latent engagement score: higher means more active / less likely to churn
    engagement = rng.beta(a=2.0, b=2.5, size=settings.n_users)

    users = pd.DataFrame(
        {
            "user_id": user_ids,
            "signup_date": [d.date().isoformat() for d in signup_dates],
            "plan": plan,
            "is_paid": is_paid.astype(int),
            "country": countries,
            "marketing_source": sources,
            "engagement_score": engagement,
        }
    )
    return users


def _assign_churn_dates(
    rng: np.random.Generator,
    users: pd.DataFrame,
    settings: GeneratorSettings,
) -> Dict[int, Optional[datetime]]:
    """
    Determine a churn date per user:
    - Higher engagement reduces churn chance.
    - Paid users churn a bit less by default.
    """
    start_dt = _parse_date(settings.start_date)
    end_dt = start_dt + timedelta(days=settings.days - 1)

    churn_dates: Dict[int, Optional[datetime]] = {}

    for row in users.itertuples(index=False):
        base = settings.churn_base_rate

        # Reduce churn for paid users a bit
        if row.is_paid == 1:
            base *= 0.75

        # Engagement effect (strong)
        # engagement_score ~ 0..1
        # low engagement -> higher churn
        engagement_factor = (1.0 - float(row.engagement_score)) ** 1.6
        churn_prob = min(0.95, base * (0.4 + 1.4 * engagement_factor))

        if rng.random() < churn_prob:
            # churn occurs somewhere in the generated range
            churn_offset = int(rng.integers(low=settings.days // 4, high=settings.days))
            churn_dt = start_dt + timedelta(days=churn_offset)
            churn_dt = min(churn_dt, end_dt)
            churn_dates[int(row.user_id)] = churn_dt
        else:
            churn_dates[int(row.user_id)] = None

    return churn_dates


def _events_for_user_day(
    rng: np.random.Generator,
    user_id: int,
    is_paid: int,
    engagement: float,
    day_dt: datetime,
) -> List[Dict]:
    """
    Generate a small, realistic set of daily events based on engagement.
    """
    events: List[Dict] = []

    # Activity probability by engagement
    active_today = rng.random() < (0.15 + 0.8 * engagement)

    if not active_today:
        return events

    # 1..3 sessions per active day
    sessions = int(rng.integers(1, 4))
    for _ in range(sessions):
        # login
        t = day_dt + timedelta(minutes=int(rng.integers(0, 1440)))
        events.append(
            {
                "user_id": user_id,
                "event_time": t.isoformat(),
                "event_type": "login",
                "course_id": None,
                "watch_minutes": 0.0,
                "quiz_score": np.nan,
                "amount": np.nan,
            }
        )

        # likely a learning activity
        course_id = rng.choice(COURSE_POOL)

        # video watch
        if rng.random() < (0.5 + 0.4 * engagement):
            t2 = day_dt + timedelta(minutes=int(rng.integers(0, 1440)))
            watch = float(np.clip(rng.normal(20 + 40 * engagement, 10), 2, 180))
            events.append(
                {
                    "user_id": user_id,
                    "event_time": t2.isoformat(),
                    "event_type": "video_watch",
                    "course_id": course_id,
                    "watch_minutes": watch,
                    "quiz_score": np.nan,
                    "amount": np.nan,
                }
            )

        # quiz attempt
        if rng.random() < (0.25 + 0.35 * engagement):
            t3 = day_dt + timedelta(minutes=int(rng.integers(0, 1440)))
            score = float(np.clip(rng.normal(50 + 40 * engagement, 15), 0, 100))
            events.append(
                {
                    "user_id": user_id,
                    "event_time": t3.isoformat(),
                    "event_type": "quiz_attempt",
                    "course_id": course_id,
                    "watch_minutes": 0.0,
                    "quiz_score": score,
                    "amount": np.nan,
                }
            )

        # occasional course enroll
        if rng.random() < 0.05:
            t4 = day_dt + timedelta(minutes=int(rng.integers(0, 1440)))
            events.append(
                {
                    "user_id": user_id,
                    "event_time": t4.isoformat(),
                    "event_type": "course_enroll",
                    "course_id": course_id,
                    "watch_minutes": 0.0,
                    "quiz_score": np.nan,
                    "amount": np.nan,
                }
            )

    # payments (monthly-ish pattern for paid users)
    if is_paid == 1 and day_dt.day in {1, 2, 3}:
        # success most of the time
        pay_success = rng.random() < 0.93
        et = "payment_success" if pay_success else "payment_failed"
        amt = float(np.clip(rng.normal(499, 80), 199, 999))
        t5 = day_dt + timedelta(minutes=int(rng.integers(0, 1440)))
        events.append(
            {
                "user_id": user_id,
                "event_time": t5.isoformat(),
                "event_type": et,
                "course_id": None,
                "watch_minutes": 0.0,
                "quiz_score": np.nan,
                "amount": amt,
            }
        )

    # support tickets (rare)
    if rng.random() < 0.005:
        t6 = day_dt + timedelta(minutes=int(rng.integers(0, 1440)))
        events.append(
            {
                "user_id": user_id,
                "event_time": t6.isoformat(),
                "event_type": "support_ticket",
                "course_id": None,
                "watch_minutes": 0.0,
                "quiz_score": np.nan,
                "amount": np.nan,
            }
        )

    return events


def build_events(
    rng: np.random.Generator,
    users: pd.DataFrame,
    churn_dates: Dict[int, Optional[datetime]],
    settings: GeneratorSettings,
) -> pd.DataFrame:
    start_dt = _parse_date(settings.start_date)

    rows: List[Dict] = []
    for row in users.itertuples(index=False):
        uid = int(row.user_id)
        churn_dt = churn_dates[uid]
        engagement = float(row.engagement_score)
        is_paid = int(row.is_paid)

        for d in range(settings.days):
            day_dt = start_dt + timedelta(days=d)

            # if churned, no events after churn date
            if churn_dt is not None and day_dt.date() > churn_dt.date():
                continue

            rows.extend(_events_for_user_day(rng, uid, is_paid, engagement, day_dt))

    events = pd.DataFrame(rows)
    if events.empty:
        return events

    # Add stable event_id
    events = events.sort_values(["user_id", "event_time"]).reset_index(drop=True)
    events.insert(0, "event_id", np.arange(1, len(events) + 1))

    return events


def write_outputs(users: pd.DataFrame, events: pd.DataFrame, settings: GeneratorSettings) -> Tuple[Path, Path]:
    out_dir = ensure_dir(settings.output_dir)

    users_path = out_dir / "users.csv"
    events_path = out_dir / "events.csv"

    users.to_csv(users_path, index=False)
    events.to_csv(events_path, index=False)

    return users_path, events_path


def parse_args() -> GeneratorSettings:
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Generate synthetic e-learning churn dataset")
    parser.add_argument("--n-users", type=int, default=2000)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--start-date", type=str, default="2025-01-01")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--paid-ratio", type=float, default=0.35)
    parser.add_argument("--churn-base-rate", type=float, default=0.35)
    parser.add_argument("--output-dir", type=str, default=cfg["paths"]["raw"])

    args = parser.parse_args()

    return GeneratorSettings(
        n_users=args.n_users,
        days=args.days,
        start_date=args.start_date,
        seed=args.seed,
        paid_ratio=args.paid_ratio,
        churn_base_rate=args.churn_base_rate,
        output_dir=args.output_dir,
    )


def main():
    cfg = load_config()
    logger = setup_logging(cfg)

    settings = parse_args()
    rng = np.random.default_rng(settings.seed)

    logger.info("Generating synthetic users...")
    users = _build_users(rng, settings)

    logger.info("Assigning churn dates...")
    churn_dates = _assign_churn_dates(rng, users, settings)

    logger.info("Generating synthetic events...")
    events = build_events(rng, users, churn_dates, settings)

    users_path, events_path = write_outputs(users, events, settings)

    logger.info("Done.")
    logger.info("Users: %s rows -> %s", len(users), users_path)
    logger.info("Events: %s rows -> %s", len(events), events_path)


if __name__ == "__main__":
    main()
