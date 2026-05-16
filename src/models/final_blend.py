"""Final blending logic for the first Member 3 submission pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PREDICTION_COLUMN = "Maximum_Monthly_Liters"


def load_gold_features(path: Path = Path("data/gold/master_features.csv")) -> pd.DataFrame | None:
    """Load optional Gold features if Member 2's file exists."""

    if not path.exists():
        return None

    gold = pd.read_csv(path)
    if "Outlet_ID" not in gold.columns:
        raise ValueError(f"{path} exists but does not contain Outlet_ID")
    return gold


def build_final_predictions(
    outlet_master: pd.DataFrame,
    baseline: pd.DataFrame,
    seasonality_adjusted: pd.DataFrame,
    peer_benchmark: pd.DataFrame,
    gold_features: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Blend baseline, seasonality, peer benchmark, and optional Gold signals."""

    if "Outlet_ID" not in outlet_master.columns:
        raise ValueError("outlet_master must contain Outlet_ID")

    frame = outlet_master[["Outlet_ID"]].copy()
    frame = frame.merge(_dedupe(baseline), on="Outlet_ID", how="left")
    frame = frame.merge(
        _dedupe(
            seasonality_adjusted[
                [
                    "Outlet_ID",
                    "Distributor_ID",
                    "january_seasonality_multiplier",
                    "seasonality_adjusted_potential_liters",
                ]
            ]
        ),
        on="Outlet_ID",
        how="left",
    )
    frame = frame.merge(_dedupe(peer_benchmark), on="Outlet_ID", how="left")

    fallback = _positive_median(frame["peer_benchmark_potential_liters"])
    frame["baseline_potential_liters"] = frame["baseline_potential_liters"].fillna(fallback)
    frame["january_seasonality_multiplier"] = frame["january_seasonality_multiplier"].fillna(1.00)
    frame["seasonality_adjusted_potential_liters"] = frame["seasonality_adjusted_potential_liters"].fillna(
        frame["baseline_potential_liters"] * frame["january_seasonality_multiplier"]
    )
    frame["peer_benchmark_potential_liters"] = frame["peer_benchmark_potential_liters"].fillna(
        frame["baseline_potential_liters"]
    )

    frame["blended_potential_liters"] = (
        0.55 * frame["baseline_potential_liters"]
        + 0.30 * frame["seasonality_adjusted_potential_liters"]
        + 0.15 * frame["peer_benchmark_potential_liters"]
    )

    if gold_features is not None:
        gold_adjustment = build_gold_adjustment(gold_features)
        frame = frame.merge(gold_adjustment, on="Outlet_ID", how="left")
        frame["gold_feature_multiplier"] = frame["gold_feature_multiplier"].fillna(1.00)
        frame["blended_potential_liters"] *= frame["gold_feature_multiplier"]
    else:
        frame["gold_feature_multiplier"] = 1.00
        frame["gold_numeric_feature_count"] = 0

    frame[PREDICTION_COLUMN] = apply_sanity_rules(frame["blended_potential_liters"])
    return frame[["Outlet_ID", PREDICTION_COLUMN]]


def build_gold_adjustment(gold_features: pd.DataFrame) -> pd.DataFrame:
    """Create a conservative optional multiplier from numeric Gold columns.

    The code intentionally does not assume POI column names. Numeric columns are
    converted to percentile ranks and averaged into a small 0.97 to 1.03
    multiplier, so Gold can help later without overpowering Silver evidence.
    """

    if "Outlet_ID" not in gold_features.columns:
        raise ValueError("gold_features must contain Outlet_ID")

    excluded = {"Outlet_ID", "Maximum_Monthly_Liters", "target", "prediction"}
    candidate_columns = [column for column in gold_features.columns if column not in excluded]
    converted = {
        column: pd.to_numeric(gold_features[column], errors="coerce")
        for column in candidate_columns
    }
    numeric_columns = [column for column, values in converted.items() if values.notna().any()]

    adjustment = gold_features[["Outlet_ID"]].drop_duplicates().copy()
    adjustment["gold_numeric_feature_count"] = len(numeric_columns)
    if not numeric_columns:
        adjustment["gold_feature_multiplier"] = 1.00
        return adjustment

    ranked = gold_features[["Outlet_ID"]].copy()
    for column in numeric_columns:
        ranked[column] = converted[column].rank(pct=True).fillna(0.5)

    ranked["gold_signal"] = ranked[numeric_columns].mean(axis=1).clip(0, 1)
    ranked["gold_feature_multiplier"] = 0.97 + 0.06 * ranked["gold_signal"]
    return (
        ranked.groupby("Outlet_ID", as_index=False)
        .agg(
            gold_feature_multiplier=("gold_feature_multiplier", "mean"),
            gold_numeric_feature_count=("gold_signal", "size"),
        )
    )


def apply_sanity_rules(values: pd.Series) -> pd.Series:
    """Remove NaN/negative values and cap extreme distribution tails."""

    prediction = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    positive = prediction.dropna()
    positive = positive.loc[positive > 0]

    if positive.empty:
        floor = 1.0
        cap = 1.0
    else:
        floor = max(1.0, float(positive.quantile(0.01) * 0.50))
        cap = max(float(positive.quantile(0.995)), floor)

    prediction = prediction.fillna(floor).clip(lower=floor, upper=cap)
    return prediction


def _dedupe(df: pd.DataFrame) -> pd.DataFrame:
    if "Outlet_ID" not in df.columns:
        raise ValueError("input frame must contain Outlet_ID")
    return df.drop_duplicates("Outlet_ID")


def _positive_median(values: pd.Series) -> float:
    positive = pd.to_numeric(values, errors="coerce").dropna()
    positive = positive.loc[positive > 0]
    if positive.empty:
        return 1.0
    return float(positive.median())
