"""Transparent risk controls.

Each control is a small pure function: ``(transaction, history, config) ->
RiskSignal | None``. A control returns ``None`` when it does not trigger.

Weight rationale (illustrative, NOT statistically calibrated)
-------------------------------------------------------------
Points are ordered by how strongly a signal suggests account compromise or
misuse, and by how hard it is for a legitimate customer to trigger by accident:

* Impossible travel (30): physically implausible; almost never innocent, so it
  is the heaviest single control and alone reaches the REVIEW band.
* Very high-risk IP (30 / 20 / 10): a known-bad network is a strong signal, but
  reputation feeds are noisy, so lower tiers are weighted down.
* New country (20): meaningful, but customers travel, so it should not block
  on its own.
* Unusual amount (12 / 20 / 30): scaled by how far above the user's median the
  amount is; extreme multiples matter most.
* Velocity (15 / 25): bursts of attempts are typical of card testing and
  automation.
* New device (15): common for legitimate reasons (new phone), so kept modest.
* Failed logins (10 / 15), new account (5 / 10), high-risk merchant category
  (8): weak context signals that mostly matter in combination.

Design principle: no single weak signal can BLOCK; blocking needs several
independent signals to agree. Thresholds live in :class:`RuleConfig`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median

from src.models import RiskSignal, Transaction, UserHistory
from src.utils import haversine_km


@dataclass(frozen=True)
class RuleConfig:
    """All weights and thresholds in one auditable place."""

    # Decision thresholds (score is 0-100)
    review_threshold: int = 30
    block_threshold: int = 60

    # Cold start: baseline-based controls need this many trusted past events
    min_history_for_baseline: int = 3

    # Velocity: attempts within the window, including the current one
    velocity_window_minutes: int = 10
    velocity_medium_count: int = 4
    velocity_high_count: int = 6
    velocity_medium_points: int = 15
    velocity_high_points: int = 25

    # Unusual amount: multiple of the user's historical median
    amount_tiers: tuple[tuple[float, int], ...] = (
        (12.0, 30),
        (8.0, 20),
        (4.0, 12),
    )

    new_device_points: int = 15
    new_country_points: int = 20

    # IP reputation (0-100, higher = riskier): (min score, points)
    ip_tiers: tuple[tuple[float, int], ...] = (
        (85.0, 30),
        (70.0, 20),
        (50.0, 10),
    )

    # Travel: implied speed thresholds in km/h
    min_travel_km: float = 300.0
    impossible_speed_kmh: float = 900.0  # faster than a commercial flight
    implausible_speed_kmh: float = 500.0
    impossible_travel_points: int = 30
    implausible_travel_points: int = 15

    # Supporting context controls
    new_account_days: int = 7
    young_account_days: int = 30
    new_account_points: int = 10
    young_account_points: int = 5
    failed_login_medium: int = 3
    failed_login_high: int = 5
    failed_login_medium_points: int = 10
    failed_login_high_points: int = 15
    high_risk_merchants: frozenset[str] = field(
        default_factory=lambda: frozenset({"crypto_exchange", "gift_cards", "wire_transfer"})
    )
    high_risk_merchant_points: int = 8


DEFAULT_CONFIG = RuleConfig()

Rule = Callable[[Transaction, UserHistory, RuleConfig], RiskSignal | None]


def transaction_velocity(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Too many attempts by one user in a short window."""
    window_start = txn.timestamp - timedelta(minutes=cfg.velocity_window_minutes)
    count = 1 + sum(1 for t in history.attempts if t >= window_start)
    if count >= cfg.velocity_high_count:
        points = cfg.velocity_high_points
    elif count >= cfg.velocity_medium_count:
        points = cfg.velocity_medium_points
    else:
        return None
    return RiskSignal(
        "Transaction velocity", points,
        f"{count} attempts within {cfg.velocity_window_minutes} minutes",
    )


def unusual_amount(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Amount far above this user's own historical median."""
    if history.trusted_count < cfg.min_history_for_baseline:
        return None
    baseline = median(history.amounts)
    if baseline <= 0:
        return None
    ratio = txn.amount / baseline
    for min_ratio, points in cfg.amount_tiers:
        if ratio >= min_ratio:
            return RiskSignal(
                "Unusual transaction amount", points,
                f"${txn.amount:,.2f} is {ratio:.1f}x the user's median of ${baseline:,.2f}",
            )
    return None


def new_device(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Device never seen on a previously trusted transaction."""
    if history.trusted_count < cfg.min_history_for_baseline:
        return None
    if txn.device_id in history.devices:
        return None
    return RiskSignal("New device", cfg.new_device_points, f"device {txn.device_id} not seen before for this user")


def new_country(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Country not previously associated with this user."""
    if history.trusted_count < cfg.min_history_for_baseline:
        return None
    if txn.country in history.countries:
        return None
    known = ", ".join(sorted(history.countries))
    return RiskSignal(
        "New country", cfg.new_country_points, f"{txn.country} not in previously seen countries ({known})"
    )


def ip_reputation(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Synthetic IP reputation score; riskier IPs contribute more points."""
    for min_score, points in cfg.ip_tiers:
        if txn.ip_risk_score >= min_score:
            return RiskSignal(
                "High-risk IP", points,
                f"IP {txn.ip_address} reputation risk {txn.ip_risk_score:.0f}/100",
            )
    return None


def implausible_travel(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Distant location too soon after the last trusted transaction."""
    if history.last_trusted is None:
        return None
    last_ts, last_lat, last_lon = history.last_trusted
    distance = haversine_km(last_lat, last_lon, txn.latitude, txn.longitude)
    if distance < cfg.min_travel_km:
        return None
    # Floor the elapsed time at one minute to avoid division by zero.
    hours = max((txn.timestamp - last_ts).total_seconds() / 3600.0, 1.0 / 60.0)
    speed = distance / hours
    if speed >= cfg.impossible_speed_kmh:
        label, points = "Impossible travel", cfg.impossible_travel_points
    elif speed >= cfg.implausible_speed_kmh:
        label, points = "Implausible travel", cfg.implausible_travel_points
    else:
        return None
    return RiskSignal(label, points, f"{distance:,.0f} km in {hours:.1f} h (~{speed:,.0f} km/h)")


def account_age(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Very new accounts carry more risk."""
    if txn.account_age_days < cfg.new_account_days:
        points = cfg.new_account_points
    elif txn.account_age_days < cfg.young_account_days:
        points = cfg.young_account_points
    else:
        return None
    return RiskSignal("New account", points, f"account is {txn.account_age_days} days old")


def failed_logins(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Repeated failed logins shortly before the transaction."""
    n = txn.failed_login_attempts
    if n >= cfg.failed_login_high:
        points = cfg.failed_login_high_points
    elif n >= cfg.failed_login_medium:
        points = cfg.failed_login_medium_points
    else:
        return None
    return RiskSignal("Failed logins", points, f"{n} failed login attempts before this transaction")


def merchant_category_risk(txn: Transaction, history: UserHistory, cfg: RuleConfig) -> RiskSignal | None:
    """Merchant categories commonly associated with cash-out or laundering."""
    if txn.merchant_category not in cfg.high_risk_merchants:
        return None
    return RiskSignal(
        "High-risk merchant category", cfg.high_risk_merchant_points, f"category '{txn.merchant_category}'"
    )


ALL_RULES: tuple[Rule, ...] = (
    transaction_velocity,
    unusual_amount,
    new_device,
    new_country,
    ip_reputation,
    implausible_travel,
    account_age,
    failed_logins,
    merchant_category_risk,
)
