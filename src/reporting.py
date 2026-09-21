"""Turns scored transactions into analyst-facing reports and summary metrics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.rules import RuleConfig

DECISION_ORDER = ["ALLOW", "REVIEW", "BLOCK"]


def control_stats(scored: pd.DataFrame) -> pd.DataFrame:
    """Frequency and average points contributed by each control."""
    totals: dict[str, list[int]] = {}
    for raw in scored["control_points"]:
        for control, points in json.loads(raw).items():
            totals.setdefault(control, []).append(points)
    columns = ["control", "times_triggered", "avg_points"]
    if not totals:
        return pd.DataFrame(columns=columns)
    rows = [
        {"control": c, "times_triggered": len(p), "avg_points": round(sum(p) / len(p), 1)}
        for c, p in totals.items()
    ]
    return pd.DataFrame(rows).sort_values("times_triggered", ascending=False).reset_index(drop=True)


def decisions_by_scenario(scored: pd.DataFrame) -> pd.DataFrame:
    """Cross-tab of synthetic scenario label vs. engine decision."""
    table = pd.crosstab(scored["scenario"], scored["decision"])
    return table.reindex(columns=DECISION_ORDER, fill_value=0)


def build_summary(scored: pd.DataFrame, config: RuleConfig, seed: int) -> dict[str, Any]:
    """Aggregate metrics saved to risk_summary.json (all values computed from the run)."""
    counts = scored["decision"].value_counts()
    total = len(scored)
    top = scored.nlargest(5, "risk_score")[["transaction_id", "user_id", "risk_score", "decision"]]
    return {
        "seed": seed,
        "transactions_analyzed": total,
        "decisions": {d: int(counts.get(d, 0)) for d in DECISION_ORDER},
        "decision_rates_pct": {d: round(100 * int(counts.get(d, 0)) / total, 1) for d in DECISION_ORDER},
        "risk_score": {
            "mean": round(float(scored["risk_score"].mean()), 2),
            "median": float(scored["risk_score"].median()),
            "p95": float(scored["risk_score"].quantile(0.95)),
            "max": int(scored["risk_score"].max()),
        },
        "thresholds": {"review": config.review_threshold, "block": config.block_threshold},
        "control_frequency": control_stats(scored).to_dict(orient="records"),
        "decisions_by_scenario": (
            decisions_by_scenario(scored).to_dict(orient="index") if "scenario" in scored.columns else {}
        ),
        "top_risk_transactions": top.to_dict(orient="records"),
    }


def save_reports(scored: pd.DataFrame, summary: dict[str, Any], output_dir: Path) -> None:
    """Write scored CSV, flagged (REVIEW/BLOCK) CSV, and the JSON summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scored_out = scored.copy()
    scored_out["timestamp"] = scored_out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    scored_out.to_csv(output_dir / "scored_transactions.csv", index=False, lineterminator="\n")

    flagged = scored_out[scored_out["decision"] != "ALLOW"].sort_values(
        ["risk_score", "timestamp"], ascending=[False, True]
    )
    flagged.to_csv(output_dir / "flagged_transactions.csv", index=False, lineterminator="\n")

    with (output_dir / "risk_summary.json").open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")


def format_terminal_summary(summary: dict[str, Any], output_dir: Path, docs_dir: Path) -> str:
    d = summary["decisions"]
    score = summary["risk_score"]
    return "\n".join([
        "RiskLens Analysis Complete",
        f"Transactions analyzed: {summary['transactions_analyzed']}",
        f"Allowed: {d['ALLOW']}",
        f"Review: {d['REVIEW']}",
        f"Blocked: {d['BLOCK']}",
        f"Average risk score: {score['mean']}",
        f"Highest risk score: {score['max']}",
        f"Reports saved to {output_dir}",
        f"Charts saved to {docs_dir}",
    ])
