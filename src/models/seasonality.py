"""January seasonality helpers for the latent-potential model."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


SEASONALITY_MULTIPLIERS = {
    "Favorable": 1.08,
    "Moderate": 1.00,
    "Un-Favorable": 0.92,
}


def load_seasonality(path: Path = Path("data/silver/distributor_seasonality_details.csv")) -> pd.DataFrame:
    """Load Silver distributor seasonality data."""

    if not path.exists():
        raise FileNotFoundError(
            f"Silver seasonality file not found: {path}. "
            "Use 1.00 multipliers only if this file is intentionally unavailable."
        )

    seasonality = pd.read_csv(path)
    required = {"Distributor_ID", "Year", "Month", "Seasonality_Index"}
    missing = required.difference(seasonality.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return seasonality


def infer_january_multipliers(
    seasonality: pd.DataFrame,
    multipliers: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Infer January 2026 multipliers from historical January labels."""

    multipliers = multipliers or SEASONALITY_MULTIPLIERS
    required = {"Distributor_ID", "Month", "Seasonality_Index"}
    missing = required.difference(seasonality.columns)
    if missing:
        raise ValueError(f"seasonality is missing required columns: {sorted(missing)}")

    january = seasonality.loc[pd.to_numeric(seasonality["Month"], errors="coerce").eq(1)].copy()
    if january.empty:
        return pd.DataFrame(columns=["Distributor_ID", "january_seasonality_multiplier"])

    january["january_seasonality_multiplier"] = january["Seasonality_Index"].map(multipliers).fillna(1.00)
    return (
        january.groupby("Distributor_ID", as_index=False)
        .agg(january_seasonality_multiplier=("january_seasonality_multiplier", "mean"))
    )


def infer_primary_distributor(transactions: pd.DataFrame) -> pd.DataFrame:
    """Choose the distributor with the highest historical volume per outlet."""

    required = {"Outlet_ID", "Distributor_ID", "Volume_Liters"}
    missing = required.difference(transactions.columns)
    if missing:
        raise ValueError(f"transactions is missing required columns: {sorted(missing)}")

    volume = transactions.copy()
    volume["Volume_Liters"] = pd.to_numeric(volume["Volume_Liters"], errors="coerce").fillna(0.0)
    ranked = (
        volume.groupby(["Outlet_ID", "Distributor_ID"], as_index=False)
        .agg(distributor_volume_liters=("Volume_Liters", "sum"))
        .sort_values(["Outlet_ID", "distributor_volume_liters"], ascending=[True, False])
    )
    return ranked.drop_duplicates("Outlet_ID")[["Outlet_ID", "Distributor_ID"]]


def apply_january_seasonality(
    potential: pd.DataFrame,
    transactions: pd.DataFrame,
    seasonality: pd.DataFrame | None,
    potential_column: str = "baseline_potential_liters",
) -> pd.DataFrame:
    """Add January multiplier and seasonality-adjusted potential columns."""

    if "Outlet_ID" not in potential.columns:
        raise ValueError("potential must contain Outlet_ID")
    if potential_column not in potential.columns:
        raise ValueError(f"potential must contain {potential_column}")

    adjusted = potential.copy()
    primary = infer_primary_distributor(transactions)
    adjusted = adjusted.merge(primary, on="Outlet_ID", how="left")

    if seasonality is None or seasonality.empty:
        adjusted["january_seasonality_multiplier"] = 1.00
    else:
        january_multipliers = infer_january_multipliers(seasonality)
        adjusted = adjusted.merge(january_multipliers, on="Distributor_ID", how="left")
        adjusted["january_seasonality_multiplier"] = adjusted["january_seasonality_multiplier"].fillna(1.00)

    adjusted["seasonality_adjusted_potential_liters"] = (
        adjusted[potential_column].fillna(0.0) * adjusted["january_seasonality_multiplier"]
    )
    return adjusted
