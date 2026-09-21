"""Scoring engine: runs every control, sums points, and decides.

Transactions are processed in timestamp order and each one is scored using
only *earlier* history, so there is no look-ahead leakage.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence

import pandas as pd

from src.models import Decision, RiskAssessment, RiskSignal, Transaction, UserHistory
from src.rules import ALL_RULES, DEFAULT_CONFIG, Rule, RuleConfig

MAX_SCORE = 100


class RiskEngine:
    """Applies weighted controls to transactions and explains the outcome."""

    def __init__(self, config: RuleConfig = DEFAULT_CONFIG, rules: Sequence[Rule] = ALL_RULES) -> None:
        self.config = config
        self.rules = tuple(rules)

    def decide(self, score: int) -> Decision:
        """Map a 0-100 score to a decision using the configured thresholds."""
        if score >= self.config.block_threshold:
            return Decision.BLOCK
        if score >= self.config.review_threshold:
            return Decision.REVIEW
        return Decision.ALLOW

    def evaluate_signals(self, txn: Transaction, history: UserHistory) -> list[RiskSignal]:
        signals = (rule(txn, history, self.config) for rule in self.rules)
        return [s for s in signals if s is not None]

    def assess(self, txn: Transaction, history: UserHistory) -> RiskAssessment:
        """Score one transaction against a user's prior history."""
        signals = self.evaluate_signals(txn, history)
        score = min(MAX_SCORE, sum(s.points for s in signals))
        decision = self.decide(score)
        return RiskAssessment(
            transaction_id=txn.transaction_id,
            score=score,
            decision=decision,
            signals=tuple(signals),
            explanation=self.explain(score, decision, signals),
        )

    def explain(self, score: int, decision: Decision, signals: Sequence[RiskSignal]) -> str:
        """Human-readable rationale an analyst can verify line by line."""
        cfg = self.config
        header = (
            f"Risk score: {score}/100 -> {decision.value} "
            f"(REVIEW >= {cfg.review_threshold}, BLOCK >= {cfg.block_threshold})"
        )
        if not signals:
            return f"{header}. No risk controls triggered."
        lines = [f"  - {s.control}: +{s.points} ({s.detail})" for s in signals]
        raw_total = sum(s.points for s in signals)
        capped = f" [raw total {raw_total} capped at {MAX_SCORE}]" if raw_total > MAX_SCORE else ""
        return header + capped + "\nTriggered controls:\n" + "\n".join(lines)

    def score_dataframe(self, transactions: pd.DataFrame) -> pd.DataFrame:
        """Score every transaction chronologically and return an enriched frame."""
        ordered = transactions.copy()
        ordered["timestamp"] = pd.to_datetime(ordered["timestamp"], utc=True)
        ordered = ordered.sort_values(["timestamp", "transaction_id"]).reset_index(drop=True)

        histories: dict[str, UserHistory] = defaultdict(UserHistory)
        records: list[dict[str, object]] = []
        for row in ordered.to_dict(orient="records"):
            txn = Transaction.from_mapping(row)
            history = histories[txn.user_id]
            assessment = self.assess(txn, history)

            history.record_attempt(txn)
            if assessment.decision is not Decision.BLOCK:
                history.record_trusted(txn)

            records.append({
                "risk_score": assessment.score,
                "decision": assessment.decision.value,
                "triggered_controls": "; ".join(assessment.triggered_controls),
                "control_points": json.dumps({s.control: s.points for s in assessment.signals}),
                "explanation": assessment.explanation,
            })

        return pd.concat([ordered, pd.DataFrame(records)], axis=1)
