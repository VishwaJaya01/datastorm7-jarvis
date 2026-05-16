"""Peer benchmark uplift logic for explainable outlet potential estimates."""

from __future__ import annotations

import numpy as np
import pandas as pd


OUTLET_COLUMNS = {"Outlet_ID", "Outlet_Type", "Outlet_Size", "Cooler_Count", "coord_status", "has_valid_coord"}


def build_peer_benchmarks(
    outlet_master: pd.DataFrame,
    baseline: pd.DataFrame,
    min_group_size: int = 30,
) -> pd.DataFrame:
    """Estimate peer benchmark potential using conservative fallback groups.

    Fallback priority:
    1. Outlet_Type + Outlet_Size
    2. Outlet_Type
    3. Global benchmark
    """

    _require_columns(outlet_master, {"Outlet_ID"}, "outlet_master")
    _require_columns(baseline, {"Outlet_ID", "baseline_potential_liters"}, "baseline")

    outlets = outlet_master.copy()
    for column in OUTLET_COLUMNS.difference(outlets.columns):
        outlets[column] = np.nan

    working = outlets.merge(
        baseline[["Outlet_ID", "baseline_potential_liters"]],
        on="Outlet_ID",
        how="left",
    )

    known = working.loc[working["baseline_potential_liters"].notna() & (working["baseline_potential_liters"] > 0)].copy()
    global_benchmark = _benchmark_value(known["baseline_potential_liters"])
    global_count = int(known["baseline_potential_liters"].notna().sum())

    type_size_stats = _group_stats(known, ["Outlet_Type", "Outlet_Size"])
    type_stats = _group_stats(known, ["Outlet_Type"])

    peer = working.merge(
        type_size_stats.add_prefix("type_size_"),
        left_on=["Outlet_Type", "Outlet_Size"],
        right_on=["type_size_Outlet_Type", "type_size_Outlet_Size"],
        how="left",
    ).merge(
        type_stats.add_prefix("type_"),
        left_on="Outlet_Type",
        right_on="type_Outlet_Type",
        how="left",
    )

    peer["peer_group_level"] = "global"
    peer["peer_group_count"] = global_count
    peer["peer_raw_benchmark_liters"] = global_benchmark

    type_mask = peer["type_count"].fillna(0).ge(min_group_size)
    peer.loc[type_mask, "peer_group_level"] = "Outlet_Type"
    peer.loc[type_mask, "peer_group_count"] = peer.loc[type_mask, "type_count"]
    peer.loc[type_mask, "peer_raw_benchmark_liters"] = peer.loc[type_mask, "type_benchmark"]

    type_size_mask = peer["type_size_count"].fillna(0).ge(min_group_size)
    peer.loc[type_size_mask, "peer_group_level"] = "Outlet_Type+Outlet_Size"
    peer.loc[type_size_mask, "peer_group_count"] = peer.loc[type_size_mask, "type_size_count"]
    peer.loc[type_size_mask, "peer_raw_benchmark_liters"] = peer.loc[type_size_mask, "type_size_benchmark"]

    peer["peer_adjustment_multiplier"] = _peer_adjustment_multiplier(peer)
    peer["peer_benchmark_potential_liters"] = (
        peer["peer_raw_benchmark_liters"].fillna(global_benchmark) * peer["peer_adjustment_multiplier"]
    )

    has_history = peer["baseline_potential_liters"].notna() & peer["baseline_potential_liters"].gt(0)
    peer.loc[has_history, "peer_benchmark_potential_liters"] = np.minimum(
        peer.loc[has_history, "peer_benchmark_potential_liters"],
        peer.loc[has_history, "baseline_potential_liters"] * 1.15,
    )
    peer.loc[~has_history, "peer_benchmark_potential_liters"] *= 0.90

    return peer[
        [
            "Outlet_ID",
            "peer_group_level",
            "peer_group_count",
            "peer_raw_benchmark_liters",
            "peer_adjustment_multiplier",
            "peer_benchmark_potential_liters",
        ]
    ]


def _group_stats(df: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=group_columns + ["count", "p75", "p90", "benchmark"])

    grouped = (
        df.dropna(subset=group_columns)
        .groupby(group_columns)
        .agg(
            count=("baseline_potential_liters", "size"),
            p75=("baseline_potential_liters", lambda value: value.quantile(0.75)),
            p90=("baseline_potential_liters", lambda value: value.quantile(0.90)),
        )
        .reset_index()
    )
    grouped["benchmark"] = grouped["p75"] + 0.15 * (grouped["p90"] - grouped["p75"])
    return grouped


def _benchmark_value(values: pd.Series) -> float:
    positive = pd.to_numeric(values, errors="coerce").dropna()
    positive = positive.loc[positive > 0]
    if positive.empty:
        return 1.0
    p75 = positive.quantile(0.75)
    p90 = positive.quantile(0.90)
    return float(p75 + 0.15 * (p90 - p75))


def _peer_adjustment_multiplier(peer: pd.DataFrame) -> pd.Series:
    multiplier = pd.Series(1.0, index=peer.index)

    cooler = pd.to_numeric(peer["Cooler_Count"], errors="coerce")
    median_cooler = cooler.median()
    if pd.notna(median_cooler):
        multiplier = multiplier.where(cooler.fillna(median_cooler) <= median_cooler, multiplier * 1.03)
        multiplier = multiplier.where(cooler.fillna(median_cooler) >= median_cooler, multiplier * 0.98)

    coord_status = peer["coord_status"].astype("string").str.lower()
    has_valid_coord = peer["has_valid_coord"].astype("string").str.lower().isin({"true", "1", "yes"})
    poi_blind = coord_status.isin({"missing", "quarantined"}) | ~has_valid_coord
    multiplier = multiplier.where(~poi_blind, multiplier * 0.98)
    return multiplier.clip(lower=0.90, upper=1.06)


def _require_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {sorted(missing)}")
