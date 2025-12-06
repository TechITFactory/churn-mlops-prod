import pandas as pd

from churn_mlops.data.validate import validate_events, validate_users


def test_validate_users_ok():
    users = pd.DataFrame(
        {
            "user_id": [1, 2],
            "signup_date": ["2025-01-01", "2025-01-02"],
            "plan": ["free", "paid"],
            "is_paid": [0, 1],
            "country": ["IN", "US"],
            "marketing_source": ["youtube", "organic"],
        }
    )
    res = validate_users(users)
    assert res.ok is True


def test_validate_events_ok():
    users = pd.DataFrame(
        {
            "user_id": [1],
            "signup_date": ["2025-01-01"],
            "plan": ["paid"],
            "is_paid": [1],
            "country": ["IN"],
            "marketing_source": ["youtube"],
        }
    )

    events = pd.DataFrame(
        {
            "event_id": [10, 11],
            "user_id": [1, 1],
            "event_time": ["2025-01-05T10:00:00", "2025-01-06T10:00:00"],
            "event_type": ["login", "video_watch"],
            "course_id": ["c1", "c1"],
            "watch_minutes": [0, 12],
            "quiz_score": [None, None],
            "amount": [None, None],
        }
    )

    res = validate_events(events, users)
    assert res.ok is True
