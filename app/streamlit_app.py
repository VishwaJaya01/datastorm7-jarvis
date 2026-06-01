"""Round 2 Outlet Intelligence Streamlit app."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.xai.outlet_explainer import explain_outlet
from src.xai.prompt_templates import build_outlet_explanation_prompt


PREDICTIONS_PATH = Path("submissions/jarvis_predictions.csv")
BUDGET_PATH = Path("submissions/jarvis_budget_allocations.csv")
GOLD_PATH = Path("data/gold/master_features.csv")


def load_outputs() -> tuple[pd.DataFrame | None, list[str]]:
    """Load local Round 2 outputs and return missing-file messages."""

    missing = [str(path) for path in [PREDICTIONS_PATH, BUDGET_PATH, GOLD_PATH] if not path.exists()]
    if missing:
        return None, missing

    predictions = pd.read_csv(PREDICTIONS_PATH)
    budget = pd.read_csv(BUDGET_PATH)
    gold = pd.read_csv(GOLD_PATH)

    data = predictions.merge(budget, on="Outlet_ID", how="left")
    data = data.merge(gold.drop_duplicates("Outlet_ID"), on="Outlet_ID", how="left")
    data["Maximum_Monthly_Liters"] = as_numeric(data, "Maximum_Monthly_Liters")
    data["Trade_Spend_Allocation_LKR"] = as_numeric(data, "Trade_Spend_Allocation_LKR")
    data["funded_status"] = data["Trade_Spend_Allocation_LKR"].gt(0).map({True: "Funded", False: "Not funded"})
    data["historical_baseline_liters"] = historical_baseline(data)
    data["opportunity_gap_liters"] = (
        data["Maximum_Monthly_Liters"] - data["historical_baseline_liters"]
    ).clip(lower=0)
    return data, []


def main() -> None:
    st.set_page_config(page_title="Team Jarvis Outlet Intelligence", layout="wide")
    st.title("Team Jarvis Outlet Intelligence")
    st.caption("Round 2 latent potential, Western Province trade spend, and outlet-level explanations.")

    data, missing = load_outputs()
    if data is None:
        show_missing_files(missing)
        return

    filtered = apply_sidebar_filters(data)
    overview_tab, explorer_tab, budget_tab, drilldown_tab = st.tabs(
        ["Overview", "Outlet Explorer", "Budget Allocation", "Outlet Drilldown / XAI"]
    )

    with overview_tab:
        show_overview(filtered)
    with explorer_tab:
        show_outlet_explorer(filtered)
    with budget_tab:
        show_budget_allocation(filtered)
    with drilldown_tab:
        show_outlet_drilldown(filtered)


def show_missing_files(missing: list[str]) -> None:
    """Show friendly startup guidance when outputs are absent."""

    st.warning("Required local outputs are missing.")
    st.write("Run the Round 2 pipeline from the repository root:")
    st.code("python -m src.pipeline.make_round2_submission", language="bash")
    st.write("Then validate the files:")
    st.code("python -m src.pipeline.validate_round2_submission", language="bash")
    st.write("Missing files:")
    for path in missing:
        st.write(f"- `{path}`")


def apply_sidebar_filters(data: pd.DataFrame) -> pd.DataFrame:
    """Apply Distributor, Province, funded-status, POI, and outlet search filters."""

    st.sidebar.header("Filters")
    filtered = data.copy()

    for column in ["Distributor_ID", "Province"]:
        if column in filtered.columns:
            options = sorted(filtered[column].dropna().astype(str).unique())
            selected = st.sidebar.multiselect(column, options=options)
            if selected:
                filtered = filtered.loc[filtered[column].astype(str).isin(selected)]

    funded_options = ["Funded", "Not funded"]
    selected_funded = st.sidebar.multiselect("Funded status", options=funded_options)
    if selected_funded:
        filtered = filtered.loc[filtered["funded_status"].isin(selected_funded)]

    if "poi_available" in filtered.columns:
        poi_options = ["POI available", "POI blind"]
        selected_poi = st.sidebar.multiselect("POI availability", options=poi_options)
        if selected_poi:
            poi_available = normalize_bool(filtered["poi_available"])
            mask = pd.Series(False, index=filtered.index)
            if "POI available" in selected_poi:
                mask = mask | poi_available
            if "POI blind" in selected_poi:
                mask = mask | ~poi_available
            filtered = filtered.loc[mask]

    search = st.sidebar.text_input("Search Outlet_ID")
    if search:
        filtered = filtered.loc[filtered["Outlet_ID"].astype(str).str.contains(search, case=False, na=False)]

    return filtered


def show_overview(data: pd.DataFrame) -> None:
    """Show portfolio-level KPI cards and summary tables."""

    st.subheader("Portfolio Overview")
    prediction = as_numeric(data, "Maximum_Monthly_Liters")
    allocation = as_numeric(data, "Trade_Spend_Allocation_LKR")
    gap = as_numeric(data, "opportunity_gap_liters")

    metric_row(
        [
            ("Outlets", f"{len(data):,}", None),
            ("Median Potential", f"{prediction.median():,.2f} L", None),
            ("Mean Potential", f"{prediction.mean():,.2f} L", None),
            ("Total Allocation", f"LKR {allocation.sum():,.0f}", None),
        ]
    )
    metric_row(
        [
            ("Funded Outlets", f"{int(allocation.gt(0).sum()):,}", None),
            ("Median Gap", f"{gap.median():,.2f} L", None),
            ("Max Potential", f"{prediction.max():,.2f} L", None),
            ("Budget Remaining", f"LKR {max(0.0, 5_000_000 - allocation.sum()):,.0f}", None),
        ]
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Prediction Distribution**")
        summary = distribution_table(prediction, "Maximum_Monthly_Liters")
        st.dataframe(summary, width="stretch", hide_index=True)
    with right:
        st.markdown("**Budget Distribution**")
        funded = allocation.loc[allocation > 0]
        summary = distribution_table(funded, "Trade_Spend_Allocation_LKR")
        st.dataframe(summary, width="stretch", hide_index=True)


def show_outlet_explorer(data: pd.DataFrame) -> None:
    """Show outlet-level prediction and feature table."""

    st.subheader("Outlet Explorer")
    preferred = [
        "Outlet_ID",
        "Maximum_Monthly_Liters",
        "historical_baseline_liters",
        "opportunity_gap_liters",
        "Trade_Spend_Allocation_LKR",
        "funded_status",
        "Distributor_ID",
        "Province",
        "Outlet_Size",
        "Cooler_Count",
        "poi_available",
        "demand_driver_score_1000m",
        "overall_spatial_gravity_score",
        "commercial_decay_score",
        "competitor_density_score",
        "market_saturation_index",
    ]
    show_table(data, preferred)


def show_budget_allocation(data: pd.DataFrame) -> None:
    """Show budget allocation diagnostics and funded outlet table."""

    st.subheader("Budget Allocation")
    allocation = as_numeric(data, "Trade_Spend_Allocation_LKR")
    funded = data.loc[allocation > 0].copy()

    metric_row(
        [
            ("Outlets Funded", f"{len(funded):,}", None),
            ("Total Allocated", f"LKR {allocation.sum():,.0f}", None),
            ("Median Allocation", f"LKR {as_numeric(funded, 'Trade_Spend_Allocation_LKR').median():,.0f}", None),
            ("Max Allocation", f"LKR {allocation.max():,.0f}", None),
        ]
    )

    preferred = [
        "Outlet_ID",
        "Trade_Spend_Allocation_LKR",
        "Maximum_Monthly_Liters",
        "opportunity_gap_liters",
        "Distributor_ID",
        "Province",
        "demand_driver_score_1000m",
        "competitor_density_score",
        "market_saturation_index",
    ]
    show_table(funded.sort_values("Trade_Spend_Allocation_LKR", ascending=False), preferred)


def show_outlet_drilldown(data: pd.DataFrame) -> None:
    """Show selected outlet facts and deterministic or optional LLM explanation."""

    st.subheader("Outlet Drilldown / XAI")
    outlet_ids = data["Outlet_ID"].dropna().astype(str).sort_values().tolist()
    if not outlet_ids:
        st.info("No outlets match the current filters.")
        return

    selected_id = st.selectbox("Select Outlet_ID", options=outlet_ids)
    row = data.loc[data["Outlet_ID"].astype(str) == selected_id].iloc[0]
    facts = row.to_dict()

    metric_row(
        [
            ("Predicted Potential", f"{float(row['Maximum_Monthly_Liters']):,.2f} L", None),
            ("Budget Allocation", f"LKR {float(row['Trade_Spend_Allocation_LKR']):,.0f}", None),
            ("Opportunity Gap", f"{float(row['opportunity_gap_liters']):,.2f} L", None),
            ("Historical Baseline", f"{float(row['historical_baseline_liters']):,.2f} L", None),
        ]
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Outlet and Historical Facts**")
        show_fact_table(facts, ["Outlet_Size", "Cooler_Count", "Distributor_ID", "Province", "active_month_count"])
    with right:
        st.markdown("**POI, Spatial, and Competition Facts**")
        show_fact_table(
            facts,
            [
                "poi_available",
                "total_poi_1000m",
                "demand_driver_score_1000m",
                "overall_spatial_gravity_score",
                "commercial_decay_score",
                "competitor_density_score",
                "market_saturation_index",
            ],
        )

    st.markdown("**Explanation**")
    explanation = optional_llm_explanation(facts) or explain_outlet(facts)
    st.write(explanation)


def optional_llm_explanation(facts: dict[str, Any]) -> str | None:
    """Return optional Gemini explanation when explicitly enabled."""

    if not llm_enabled():
        return None
    api_key = get_secret_or_env("GEMINI_API_KEY")
    if not api_key:
        st.info("LLM explanations are enabled, but `GEMINI_API_KEY` is not configured. Using deterministic fallback.")
        return None

    try:
        import requests

        prompt = build_outlet_explanation_prompt(facts)
        model = get_secret_or_env("GEMINI_MODEL") or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        response = requests.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        candidates = payload.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = parts[0].get("text") if parts else None
        return text.strip() if text else None
    except Exception as exc:
        st.warning(f"LLM explanation failed, using deterministic fallback. Details: {exc}")
        return None


def llm_enabled() -> bool:
    """Check explicit opt-in for optional LLM explanations."""

    value = get_secret_or_env("USE_LLM_EXPLANATIONS")
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def get_secret_or_env(name: str) -> str | None:
    """Read a setting from Streamlit secrets or environment variables."""

    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    value = os.getenv(name)
    return value if value else None


def historical_baseline(data: pd.DataFrame) -> pd.Series:
    """Select the best available historical baseline for opportunity-gap display."""

    for column in ["recent_avg_monthly_volume_liters", "avg_monthly_volume_liters", "median_monthly_volume_liters"]:
        if column in data.columns:
            return as_numeric(data, column)
    if "total_volume_liters" in data.columns and "active_month_count" in data.columns:
        active_months = as_numeric(data, "active_month_count").replace(0, pd.NA)
        return (as_numeric(data, "total_volume_liters") / active_months).fillna(0.0)
    return pd.Series(0.0, index=data.index)


def metric_row(items: list[tuple[str, str, str | None]]) -> None:
    """Render a row of KPI cards."""

    columns = st.columns(len(items))
    for column, (label, value, delta) in zip(columns, items):
        column.metric(label, value, delta=delta)


def show_table(data: pd.DataFrame, preferred_columns: list[str]) -> None:
    """Render a table using only columns available in the data."""

    columns = [column for column in preferred_columns if column in data.columns]
    if not columns:
        st.info("No display columns are available for the current view.")
        return
    st.dataframe(data[columns], width="stretch", hide_index=True)


def show_fact_table(facts: dict[str, Any], columns: list[str]) -> None:
    """Show selected facts for one outlet."""

    rows = [
        {"Fact": column, "Value": format_display_value(facts.get(column))}
        for column in columns
        if column in facts
    ]
    if not rows:
        st.write("No facts available.")
        return
    st.dataframe(make_display_table(rows), width="stretch", hide_index=True)


def make_display_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build an Arrow-safe small display table.

    Streamlit serializes dataframes through Arrow. Small label/value tables can
    otherwise fail when a single display column mixes strings, floats, ints,
    booleans, and missing values.
    """

    display = pd.DataFrame(rows)
    for column in ["Metric", "Value", "Feature", "Field"]:
        if column in display.columns:
            display[column] = display[column].map(format_display_value).astype("string")
    return display


