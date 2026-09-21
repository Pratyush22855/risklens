"""Unit tests for each individual control."""
from __future__ import annotations

from datetime import timedelta

from src.models import UserHistory
from src.rules import (
    DEFAULT_CONFIG,
    account_age,
    failed_logins,
    implausible_travel,
    ip_reputation,
    merchant_category_risk,
    new_country,
    new_device,
    transaction_velocity,
    unusual_amount,
)
from tests.conftest import BASE_TIME, LONDON, make_history, make_txn

CFG = DEFAULT_CONFIG


def test_baseline_transaction_triggers_nothing(txn, history):
    for rule in (new_device, new_country, unusual_amount, ip_reputation,
                 implausible_travel, transaction_velocity, account_age,
                 failed_logins, merchant_category_risk):
        assert rule(txn, history, CFG) is None, rule.__name__


def test_new_device_triggers_for_unseen_device(history):
    signal = new_device(make_txn(device_id="DEV-NEW"), history, CFG)
    assert signal is not None
    assert signal.points == CFG.new_device_points


def test_new_country_triggers_for_unseen_country(history):
    signal = new_country(make_txn(country="GB"), history, CFG)
    assert signal is not None
    assert signal.points == CFG.new_country_points


def test_baseline_controls_skip_users_without_enough_history():
    thin = make_history(n=1)
    assert new_device(make_txn(device_id="DEV-NEW"), thin, CFG) is None
    assert new_country(make_txn(country="GB"), thin, CFG) is None
    assert unusual_amount(make_txn(amount=9999), thin, CFG) is None


def test_unusual_amount_scales_with_multiple_of_median(history):
    assert unusual_amount(make_txn(amount=100), history, CFG) is None  # ~2.4x
    medium = unusual_amount(make_txn(amount=200), history, CFG)  # ~4.7x
    high = unusual_amount(make_txn(amount=400), history, CFG)  # ~9.4x
    extreme = unusual_amount(make_txn(amount=800), history, CFG)  # ~18.8x
    assert (medium.points, high.points, extreme.points) == (12, 20, 30)


def test_ip_reputation_higher_risk_means_more_points(history):
    points = [
        ip_reputation(make_txn(ip_risk_score=s), history, CFG)
        for s in (20, 55, 75, 92)
    ]
    assert points[0] is None
    assert [p.points for p in points[1:]] == [10, 20, 30]


def test_velocity_counts_recent_attempts_including_current():
    history = UserHistory()
    for seconds in (30, 60, 90):  # three prior attempts in the last 2 minutes
        history.attempts.append(BASE_TIME - timedelta(seconds=seconds))
    signal = transaction_velocity(make_txn(), history, CFG)  # 4th attempt
    assert signal is not None and signal.points == CFG.velocity_medium_points

    for seconds in (120, 150):
        history.attempts.append(BASE_TIME - timedelta(seconds=seconds))
    high = transaction_velocity(make_txn(), history, CFG)  # 6th attempt
    assert high is not None and high.points == CFG.velocity_high_points


def test_velocity_ignores_attempts_outside_window():
    history = UserHistory()
    for minutes in (30, 40, 50, 60, 70):
        history.attempts.append(BASE_TIME - timedelta(minutes=minutes))
    assert transaction_velocity(make_txn(), history, CFG) is None


def test_impossible_travel_triggers_for_far_location_in_short_time():
    history = make_history()
    history.last_trusted = (BASE_TIME - timedelta(hours=1), 40.7128, -74.0060)  # NYC
    txn = make_txn(latitude=LONDON[0], longitude=LONDON[1], country="GB")
    signal = implausible_travel(txn, history, CFG)
    assert signal is not None
    assert signal.control == "Impossible travel"
    assert signal.points == CFG.impossible_travel_points


def test_plausible_travel_does_not_trigger():
    history = make_history()
    history.last_trusted = (BASE_TIME - timedelta(hours=12), 40.7128, -74.0060)
    txn = make_txn(latitude=LONDON[0], longitude=LONDON[1], country="GB")
    assert implausible_travel(txn, history, CFG) is None  # ~5,570 km in 12 h = ~460 km/h


def test_short_distance_never_counts_as_travel():
    history = make_history()
    history.last_trusted = (BASE_TIME - timedelta(minutes=2), 40.7128, -74.0060)
    nearby = make_txn(latitude=40.80, longitude=-73.95)
    assert implausible_travel(nearby, history, CFG) is None


def test_account_age_tiers():
    assert account_age(make_txn(account_age_days=3), UserHistory(), CFG).points == 10
    assert account_age(make_txn(account_age_days=20), UserHistory(), CFG).points == 5
    assert account_age(make_txn(account_age_days=90), UserHistory(), CFG) is None


def test_failed_login_tiers():
    assert failed_logins(make_txn(failed_login_attempts=2), UserHistory(), CFG) is None
    assert failed_logins(make_txn(failed_login_attempts=3), UserHistory(), CFG).points == 10
    assert failed_logins(make_txn(failed_login_attempts=6), UserHistory(), CFG).points == 15


def test_high_risk_merchant_category():
    signal = merchant_category_risk(make_txn(merchant_category="gift_cards"), UserHistory(), CFG)
    assert signal is not None and signal.points == CFG.high_risk_merchant_points
