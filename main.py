"""RiskLens entry point.

Default: generate synthetic data, score it, write reports and charts.
With --input: score your own CSV instead (results go to output/custom/).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.data_generator import DEFAULT_SEED, DEFAULT_USERS, generate_transactions
from src.loader import DataValidationError, validate_transactions
from src.reporting import build_summary, format_terminal_summary, save_reports
from src.risk_engine import RiskEngine
from src.rules import DEFAULT_CONFIG
from src.utils import DATA_DIR, DOCS_DIR, OUTPUT_DIR, REPO_ROOT, ensure_dirs
from src.visualization import generate_all_charts

CUSTOM_DIR = OUTPUT_DIR / "custom"


def analyze(transactions: pd.DataFrame, report_dir: Path, chart_dir: Path, seed: int | None = None):
    """Score a validated transaction frame and write reports and charts."""
    scored = RiskEngine(DEFAULT_CONFIG).score_dataframe(transactions)
    summary = build_summary(scored, DEFAULT_CONFIG, seed)
    save_reports(scored, summary, report_dir)
    generate_all_charts(scored, DEFAULT_CONFIG, chart_dir)
    return scored, summary


def run(seed: int = DEFAULT_SEED, n_users: int = DEFAULT_USERS) -> tuple[pd.DataFrame, dict]:
    """Synthetic-data pipeline; returns the scored frame and the summary dict."""
    ensure_dirs(DATA_DIR, OUTPUT_DIR, DOCS_DIR)
    transactions = generate_transactions(seed=seed, n_users=n_users)
    transactions.to_csv(DATA_DIR / "synthetic_transactions.csv", index=False, lineterminator="\n")
    return analyze(transactions, OUTPUT_DIR, DOCS_DIR, seed)


def run_on_file(path: Path) -> tuple[pd.DataFrame, dict]:
    """Score a user-supplied CSV; outputs go to output/custom/."""
    validated, notes = validate_transactions(pd.read_csv(path))
    for note in notes:
        print(f"Note: {note}")
    ensure_dirs(CUSTOM_DIR)
    return analyze(validated, CUSTOM_DIR, CUSTOM_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="RiskLens explainable transaction risk engine.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed for synthetic data")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="number of synthetic users")
    parser.add_argument("--input", type=Path, help="score your own CSV instead of generating synthetic data")
    args = parser.parse_args()

    try:
        if args.input:
            scored, summary = run_on_file(args.input)
            out_dir = CUSTOM_DIR
        else:
            scored, summary = run(args.seed, args.users)
            out_dir = OUTPUT_DIR
    except (DataValidationError, FileNotFoundError) as err:
        raise SystemExit(f"Error: {err}") from err

    charts = CUSTOM_DIR if args.input else DOCS_DIR
    print(format_terminal_summary(summary, out_dir.relative_to(REPO_ROOT), charts.relative_to(REPO_ROOT)))

    top = scored.loc[scored["risk_score"].idxmax()]
    print(f"\nHighest-risk transaction: {top['transaction_id']} (user {top['user_id']})")
    print(top["explanation"])


if __name__ == "__main__":
    main()
