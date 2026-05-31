"""Build the reproducible Gold master feature table.

The Gold table starts from all Silver outlet master rows, then left-joins
optional Silver base features and POI v2 features. Outlets without usable
coordinates remain in the table as POI-blind rows with zero-filled POI counts.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


OUTLET_MASTER_PATH = Path("data/silver/outlet_master.csv")
OUTLET_BASE_FEATURES_PATH = Path("data/silver/outlet_base_features.csv")
POI_FEATURES_PATH = Path("data/external/outlet_poi_features_v2.csv")
COMPETITOR_DENSITY_PATH = Path("data/silver/competitor_density_features.csv")
OUTPUT_PATH = Path("data/gold/master_features.csv")

POI_COUNT_PREFIXES = (
    "schools",
    "bus_stops",
    "hospitals",
    "restaurants",
    "supermarkets",
    "markets",
    "banks_atms",
    "fuel_stations",
    "religious_places",
    "tourism",
    "railway_stations",
)
POI_RADII = (500, 1000)
EXPECTED_POI_COUNT_COLUMNS = [f"{prefix}_{radius}m" for prefix in POI_COUNT_PREFIXES for radius in POI_RADII]
POI_TOTAL_COLUMNS = ["total_poi_500m", "total_poi_1000m"]
DEMAND_SCORE_COLUMNS = ["demand_driver_score_500m", "demand_driver_score_1000m"]
DERIVED_COLUMNS = [
    "log_total_poi_500m",
    "log_total_poi_1000m",
    "log_demand_driver_score_500m",
    "log_demand_driver_score_1000m",
    "poi_density_rank_500m",
    "poi_density_rank_1000m",
    "demand_score_rank_500m",
    "demand_score_rank_1000m",
    "catchment_class",
]

# Competitor density feature columns produced by src.spatial.competitor_density.
COMPETITOR_DENSITY_COLUMNS = [
    "nearby_outlets_250m",
    "nearby_outlets_500m",
    "nearby_outlets_1000m",
    "competitor_density_score",
    "market_saturation_index",
    "isolated_outlet_flag",
    "high_competition_cluster_flag",
]


def build_master_features(
    outlet_master_path: Path = OUTLET_MASTER_PATH,
    outlet_base_features_path: Path = OUTLET_BASE_FEATURES_PATH,
    poi_features_path: Path = POI_FEATURES_PATH,
    competitor_density_path: Path = COMPETITOR_DENSITY_PATH,
    output_path: Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Build and save the Gold master feature table."""

    outlet_master = read_required_csv(outlet_master_path, required_columns={"Outlet_ID"})
    master = dedupe_by_outlet(outlet_master, source_name=str(outlet_master_path))

    if outlet_base_features_path.exists():
        base_features = read_required_csv(outlet_base_features_path, required_columns={"Outlet_ID"})
        master = left_join_new_columns(master, dedupe_by_outlet(base_features, str(outlet_base_features_path)))
    else:
        print(f"Optional base feature file not found; continuing without it: {outlet_base_features_path}")

    poi_features = read_required_csv(poi_features_path, required_columns={"Outlet_ID"})
    master = left_join_new_columns(master, dedupe_by_outlet(poi_features, str(poi_features_path)))

    # Round 2: competitor density features.
    if competitor_density_path.exists():
        density_features = pd.read_csv(competitor_density_path)
        density_features = dedupe_by_outlet(density_features, str(competitor_density_path))
        master = left_join_new_columns(master, density_features)
        print(f"Joined competitor density features from {competitor_density_path} "
              f"({len(density_features)} outlets)")
    else:
        print(f"Optional competitor density file not found; continuing without it: {competitor_density_path}")

    master = normalize_poi_features(master)
    validate_master_features(master, expected_rows=len(outlet_master))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(output_path, index=False)
    print_summary(master, output_path)
    return master


def read_required_csv(path: Path, required_columns: set[str]) -> pd.DataFrame:
    """Read a CSV and fail clearly when required columns are absent."""

    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")

    df = pd.read_csv(path)
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return df


