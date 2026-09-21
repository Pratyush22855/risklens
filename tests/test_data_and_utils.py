"""Tests for the synthetic data generator, reporting, and geo helpers."""
from __future__ import annotations

import ipaddress

import pytest

from src.data_generator import generate_transactions
from src.reporting import build_summary, control_stats
from src.risk_engine import RiskEngine
from src.rules import DEFAULT_CONFIG
from src.utils import haversine_km

REQUIRED_COLUMNS = {
    "transaction_id", "user_id", "timestamp", "amount", "currency", "device_id",
    "ip_address", "ip_risk_score", "country", "latitude", "longitude",
    "merchant_category", "account_age_days", "failed_login_attempts",
}


def test_generator_is_reproducible_for_a_fixed_seed():
    a = generate_transactions(seed=7, n_users=20)
    b = generate_transactions(seed=7, n_users=20)
    assert a.equals(b)


def test_generator_changes_with_seed():
    assert not generate_transactions(seed=1, n_users=20).equals(generate_transactions(seed=2, n_users=20))


def test_default_dataset_has_expected_shape():
    df = generate_transactions()
    assert 300 <= len(df) <= 1000
    assert REQUIRED_COLUMNS <= set(df.columns)
    assert df["transaction_id"].is_unique
    assert (df["amount"] > 0).all()
    assert df["ip_risk_score"].between(0, 100).all()
    assert (df["scenario"] == "normal").mean() > 0.7  # mostly ordinary activity


def test_all_ip_addresses_are_reserved_documentation_addresses():
    """Guards the 'no real data' promise: IPs come only from RFC 5737 test ranges."""
    networks = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
    for ip in generate_transactions()["ip_address"].unique():
        assert any(ipaddress.ip_address(ip) in n for n in networks), ip


def test_haversine_known_distance():
    assert haversine_km(40.7128, -74.0060, 51.5074, -0.1278) == pytest.approx(5570, rel=0.01)
    assert haversine_km(10, 10, 10, 10) == pytest.approx(0)


def test_summary_counts_match_scored_frame():
    scored = RiskEngine().score_dataframe(generate_transactions(seed=42))
    summary = build_summary(scored, DEFAULT_CONFIG, seed=42)
    assert summary["transactions_analyzed"] == len(scored)
    assert sum(summary["decisions"].values()) == len(scored)
    assert not control_stats(scored).empty
