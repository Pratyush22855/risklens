"""Matplotlib charts. Each function returns a Figure and optionally saves a PNG."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from src.reporting import DECISION_ORDER, control_stats, decisions_by_scenario  # noqa: E402
from src.rules import RuleConfig  # noqa: E402

COLORS = {"ALLOW": "#2e8b57", "REVIEW": "#e0a100", "BLOCK": "#c0392b"}


def _finish(fig: Figure, path: Path | None) -> Figure:
    fig.tight_layout()
    if path is not None:
        fig.savefig(path, dpi=150)
    return fig


def plot_score_distribution(scored: pd.DataFrame, config: RuleConfig, path: Path | None = None) -> Figure:
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(scored["risk_score"], bins=range(0, 105, 5), color="#4a6fa5", edgecolor="white")
    ax.axvline(config.review_threshold, color=COLORS["REVIEW"], linestyle="--",
               label=f"REVIEW >= {config.review_threshold}")
    ax.axvline(config.block_threshold, color=COLORS["BLOCK"], linestyle="--",
               label=f"BLOCK >= {config.block_threshold}")
    ax.set_yscale("log")
    ax.set_xlabel("Risk score (0-100)")
    ax.set_ylabel("Transactions (log scale)")
    ax.set_title("RiskLens: Risk Score Distribution")
    ax.legend()
    return _finish(fig, path)


def plot_decision_distribution(scored: pd.DataFrame, path: Path | None = None) -> Figure:
    counts = scored["decision"].value_counts().reindex(DECISION_ORDER, fill_value=0)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    bars = ax.bar(counts.index, counts.values, color=[COLORS[d] for d in counts.index])
    ax.bar_label(bars)
    ax.set_ylabel("Transactions")
    ax.set_title("RiskLens: Decision Distribution")
    return _finish(fig, path)


def plot_control_frequency(scored: pd.DataFrame, path: Path | None = None) -> Figure:
    stats = control_stats(scored).sort_values("times_triggered")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.barh(stats["control"], stats["times_triggered"], color="#4a6fa5")
    ax.bar_label(bars)
    ax.set_xlabel("Times triggered")
    ax.set_title("RiskLens: Control Trigger Frequency")
    return _finish(fig, path)


def plot_decisions_by_scenario(scored: pd.DataFrame, path: Path | None = None) -> Figure:
    counts = decisions_by_scenario(scored)
    totals = counts.sum(axis=1)
    share = counts.div(totals, axis=0) * 100
    share.index = [f"{name} (n={totals[name]})" for name in share.index]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    share.plot(kind="barh", stacked=True, ax=ax, color=[COLORS[c] for c in share.columns])
    ax.set_xlim(0, 100)
    ax.set_xlabel("% of that scenario's transactions")
    ax.set_ylabel("Synthetic scenario label")
    ax.set_title("RiskLens: Decisions by Synthetic Scenario")
    ax.legend(title="decision", loc="lower left", bbox_to_anchor=(1.01, 0))
    return _finish(fig, path)


def generate_all_charts(scored: pd.DataFrame, config: RuleConfig, docs_dir: Path) -> list[Path]:
    """Render every applicable chart to PNG and return the written paths."""
    docs_dir.mkdir(parents=True, exist_ok=True)
    jobs = {
        "risk_score_distribution.png": lambda p: plot_score_distribution(scored, config, p),
        "decision_distribution.png": lambda p: plot_decision_distribution(scored, p),
    }
    if not control_stats(scored).empty:
        jobs["control_frequency.png"] = lambda p: plot_control_frequency(scored, p)
    if "scenario" in scored.columns:
        jobs["decisions_by_scenario.png"] = lambda p: plot_decisions_by_scenario(scored, p)
    written = []
    for name, draw in jobs.items():
        path = docs_dir / name
        plt.close(draw(path))
        written.append(path)
    return written
