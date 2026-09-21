"""Load and validate user-supplied transaction data (e.g. an uploaded CSV).

Only a few columns are strictly required. Optional columns get neutral
defaults, and every applied default is reported so the user knows what the
engine assumed about their data.
"""
from __future__ import annotations

import warnings

import pandas as pd

REQUIRED_COLUMNS = [
    "transaction_id", "user_id", "timestamp", "amount", "device_id",
    "country", "latitude", "longitude",
]

# column -> (default value, why it is safe/neutral)
OPTIONAL_DEFAULTS: dict[str, tuple[object, str]] = {
    "currency": ("USD", "assumed USD"),
    "ip_address": ("unknown", "no IP shown in explanations"),
    "ip_risk_score": (0.0, "IP reputation control cannot fire"),
    "merchant_category": ("unknown", "merchant control cannot fire"),
    "account_age_days": (365, "new-account control cannot fire"),
    "failed_login_attempts": (0, "failed-login control cannot fire"),
}

NUMERIC_COLUMNS = ["amount", "latitude", "longitude", "ip_risk_score",
                   "account_age_days", "failed_login_attempts"]


class DataValidationError(ValueError):
    """Raised with a human-readable message when the input cannot be scored."""


def validate_transactions(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return a cleaned frame and a list of notes about defaults applied."""
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]

    if df.empty:
        raise DataValidationError("The file has no rows.")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataValidationError(
            "Missing required column(s): " + ", ".join(missing)
            + ". Required columns are: " + ", ".join(REQUIRED_COLUMNS) + "."
        )

    notes: list[str] = []
    for column, (default, effect) in OPTIONAL_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default
            notes.append(f"Column '{column}' not provided: used {default!r} ({effect}).")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # mixed date formats are handled by errors="coerce"
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    for column in NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")

    required_values = REQUIRED_COLUMNS + ["ip_risk_score", "account_age_days", "failed_login_attempts"]
    bad = df[required_values].isna().any(axis=1)
    if bad.any():
        first = df.index[bad][0] + 2  # +2: header row and 1-based row numbers
        raise DataValidationError(
            f"{int(bad.sum())} row(s) have missing or unreadable values in required fields "
            f"(first problem near row {first}). Check timestamps, amounts, and coordinates."
        )
    if not df["latitude"].between(-90, 90).all() or not df["longitude"].between(-180, 180).all():
        raise DataValidationError("Latitude must be between -90 and 90, and longitude between -180 and 180.")
    if (df["amount"] <= 0).any():
        raise DataValidationError("All amounts must be greater than 0.")
    if df["transaction_id"].duplicated().any():
        raise DataValidationError("transaction_id values must be unique.")

    for column in ("transaction_id", "user_id", "device_id", "country"):
        df[column] = df[column].astype(str)
    df["account_age_days"] = df["account_age_days"].astype(int)
    df["failed_login_attempts"] = df["failed_login_attempts"].astype(int)
    return df, notes
