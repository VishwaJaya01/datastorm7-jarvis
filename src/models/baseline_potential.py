"""Explainable baseline latent-potential estimator for Member 3.

The baseline treats observed monthly sales as a censored signal:

Observed Sales = min(True Demand Potential, Constraints)

Instead of predicting an average historical month, it uses high-but-still-
credible historical outlet months as a first estimate of hidden monthly
potential.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


TRANSACTION_COLUMNS = {
    "Outlet_ID",
    "Year",
    "Month",
    "Distributor_ID",
    "SKU_ID",
    "Volume_Liters",
    "Total_Bill_Value",
}


def load_transactions(path: Path = Path("data/silver/transactions_history_final.csv")) -> pd.DataFrame:
    """Load Silver transactions with defensive column validation."""

    if not path.exists():
        raise FileNotFoundError(
            f"Silver transaction file not found: {path}. "
            "Run the Data Architect Silver pipeline before modeling."
        )

    transactions = pd.read_csv(path)
    missing = TRANSACTION_COLUMNS.difference(transactions.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return transactions


def build_monthly_outlet_volume(transactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate SKU/distributor transaction rows to outlet-month volume."""

    _require_columns(transactions, TRANSACTION_COLUMNS, "transactions")
    working = transactions.copy()
    working["Year"] = pd.to_numeric(working["Year"], errors="coerce")
    working["Month"] = pd.to_numeric(working["Month"], errors="coerce")
    working["Volume_Liters"] = pd.to_numeric(working["Volume_Liters"], errors="coerce").fillna(0.0)
    working["Total_Bill_Value"] = pd.to_numeric(working["Total_Bill_Value"], errors="coerce")

    return (
        working.groupby(["Outlet_ID", "Year", "Month"], as_index=False)
        .agg(
            monthly_volume_liters=("Volume_Liters", "sum"),
            monthly_bill_value=("Total_Bill_Value", "sum"),
            monthly_transaction_count=("SKU_ID", "size"),
        )
        .sort_values(["Outlet_ID", "Year", "Month"])
    )


def build_baseline_potential(transactions: pd.DataFrame, recent_months: int = 3) -> pd.DataFrame:
    """Build outlet-level historical stats and conservative baseline potential.

    Formula:
        max(
            recent average monthly volume,
            p75 monthly volume,
            0.85 * p90 monthly volume,
            0.70 * max monthly volume
        )

    A small activity multiplier is then applied. Outlets with longer histories
    get slightly more confidence; sparse outlets are kept conservative.
    """

    _require_columns(transactions, TRANSACTION_COLUMNS, "transactions")
    monthly = build_monthly_outlet_volume(transactions)

    outlet_stats = (
        monthly.groupby("Outlet_ID")
        .agg(
            avg_monthly_volume_liters=("monthly_volume_liters", "mean"),
            median_monthly_volume_liters=("monthly_volume_liters", "median"),
            max_monthly_volume_liters=("monthly_volume_liters", "max"),
            p75_monthly_volume_liters=("monthly_volume_liters", lambda value: value.quantile(0.75)),
            p90_monthly_volume_liters=("monthly_volume_liters", lambda value: value.quantile(0.90)),
            active_month_count=("monthly_volume_liters", "size"),
            total_volume_liters=("monthly_volume_liters", "sum"),
        )
        .reset_index()
    )

    transaction_stats = (
        transactions.assign(Total_Bill_Value=pd.to_numeric(transactions["Total_Bill_Value"], errors="coerce"))
        .groupby("Outlet_ID")
        .agg(
            transaction_count=("SKU_ID", "size"),
            avg_bill_value=("Total_Bill_Value", "mean"),
        )
        .reset_index()
    )

    recent_avg = _recent_average(monthly, recent_months=recent_months)
    baseline = outlet_stats.merge(transaction_stats, on="Outlet_ID", how="left").merge(
        recent_avg,
        on="Outlet_ID",
        how="left",
    )

    candidate_columns = [
        "recent_avg_monthly_volume_liters",
        "p75_monthly_volume_liters",
        "p90_conservative_volume_liters",
        "max_conservative_volume_liters",
    ]
    baseline["p90_conservative_volume_liters"] = 0.85 * baseline["p90_monthly_volume_liters"]
    baseline["max_conservative_volume_liters"] = 0.70 * baseline["max_monthly_volume_liters"]
    baseline["baseline_raw_potential_liters"] = baseline[candidate_columns].max(axis=1)
    baseline["activity_uplift"] = baseline["active_month_count"].map(_activity_uplift)
    baseline["baseline_potential_liters"] = (
        baseline["baseline_raw_potential_liters"] * baseline["activity_uplift"]
    ).clip(lower=0)

    return baseline[
        [
            "Outlet_ID",
            "avg_monthly_volume_liters",
            "median_monthly_volume_liters",
            "max_monthly_volume_liters",
            "p75_monthly_volume_liters",
            "p90_monthly_volume_liters",
            "recent_avg_monthly_volume_liters",
            "active_month_count",
            "transaction_count",
            "total_volume_liters",
            "avg_bill_value",
            "activity_uplift",
            "baseline_potential_liters",
        ]
    ]


def _recent_average(monthly: pd.DataFrame, recent_months: int) -> pd.DataFrame:
    """Average the most recent active months per outlet."""

    monthly = monthly.copy()
    monthly["period"] = monthly["Year"].astype(int) * 100 + monthly["Month"].astype(int)
    recent = (
        monthly.sort_values(["Outlet_ID", "period"], ascending=[True, False])
        .groupby("Outlet_ID", group_keys=False)
        .head(recent_months)
    )
    return (
        recent.groupby("Outlet_ID", as_index=False)
        .agg(recent_avg_monthly_volume_liters=("monthly_volume_liters", "mean"))
    )


def _activity_uplift(active_month_count: float) -> float:
    """Small confidence uplift based on historical coverage."""

    if pd.isna(active_month_count):
        return 1.0
    if active_month_count >= 24:
        return 1.04
    if active_month_count >= 12:
        return 1.02
    if active_month_count >= 6:
        return 1.00
    return 0.98


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {sorted(missing)}")
