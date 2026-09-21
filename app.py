"""RiskLens web page: upload a transaction CSV, get scores, decisions, explanations.

Run with:  streamlit run app.py
Everything is processed locally on your machine; nothing is sent anywhere.
"""
from __future__ import annotations

import io

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from src.data_generator import generate_transactions
from src.loader import (
    OPTIONAL_DEFAULTS,
    REQUIRED_COLUMNS,
    DataValidationError,
    validate_transactions,
)
from src.reporting import DECISION_ORDER, control_stats
from src.risk_engine import RiskEngine
from src.rules import DEFAULT_CONFIG
from src.visualization import (
    plot_control_frequency,
    plot_decision_distribution,
    plot_score_distribution,
)

st.set_page_config(page_title="RiskLens", page_icon="🔎", layout="wide")


@st.cache_data(show_spinner=False)
def score(transactions: pd.DataFrame) -> pd.DataFrame:
    return RiskEngine(DEFAULT_CONFIG).score_dataframe(transactions)


@st.cache_data(show_spinner=False)
def sample_data() -> pd.DataFrame:
    return generate_transactions()


def template_csv() -> bytes:
    columns = REQUIRED_COLUMNS + list(OPTIONAL_DEFAULTS)
    return sample_data().head(8)[columns].to_csv(index=False).encode("utf-8")


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    out = df.copy()
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out.to_csv(index=False).encode("utf-8")


def show_figure(fig) -> None:
    st.pyplot(fig)
    plt.close(fig)


# ---------------------------------------------------------------- sidebar
st.sidebar.title("RiskLens")
st.sidebar.caption("Explainable transaction security risk engine")
source = st.sidebar.radio("Data source", ["Upload my CSV", "Use built-in synthetic sample"])
uploaded = None
if source == "Upload my CSV":
    uploaded = st.sidebar.file_uploader("Transaction CSV", type=["csv"])
    st.sidebar.download_button("Download CSV template", template_csv(), "risklens_template.csv", "text/csv")
    st.sidebar.markdown(
        "**Required columns**\n\n" + ", ".join(f"`{c}`" for c in REQUIRED_COLUMNS)
        + "\n\n**Optional** (defaults used if missing)\n\n" + ", ".join(f"`{c}`" for c in OPTIONAL_DEFAULTS)
    )
st.sidebar.markdown(
    f"**Thresholds**: REVIEW >= {DEFAULT_CONFIG.review_threshold}, BLOCK >= {DEFAULT_CONFIG.block_threshold}"
)

# ------------------------------------------------------------------- main
st.title("RiskLens: Transaction Risk Analysis")
st.caption(
    "Rule-based, explainable scoring. Illustrative weights, not calibrated on real institution data. "
    "Not a production fraud system."
)

if source == "Use built-in synthetic sample":
    raw = sample_data()
elif uploaded is not None:
    try:
        raw = pd.read_csv(uploaded)
    except Exception as err:  # unreadable/non-CSV file
        st.error(f"Could not read that file as a CSV: {err}")
        st.stop()
else:
    st.info("Upload a CSV in the sidebar to begin, or switch to the built-in synthetic sample. "
            "Use **Download CSV template** to see the expected format.")
    st.stop()

try:
    clean, notes = validate_transactions(raw)
except DataValidationError as err:
    st.error(str(err))
    st.stop()

if notes:
    with st.expander(f"{len(notes)} optional column(s) missing: default values used (click to see)"):
        for note in notes:
            st.write("- " + note)

scored = score(clean)
counts = scored["decision"].value_counts().reindex(DECISION_ORDER, fill_value=0)

cols = st.columns(5)
cols[0].metric("Transactions", len(scored))
cols[1].metric("Allowed", int(counts["ALLOW"]))
cols[2].metric("Review", int(counts["REVIEW"]))
cols[3].metric("Blocked", int(counts["BLOCK"]))
cols[4].metric("Avg risk score", f"{scored['risk_score'].mean():.1f}")

overview, flagged_tab, explain_tab, download_tab = st.tabs(
    ["Overview", "Flagged transactions", "Explain a transaction", "Download"]
)

with overview:
    left, right = st.columns(2)
    with left:
        show_figure(plot_decision_distribution(scored))
    with right:
        show_figure(plot_score_distribution(scored, DEFAULT_CONFIG))
    if not control_stats(scored).empty:
        show_figure(plot_control_frequency(scored))
        st.dataframe(control_stats(scored), hide_index=True, use_container_width=True)
    else:
        st.success("No risk controls triggered on this data.")

flagged = scored[scored["decision"] != "ALLOW"].sort_values("risk_score", ascending=False)
table_columns = ["transaction_id", "user_id", "timestamp", "amount", "country",
                 "risk_score", "decision", "triggered_controls"]

with flagged_tab:
    if flagged.empty:
        st.success("Nothing was flagged for REVIEW or BLOCK.")
    else:
        choice = st.multiselect("Show decisions", ["REVIEW", "BLOCK"], default=["REVIEW", "BLOCK"])
        st.dataframe(flagged[flagged["decision"].isin(choice)][table_columns],
                     hide_index=True, use_container_width=True)

with explain_tab:
    pool = flagged if not flagged.empty else scored
    label = "flagged transaction" if not flagged.empty else "transaction"
    selected = st.selectbox(f"Pick a {label}", pool["transaction_id"].tolist())
    row = scored[scored["transaction_id"] == selected].iloc[0]
    st.subheader(f"{row['transaction_id']}: {row['decision']} (score {row['risk_score']})")
    st.code(row["explanation"], language="text")
    details = row[["user_id", "timestamp", "amount", "currency", "country", "device_id",
                   "ip_address", "ip_risk_score", "merchant_category"]]
    st.dataframe(details.astype(str).rename("value").to_frame(), use_container_width=True)

with download_tab:
    st.download_button("Download all scored transactions (CSV)", to_csv_bytes(scored),
                       "scored_transactions.csv", "text/csv")
    st.download_button("Download flagged transactions (CSV)", to_csv_bytes(flagged),
                       "flagged_transactions.csv", "text/csv")
    st.caption(f"Analyzed {len(scored)} transactions from {scored['user_id'].nunique()} users.")
