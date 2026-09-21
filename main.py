"""RiskLens entry point: generate data, score it, write reports and charts."""
from __future__ import annotations

import argparse

import pandas as pd

from src.data_generator import DEFAULT_SEED, DEFAULT_USERS, generate_transactions
from src.reporting import build_summary, format_terminal_summary, save_reports
from src.risk_engine import RiskEngine
from src.rules import DEFAULT_CONFIG
from src.utils import DATA_DIR, DOCS_DIR, OUTPUT_DIR, REPO_ROOT, ensure_dirs
from src.visualization import generate_all_charts


def run(seed: int = DEFAULT_SEED, n_users: int = DEFAULT_USERS) -> tuple[pd.DataFrame, dict]:
    """Full pipeline; returns the scored frame and the summary dict."""
    ensure_dirs(DATA_DIR, OUTPUT_DIR, DOCS_DIR)

    transactions = generate_transactions(seed=seed, n_users=n_users)
    transactions.to_csv(DATA_DIR / "synthetic_transactions.csv", index=False, lineterminator="\n")

    engine = RiskEngine(DEFAULT_CONFIG)
    scored = engine.score_dataframe(transactions)

    summary = build_summary(scored, DEFAULT_CONFIG, seed)
    save_reports(scored, summary, OUTPUT_DIR)
    generate_all_charts(scored, DEFAULT_CONFIG, DOCS_DIR)
    return scored, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="RiskLens explainable transaction risk engine (synthetic data).")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed for reproducible data")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS, help="number of synthetic users")
    args = parser.parse_args()

    scored, summary = run(args.seed, args.users)
    print(format_terminal_summary(summary, OUTPUT_DIR.relative_to(REPO_ROOT), DOCS_DIR.relative_to(REPO_ROOT)))

    top = scored.loc[scored["risk_score"].idxmax()]
    print(f"\nHighest-risk transaction: {top['transaction_id']} (user {top['user_id']})")
    print(top["explanation"])


if __name__ == "__main__":
    main()
