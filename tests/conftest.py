"""Shared factories so each test states only what makes it interesting."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.models import Transaction, UserHistory

BASE_TIME = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
NYC = (40.7128, -74.0060)
LONDON = (51.5074, -0.1278)


def make_txn(**overrides) -> Transaction:
    """A boring, low-risk transaction; override fields to introduce risk."""
    fields = dict(
        transaction_id="TXN-TEST",
        user_id="U-TEST",
        timestamp=BASE_TIME,
        amount=40.0,
        currency="USD",
        device_id="DEV-HOME",
        ip_address="203.0.113.10",
        ip_risk_score=5.0,
        country="US",
        latitude=NYC[0],
        longitude=NYC[1],
        merchant_category="groceries",
        account_age_days=400,
        failed_login_attempts=0,
    )
    fields.update(overrides)
    return Transaction(**fields)


def make_history(n: int = 6, **overrides) -> UserHistory:
    """A user with n ordinary trusted transactions ending a day before BASE_TIME."""
    history = UserHistory()
    for i in range(n):
        past = make_txn(
            timestamp=BASE_TIME - timedelta(days=n - i + 1),
            amount=40.0 + i,  # median around $42.5
        )
        history.record_attempt(past)
        history.record_trusted(past)
    for key, value in overrides.items():
        setattr(history, key, value)
    return history


@pytest.fixture
def txn() -> Transaction:
    return make_txn()


@pytest.fixture
def history() -> UserHistory:
    return make_history()
