"""Competitor density and market saturation features for Round 2.

Uses a BallTree with haversine distance on Silver outlet coordinates to
efficiently compute pairwise spatial density features.  Only outlets with
usable coordinates (``coord_status`` in {valid, corrected}) are included.

Features produced per outlet:
    nearby_outlets_250m   – count of other outlets within 250 m
    nearby_outlets_500m   – count of other outlets within 500 m
    nearby_outlets_1000m  – count of other outlets within 1000 m
    competitor_density_score   – gravity-weighted density Σ 1/(1+d_km) for
                                 all neighbours within 1 000 m
    market_saturation_index    – percentile rank of competitor_density_score
                                 across all outlets (0.0 – 1.0)
    isolated_outlet_flag       – True when nearby_outlets_500m == 0
    high_competition_cluster_flag – True when nearby_outlets_500m ≥ 90th pctl

Run standalone:
    python -m src.spatial.competitor_density
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

# ---------------------------------------------------------------------------
# Paths – use cleaned Silver locations (only valid/corrected coordinates).
# ---------------------------------------------------------------------------
LOCATIONS_PATH = Path("data/silver/clean_outlet_locations.csv")
OUTPUT_PATH = Path("data/silver/competitor_density_features.csv")
REPORT_PATH = Path("reports/eda/competitor_density_summary.json")

# Earth radius in kilometres (for haversine → km conversion).
EARTH_RADIUS_KM = 6_371.0

# Neighbourhood radii in metres.
RADII_M = (250, 500, 1_000)

# Gravity‑weighted density cap radius in metres.
GRAVITY_RADIUS_M = 1_000


def compute_competitor_density(
    locations_path: Path = LOCATIONS_PATH,
    output_path: Path = OUTPUT_PATH,
    report_path: Path = REPORT_PATH,
) -> pd.DataFrame:
    """Compute competitor density features for every outlet with usable coords.

    Parameters
    ----------
    locations_path:
        CSV with at least ``Outlet_ID``, ``Latitude``, ``Longitude``.
    output_path:
        Where to write the per‑outlet feature CSV.
    report_path:
        Where to write a JSON summary for the forensics report.

    Returns
    -------
    pd.DataFrame
        One row per outlet with the 7 spatial density features.
    """

    locations = pd.read_csv(locations_path)
    _validate_input(locations)

    # Convert degrees → radians for haversine BallTree.
    coords_rad = np.radians(locations[["Latitude", "Longitude"]].values)
    tree = BallTree(coords_rad, metric="haversine")

    # ------------------------------------------------------------------
    # 1) Radius‑based neighbour counts at 250 m, 500 m, 1 000 m.
    # ------------------------------------------------------------------
    nearby = {}
    for radius_m in RADII_M:
        radius_rad = radius_m / (EARTH_RADIUS_KM * 1_000)  # m → radians
        counts = tree.query_radius(coords_rad, r=radius_rad, count_only=True)
        # Subtract 1 because each point counts itself.
        nearby[f"nearby_outlets_{radius_m}m"] = counts - 1

    # ------------------------------------------------------------------
    # 2) Gravity‑weighted competitor density score.
    #    score = Σ 1 / (1 + d_km)  for all neighbours within 1 000 m.
    # ------------------------------------------------------------------
    gravity_radius_rad = GRAVITY_RADIUS_M / (EARTH_RADIUS_KM * 1_000)
    indices, distances = tree.query_radius(
        coords_rad, r=gravity_radius_rad, return_distance=True
    )

    density_scores = np.zeros(len(locations))
    for i, (idx_arr, dist_arr) in enumerate(zip(indices, distances)):
        # Convert haversine radians → km.
        dist_km = dist_arr * EARTH_RADIUS_KM
        # Exclude self (distance ≈ 0).
        mask = dist_km > 1e-9
        if mask.any():
            density_scores[i] = np.sum(1.0 / (1.0 + dist_km[mask]))

    # ------------------------------------------------------------------
    # 3) Derived features.
    # ------------------------------------------------------------------
    nearby_500 = nearby["nearby_outlets_500m"]
    p90_500 = np.percentile(nearby_500, 90) if len(nearby_500) > 0 else 0

    features = pd.DataFrame(
        {
            "Outlet_ID": locations["Outlet_ID"].values,
            "nearby_outlets_250m": nearby["nearby_outlets_250m"],
            "nearby_outlets_500m": nearby_500,
            "nearby_outlets_1000m": nearby["nearby_outlets_1000m"],
            "competitor_density_score": np.round(density_scores, 6),
            "market_saturation_index": _percentile_rank(density_scores),
            "isolated_outlet_flag": nearby_500 == 0,
            "high_competition_cluster_flag": nearby_500 >= p90_500,
        }
    )

    # ------------------------------------------------------------------
    # 4) Write outputs.
    # ------------------------------------------------------------------
    output_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output_path, index=False)

    summary = _build_summary(features, p90_500)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    _print_summary(features, summary, output_path)
    return features


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_input(df: pd.DataFrame) -> None:
    """Fail fast if input is missing required columns or has NaN coords."""

    required = {"Outlet_ID", "Latitude", "Longitude"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input is missing required columns: {sorted(missing)}")
    if df["Outlet_ID"].isna().any():
        raise ValueError("Input contains null Outlet_ID values")
    if df[["Latitude", "Longitude"]].isna().any().any():
        raise ValueError(
            "Input contains null coordinates — use clean_outlet_locations.csv "
            "which only includes outlets with usable coordinates"
        )
    if df["Outlet_ID"].duplicated().any():
        raise ValueError("Input contains duplicate Outlet_ID values")


def _percentile_rank(values: np.ndarray) -> np.ndarray:
    """Compute percentile ranks (0.0–1.0) for an array of values."""

    n = len(values)
    if n == 0:
        return values.copy()
    order = values.argsort().argsort()  # double argsort → ranks (0‑based)
    return (order + 1) / n


def _build_summary(features: pd.DataFrame, p90_threshold: float) -> dict:
    """Build a JSON‑serialisable summary of the density features."""

    return {
        "total_outlets": int(len(features)),
        "nearby_outlets_250m": {
            "min": int(features["nearby_outlets_250m"].min()),
            "median": float(features["nearby_outlets_250m"].median()),
            "max": int(features["nearby_outlets_250m"].max()),
            "mean": round(float(features["nearby_outlets_250m"].mean()), 2),
        },
        "nearby_outlets_500m": {
            "min": int(features["nearby_outlets_500m"].min()),
            "median": float(features["nearby_outlets_500m"].median()),
            "max": int(features["nearby_outlets_500m"].max()),
            "mean": round(float(features["nearby_outlets_500m"].mean()), 2),
            "p90_threshold": float(p90_threshold),
        },
        "nearby_outlets_1000m": {
            "min": int(features["nearby_outlets_1000m"].min()),
            "median": float(features["nearby_outlets_1000m"].median()),
            "max": int(features["nearby_outlets_1000m"].max()),
            "mean": round(float(features["nearby_outlets_1000m"].mean()), 2),
        },
        "competitor_density_score": {
            "min": round(float(features["competitor_density_score"].min()), 4),
            "median": round(float(features["competitor_density_score"].median()), 4),
            "max": round(float(features["competitor_density_score"].max()), 4),
            "mean": round(float(features["competitor_density_score"].mean()), 4),
        },
        "isolated_outlets": int(features["isolated_outlet_flag"].sum()),
        "high_competition_outlets": int(features["high_competition_cluster_flag"].sum()),
    }


def _print_summary(
    features: pd.DataFrame, summary: dict, output_path: Path
) -> None:
    """Print a human‑readable summary after writing outputs."""

    print(f"\n{'='*60}")
    print("Competitor Density Feature Summary")
    print(f"{'='*60}")
    print(f"Output path       : {output_path}")
    print(f"Total outlets     : {summary['total_outlets']}")
    print(f"Isolated outlets  : {summary['isolated_outlets']} "
          f"({summary['isolated_outlets']/summary['total_outlets']*100:.1f}%)")
    print(f"High competition  : {summary['high_competition_outlets']} "
          f"({summary['high_competition_outlets']/summary['total_outlets']*100:.1f}%)")
    print(f"\nNearby outlets (median): "
          f"250m={summary['nearby_outlets_250m']['median']:.0f}, "
          f"500m={summary['nearby_outlets_500m']['median']:.0f}, "
          f"1000m={summary['nearby_outlets_1000m']['median']:.0f}")
    print(f"Density score (median): "
          f"{summary['competitor_density_score']['median']:.4f}")
    print(f"{'='*60}\n")


def main() -> None:
    compute_competitor_density()


if __name__ == "__main__":
    main()