def format_display_value(value: Any) -> str:
    """Format small display-table values as strings for Arrow compatibility."""

    if value is None:
        return "Not available"
    try:
        if pd.isna(value):
            return "Not available"
    except (TypeError, ValueError):
        pass

    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{float(value):,.2f}"

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return "Not available"
    if text.lower() in {"true", "false"}:
        return "Yes" if text.lower() == "true" else "No"
    return text


def distribution_table(values: pd.Series, label: str) -> pd.DataFrame:
    """Build a compact distribution table."""

    numeric_values = pd.to_numeric(values, errors="coerce").dropna()
    if numeric_values.empty:
        return pd.DataFrame({"Metric": ["Rows"], label: [0]})
    return pd.DataFrame(
        {
            "Metric": ["Rows", "Min", "P25", "Median", "Mean", "P75", "P90", "Max"],
            label: [
                len(numeric_values),
                numeric_values.min(),
                numeric_values.quantile(0.25),
                numeric_values.median(),
                numeric_values.mean(),
                numeric_values.quantile(0.75),
                numeric_values.quantile(0.90),
                numeric_values.max(),
            ],
        }
    )


def as_numeric(data: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric Series, using zeros when a column is absent."""

    if column not in data.columns:
        return pd.Series(0.0, index=data.index)
    return pd.to_numeric(data[column], errors="coerce").fillna(0.0)


def normalize_bool(values: pd.Series) -> pd.Series:
    """Normalize common truthy values to bool."""

    if values.dtype == bool:
        return values.fillna(False)
    return values.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y", "t"})


if __name__ == "__main__":
    main()
