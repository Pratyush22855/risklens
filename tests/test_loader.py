"""Tests for validating user-supplied CSV data."""
from __future__ import annotations

import pandas as pd
import pytest

from src.data_generator import generate_transactions
from src.loader import REQUIRED_COLUMNS, DataValidationError, validate_transactions
from src.risk_engine import RiskEngine


@pytest.fixture
def minimal() -> pd.DataFrame:
    return generate_transactions(seed=3, n_users=15)[REQUIRED_COLUMNS].copy()


def test_minimal_columns_are_accepted_and_defaults_reported(minimal):
    df, notes = validate_transactions(minimal)
    assert len(notes) == 6  # all optional columns defaulted
    assert {"ip_risk_score", "merchant_category", "account_age_days"} <= set(df.columns)


def test_minimal_data_can_be_scored_end_to_end(minimal):
    df, _ = validate_transactions(minimal)
    scored = RiskEngine().score_dataframe(df)
    assert scored["risk_score"].between(0, 100).all()
    assert set(scored["decision"]) <= {"ALLOW", "REVIEW", "BLOCK"}


def test_full_synthetic_data_passes_validation():
    df, notes = validate_transactions(generate_transactions(seed=3, n_users=15))
    assert notes == []
    assert len(df) > 0


@pytest.mark.parametrize("column", REQUIRED_COLUMNS)
def test_missing_required_column_is_rejected_with_its_name(minimal, column):
    with pytest.raises(DataValidationError, match=column):
        validate_transactions(minimal.drop(columns=[column]))


def test_empty_file_is_rejected():
    with pytest.raises(DataValidationError, match="no rows"):
        validate_transactions(pd.DataFrame(columns=REQUIRED_COLUMNS))


def test_unreadable_timestamp_is_rejected(minimal):
    minimal.loc[0, "timestamp"] = "not a date"
    with pytest.raises(DataValidationError, match="unreadable"):
        validate_transactions(minimal)


def test_non_positive_amount_is_rejected(minimal):
    minimal.loc[0, "amount"] = -5
    with pytest.raises(DataValidationError, match="greater than 0"):
        validate_transactions(minimal)


def test_out_of_range_coordinates_are_rejected(minimal):
    minimal.loc[0, "latitude"] = 123
    with pytest.raises(DataValidationError, match="Latitude"):
        validate_transactions(minimal)


def test_duplicate_transaction_ids_are_rejected(minimal):
    minimal.loc[1, "transaction_id"] = minimal.loc[0, "transaction_id"]
    with pytest.raises(DataValidationError, match="unique"):
        validate_transactions(minimal)
