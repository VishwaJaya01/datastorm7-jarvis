"""Minimal Round 2 Outlet Intelligence Streamlit app."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.xai.outlet_explainer import explain_outlet


PREDICTIONS_PATH = Path("submissions/jarvis_predictions.csv")
BUDGET_PATH = Path("submissions/jarvis_budget_allocations.csv")
GOLD_PATH = Path("data/gold/master_features.csv")


def load_outputs() -> tuple[pd.DataFrame | None, list[str]]:
    """Load available local outputs and return friendly missing-file messages."""

    missing: list[str] = []
    if not PREDICTIONS_PATH.exists():
        missing.append(str(PREDICTIONS_PATH))
    if not BUDGET_PATH.exists():
        missing.append(str(BUDGET_PATH))
    if not GOLD_PATH.exists():
        missing.append(str(GOLD_PATH))
    if missing:
        return None, missing

    predictions = pd.read_csv(PREDICTIONS_PATH)
    budget = pd.read_csv(BUDGET_PATH)
    gold = pd.read_csv(GOLD_PATH)

    data = predictions.merge(budget, on="Outlet_ID", how="left")
    data = data.merge(gold.drop_duplicates("Outlet_ID"), on="Outlet_ID", how="left")
    data["Trade_Spend_Allocation_LKR"] = pd.to_numeric(
        data.get("Trade_Spend_Allocation_LKR"),
        errors="coerce",
    ).fillna(0.0)
    return data, []


def main() -> None:
    st.set_page_config(page_title="Team Jarvis Outlet Intelligence", layout="wide")
    st.title("Team Jarvis Outlet Intelligence")

    data, missing = load_outputs()
    if data is None:
        st.warning("Required local outputs are missing.")
        st.write("Run the Round 2 pipeline from the repository root:")
        st.code("python -m src.pipeline.make_round2_submission", language="bash")
        st.write("Missing files:")
        for path in missing:
            st.write(f"- `{path}`")
        return

    filtered = apply_sidebar_filters(data)
    show_overview(filtered)
    show_outlet_table(filtered)
    show_outlet_drilldown(filtered)


def apply_sidebar_filters(data: pd.DataFrame) -> pd.DataFrame:
    """Apply simple Province, Distributor_ID, and Outlet_ID filters."""

    st.sidebar.header("Filters")
    filtered = data.copy()

    for column in ["Province", "Distributor_ID"]:
        if column in filtered.columns:
            options = sorted(filtered[column].dropna().astype(str).unique())
            selected = st.sidebar.multiselect(column, options=options)
            if selected:
                filtered = filtered.loc[filtered[column].astype(str).isin(selected)]

    search = st.sidebar.text_input("Search Outlet_ID")
    if search:
        filtered = filtered.loc[filtered["Outlet_ID"].astype(str).str.contains(search, case=False, na=False)]

    return filtered


def show_overview(data: pd.DataFrame) -> None:
    """Show compact portfolio metrics."""

    st.subheader("Overview")
    prediction = pd.to_numeric(data["Maximum_Monthly_Liters"], errors="coerce")
    allocation = pd.to_numeric(data["Trade_Spend_Allocation_LKR"], errors="coerce").fillna(0.0)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Outlets", f"{len(data):,}")
    col2.metric("Median Potential", f"{prediction.median():,.2f} L")
    col3.metric("Total Allocation", f"LKR {allocation.sum():,.2f}")
    col4.metric("Funded Outlets", f"{int(allocation.gt(0).sum()):,}")


def show_outlet_table(data: pd.DataFrame) -> None:
    """Show a scan-friendly outlet table."""

    st.subheader("Outlet Table")
    preferred = [
        "Outlet_ID",
        "Maximum_Monthly_Liters",
        "Trade_Spend_Allocation_LKR",
        "Distributor_ID",
        "Province",
        "Outlet_Size",
        "Cooler_Count",
        "poi_available",
        "demand_driver_score_1000m",
        "market_saturation_index",
    ]
    columns = [column for column in preferred if column in data.columns]
    st.dataframe(data[columns], use_container_width=True, hide_index=True)


def show_outlet_drilldown(data: pd.DataFrame) -> None:
    """Show one selected outlet and deterministic explanation."""

    st.subheader("Outlet Drilldown")
    outlet_ids = data["Outlet_ID"].dropna().astype(str).sort_values().tolist()
    if not outlet_ids:
        st.info("No outlets match the current filters.")
        return

    selected_id = st.selectbox("Select Outlet_ID", options=outlet_ids)
    row = data.loc[data["Outlet_ID"].astype(str) == selected_id].iloc[0]

    col1, col2 = st.columns(2)
    col1.metric("Predicted Potential", f"{float(row['Maximum_Monthly_Liters']):,.2f} L")
    col2.metric("Budget Allocation", f"LKR {float(row['Trade_Spend_Allocation_LKR']):,.2f}")

    st.markdown("**Explanation**")
    st.write(explain_outlet(row.to_dict()))


if __name__ == "__main__":
    main()
