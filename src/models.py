"""Core data structures shared by the rules, scoring engine, and reports."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd


class Decision(str, Enum):
    """Operational outcome for a scored transaction."""

    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class Transaction:
    """A single (synthetic) transaction event."""

    transaction_id: str
    user_id: str
    timestamp: datetime
    amount: float
    currency: str
    device_id: str
    ip_address: str
    ip_risk_score: float
    country: str
    latitude: float
    longitude: float
    merchant_category: str
    account_age_days: int
    failed_login_attempts: int

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> Transaction:
        """Build a Transaction from a DataFrame row or dict."""
        return cls(
            transaction_id=str(row["transaction_id"]),
            user_id=str(row["user_id"]),
            timestamp=pd.Timestamp(row["timestamp"]).to_pydatetime(),
            amount=float(row["amount"]),
            currency=str(row["currency"]),
            device_id=str(row["device_id"]),
            ip_address=str(row["ip_address"]),
            ip_risk_score=float(row["ip_risk_score"]),
            country=str(row["country"]),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            merchant_category=str(row["merchant_category"]),
            account_age_days=int(row["account_age_days"]),
            failed_login_attempts=int(row["failed_login_attempts"]),
        )


@dataclass(frozen=True)
class RiskSignal:
    """One triggered control and the points it contributes."""

    control: str
    points: int
    detail: str


@dataclass(frozen=True)
class RiskAssessment:
    """The full, explainable result for one transaction."""

    transaction_id: str
    score: int
    decision: Decision
    signals: tuple[RiskSignal, ...]
    explanation: str

    @property
    def triggered_controls(self) -> list[str]:
        return [s.control for s in self.signals]


@dataclass
class UserHistory:
    """Behavioral baseline for one user, built only from *past* events.

    ``attempts`` records every attempt (including blocked ones) because
    velocity should count attempts. The baseline fields (devices, countries,
    amounts, last_trusted) are only updated by non-blocked transactions so a
    blocked attacker cannot poison a user's normal profile.
    """

    devices: set[str] = field(default_factory=set)
    countries: set[str] = field(default_factory=set)
    amounts: list[float] = field(default_factory=list)
    attempts: list[datetime] = field(default_factory=list)
    last_trusted: tuple[datetime, float, float] | None = None

    @property
    def trusted_count(self) -> int:
        return len(self.amounts)

    def record_attempt(self, txn: Transaction) -> None:
        self.attempts.append(txn.timestamp)

    def record_trusted(self, txn: Transaction) -> None:
        self.devices.add(txn.device_id)
        self.countries.add(txn.country)
        self.amounts.append(txn.amount)
        self.last_trusted = (txn.timestamp, txn.latitude, txn.longitude)