def dedupe_by_outlet(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """Ensure one row per outlet for feature joins."""

    if df["Outlet_ID"].isna().any():
        raise ValueError(f"{source_name} contains missing Outlet_ID values")
    duplicate_count = int(df["Outlet_ID"].duplicated().sum())
    if duplicate_count:
        print(f"{source_name}: dropping {duplicate_count} duplicate Outlet_ID rows, keeping first occurrence.")
    return df.drop_duplicates("Outlet_ID", keep="first").copy()


def left_join_new_columns(master: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    """Left join only columns not already present in master."""

    new_columns = ["Outlet_ID"] + [column for column in features.columns if column != "Outlet_ID" and column not in master]
    return master.merge(features[new_columns], on="Outlet_ID", how="left")


def normalize_poi_features(master: pd.DataFrame) -> pd.DataFrame:
    """Fill missing POI values, normalize availability, and add derived features."""

    normalized = master.copy()
    for column in EXPECTED_POI_COUNT_COLUMNS + POI_TOTAL_COLUMNS + DEMAND_SCORE_COLUMNS:
        if column not in normalized:
            normalized[column] = 0.0
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce").fillna(0.0)

    normalized["poi_available"] = normalize_boolean_series(normalized.get("poi_available"), index=normalized.index)
    normalized["poi_available"] = normalized["poi_available"] | normalized["total_poi_1000m"].gt(0)
    coord_status = normalized.get("coord_status", pd.Series("", index=normalized.index)).astype("string").str.lower()
    poi_blind_mask = coord_status.isin({"quarantined", "missing"})
    normalized.loc[poi_blind_mask, "poi_available"] = False
    normalized.loc[normalized["total_poi_1000m"].le(0), "poi_available"] = False

    normalized["log_total_poi_500m"] = np.log1p(normalized["total_poi_500m"].clip(lower=0))
    normalized["log_total_poi_1000m"] = np.log1p(normalized["total_poi_1000m"].clip(lower=0))
    normalized["log_demand_driver_score_500m"] = np.log1p(normalized["demand_driver_score_500m"].clip(lower=0))
    normalized["log_demand_driver_score_1000m"] = np.log1p(normalized["demand_driver_score_1000m"].clip(lower=0))

    normalized["poi_density_rank_500m"] = positive_percentile_rank(normalized["total_poi_500m"])
    normalized["poi_density_rank_1000m"] = positive_percentile_rank(normalized["total_poi_1000m"])
    normalized["demand_score_rank_500m"] = positive_percentile_rank(normalized["demand_driver_score_500m"])
    normalized["demand_score_rank_1000m"] = positive_percentile_rank(normalized["demand_driver_score_1000m"])
    normalized["catchment_class"] = build_catchment_class(normalized)

    # Normalize competitor density features (zero-fill POI-blind outlets).
    for col in ["nearby_outlets_250m", "nearby_outlets_500m", "nearby_outlets_1000m"]:
        if col not in normalized:
            normalized[col] = 0
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce").fillna(0).astype(int)

    if "competitor_density_score" not in normalized:
        normalized["competitor_density_score"] = 0.0
    normalized["competitor_density_score"] = pd.to_numeric(
        normalized["competitor_density_score"], errors="coerce"
    ).fillna(0.0)

    if "market_saturation_index" not in normalized:
        normalized["market_saturation_index"] = 0.0
    normalized["market_saturation_index"] = pd.to_numeric(
        normalized["market_saturation_index"], errors="coerce"
    ).fillna(0.0)

    for flag_col in ["isolated_outlet_flag", "high_competition_cluster_flag"]:
        if flag_col not in normalized:
            normalized[flag_col] = False
        normalized[flag_col] = normalize_boolean_series(normalized[flag_col], index=normalized.index)
    # POI-blind outlets default to isolated=True, high_competition=False.
    normalized.loc[poi_blind_mask, "isolated_outlet_flag"] = True
    normalized.loc[poi_blind_mask, "high_competition_cluster_flag"] = False

    return normalized


def normalize_boolean_series(series: pd.Series | None, index: pd.Index) -> pd.Series:
    """Convert common truthy/falsy values to a clean bool series."""

    if series is None:
        return pd.Series(False, index=index, dtype=bool)

    truthy = {"true", "1", "yes", "y", "t"}
    return series.fillna(False).astype(str).str.strip().str.lower().isin(truthy)


def positive_percentile_rank(values: pd.Series) -> pd.Series:
    """Percentile ranks where zero/negative values remain zero."""

    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    ranks = numeric.rank(pct=True, method="average").fillna(0.0)
    return ranks.where(numeric > 0, 0.0)


def build_catchment_class(df: pd.DataFrame) -> pd.Series:
    """Classify catchment strength from 1000m POI density and demand score."""

    total = pd.to_numeric(df["total_poi_1000m"], errors="coerce").fillna(0.0)
    score = pd.to_numeric(df["demand_driver_score_1000m"], errors="coerce").fillna(0.0)
    positive_score = score[score > 0]

    catchment = pd.Series("poi_blind", index=df.index, dtype="object")
    if positive_score.empty:
        return catchment

    moderate_cut = positive_score.quantile(0.50)
    high_cut = positive_score.quantile(0.75)
    catchment.loc[(total > 0) & (score <= moderate_cut)] = "low"
    catchment.loc[(score > moderate_cut) & (score <= high_cut)] = "moderate"
    catchment.loc[score > high_cut] = "high"
    return catchment


def validate_master_features(master: pd.DataFrame, expected_rows: int) -> None:
    """Fail fast if the Gold table breaks outlet-level contract."""

    if len(master) != expected_rows:
        raise ValueError(f"Gold row count {len(master)} does not match outlet master row count {expected_rows}")
    if master["Outlet_ID"].isna().any():
        raise ValueError("Gold table contains missing Outlet_ID values")
    duplicate_count = int(master["Outlet_ID"].duplicated().sum())
    if duplicate_count:
        raise ValueError(f"Gold table contains {duplicate_count} duplicate Outlet_ID values")


def print_summary(master: pd.DataFrame, output_path: Path) -> None:
    """Print reproducibility summary for the Gold builder."""

    print(f"Output path: {output_path}")
    print(f"Row count: {len(master)}")
    print(f"Duplicate Outlet_ID count: {int(master['Outlet_ID'].duplicated().sum())}")
    print(f"Missing Outlet_ID count: {int(master['Outlet_ID'].isna().sum())}")
    print("poi_available value counts:")
    print(master["poi_available"].value_counts(dropna=False).to_string())
    print(f"Number of columns: {len(master.columns)}")


def main() -> None:
    build_master_features()


if __name__ == "__main__":
    main()
