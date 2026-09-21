"""Tests for scoring, decisions, explanations, and the batch pipeline."""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from src.data_generator import generate_transactions
from src.models import Decision
from src.risk_engine import MAX_SCORE, RiskEngine
from src.rules import DEFAULT_CONFIG
from tests.conftest import BASE_TIME, LONDON, make_history, make_txn

engine = RiskEngine()


def test_normal_transaction_gets_low_risk_and_is_allowed(txn, history):
    result = engine.assess(txn, history)
    assert result.score == 0
    assert result.decision is Decision.ALLOW
    assert result.signals == ()
    assert "No risk controls triggered" in result.explanation


def test_new_country_increases_score(txn, history):
    base = engine.assess(txn, history).score
    changed = engine.assess(make_txn(country="GB"), history).score
    assert changed == base + DEFAULT_CONFIG.new_country_points


def test_new_device_increases_score(history):
    base = engine.assess(make_txn(), history).score
    changed = engine.assess(make_txn(device_id="DEV-NEW"), history).score
    assert changed == base + DEFAULT_CONFIG.new_device_points


def test_high_ip_risk_increases_score(history):
    low = engine.assess(make_txn(ip_risk_score=10), history).score
    high = engine.assess(make_txn(ip_risk_score=95), history).score
    assert high > low


def test_unusual_amount_increases_score(history):
    normal = engine.assess(make_txn(amount=45), history).score
    unusual = engine.assess(make_txn(amount=900), history).score
    assert unusual > normal


def test_velocity_rule_triggers_through_engine(history):
    for seconds in (20, 40, 60, 80):
        history.attempts.append(BASE_TIME - timedelta(seconds=seconds))
    result = engine.assess(make_txn(), history)
    assert "Transaction velocity" in result.triggered_controls


def test_impossible_travel_triggers_through_engine(history):
    history.last_trusted = (BASE_TIME - timedelta(minutes=45), 40.7128, -74.0060)
    result = engine.assess(make_txn(latitude=LONDON[0], longitude=LONDON[1], country="GB"), history)
    assert "Impossible travel" in result.triggered_controls


def test_score_never_exceeds_100():
    history = make_history()
    history.last_trusted = (BASE_TIME - timedelta(minutes=30), 40.7128, -74.0060)
    extreme = make_txn(
        country="GB", latitude=LONDON[0], longitude=LONDON[1], device_id="DEV-X",
        ip_risk_score=99, amount=5000, failed_login_attempts=9,
        merchant_category="crypto_exchange", account_age_days=1,
    )
    result = engine.assess(extreme, history)
    assert result.score == MAX_SCORE
    assert result.decision is Decision.BLOCK
    assert "capped" in result.explanation


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0, Decision.ALLOW), (29, Decision.ALLOW), (30, Decision.REVIEW),
     (59, Decision.REVIEW), (60, Decision.BLOCK), (100, Decision.BLOCK)],
)
def test_decisions_match_thresholds(score, expected):
    assert engine.decide(score) is expected


def test_explanation_lists_every_triggered_control_with_points(history):
    result = engine.assess(make_txn(country="GB", device_id="DEV-NEW"), history)
    assert f"+{DEFAULT_CONFIG.new_country_points}" in result.explanation
    assert "New country" in result.explanation and "New device" in result.explanation
    assert result.score == sum(s.points for s in result.signals)


# ---- batch pipeline -------------------------------------------------------

@pytest.fixture(scope="module")
def scored() -> pd.DataFrame:
    return engine.score_dataframe(generate_transactions(seed=42))


def test_batch_output_has_required_columns(scored):
    for col in ("risk_score", "decision", "triggered_controls", "explanation"):
        assert col in scored.columns
    assert scored["risk_score"].between(0, MAX_SCORE).all()
    assert set(scored["decision"]) <= {"ALLOW", "REVIEW", "BLOCK"}


def test_batch_decisions_are_consistent_with_scores(scored):
    for score, decision in zip(scored["risk_score"], scored["decision"], strict=True):
        assert decision == engine.decide(int(score)).value


def test_first_transaction_for_a_user_has_no_baseline_signals(scored):
    first = scored.groupby("user_id").head(1)
    baseline_controls = ("New device", "New country", "Unusual transaction amount")
    for controls in first["triggered_controls"]:
        assert not any(c in controls for c in baseline_controls)


def test_blocked_transactions_do_not_poison_user_baseline():
    """An attacker's blocked device must still look 'new' on the next attempt."""
    history = make_history()
    attack = make_txn(device_id="DEV-ATK", country="GB", latitude=LONDON[0], longitude=LONDON[1],
                      ip_risk_score=97, amount=800, failed_login_attempts=6)
    engine.assess(attack, history)
    # Simulate what score_dataframe does for a BLOCK: attempt recorded, baseline not.
    history.record_attempt(attack)
    assert "DEV-ATK" not in history.devices
    assert "GB" not in history.countries
