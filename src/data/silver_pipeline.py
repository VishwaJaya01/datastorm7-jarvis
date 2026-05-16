"""Bronze -> Silver data pipeline for Member 1 data forensics work."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.quality.checks import (
    CheckResult,
    build_rejected_records,
    combine_failure_masks,
    duplicate_check,
    null_check,
    numeric_range_check,
    referential_integrity_check,
    value_set_check,
)


RAW_FILES = {
    "outlet_master": "outlet_master.csv",
    "outlet_coordinates": "outlet_coordinates.csv",
    "transactions": "transactions_history_final.csv",
    "seasonality": "distributor_seasonality_details.csv",
    "holidays": "holiday_list.csv",
}

EXPECTED_DISTRIBUTORS = {
    "DIST_W_01",
    "DIST_W_02",
    "DIST_W_03",
    "DIST_C_01",
    "DIST_C_02",
    "DIST_C_03",
    "DIST_NW_01",
    "DIST_NW_02",
    "DIST_S_01",
    "DIST_S_02",
}
VALID_OUTLET_SIZES = {"Small", "Medium", "Large", "Extra Large"}
SILVER_OUTLET_SIZES = VALID_OUTLET_SIZES | {"Unknown"}
VALID_OUTLET_SIZE_STATUSES = {"provided", "missing"}
VALID_OUTLET_TYPES = {"Grocery", "Hotel", "SMMT", "Pharmacy", "Kiosk", "Bakery", "Eatery"}
VALID_SEASONALITY = {"Moderate", "Favorable", "Un-Favorable"}
SEASONALITY_CANONICAL = {
    "moderate": "Moderate",
    "favorable": "Favorable",
    "unfavorable": "Un-Favorable",
}
VALID_COORD_STATUSES = {"valid", "corrected", "quarantined", "missing"}
SRI_LANKA_LAT_RANGE = (5.0, 10.0)
SRI_LANKA_LON_RANGE = (79.0, 82.0)
YEAR_RANGE = (2023, 2025)


@dataclass(frozen=True)
class PipelinePaths:
    raw: Path = Path("data/raw")
    bronze: Path = Path("data/bronze")
    silver: Path = Path("data/silver")
    rejected: Path = Path("data/rejected")
    reports_eda: Path = Path("reports/eda")


def run_pipeline(paths: PipelinePaths | None = None) -> dict[str, dict[str, int]]:
    """Run the complete Member 1 pipeline and return dataset-level metrics."""

    paths = paths or PipelinePaths()
    _ensure_directories(paths)
    rejected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    copy_raw_to_bronze(paths)

    outlet_master_raw = read_raw(paths, "outlet_master")
    outlet_master_silver, outlet_master_rejected, outlet_master_warnings = clean_outlet_master(
        outlet_master_raw,
        rejected_at,
    )

    coordinates_raw = read_raw(paths, "outlet_coordinates")
    coordinates_silver, coordinates_rejected, coordinate_corrections = clean_outlet_coordinates(
        coordinates_raw,
        valid_outlet_ids=set(outlet_master_silver["Outlet_ID"]),
        rejected_at=rejected_at,
    )
    outlet_master_silver = add_coordinate_status_to_outlets(
        outlet_master_silver,
        raw_coordinates=coordinates_raw,
        silver_coordinates=coordinates_silver,
    )
    _write_dataset_outputs(paths, "outlet_master", outlet_master_silver, outlet_master_rejected)
    _write_warning_outputs(paths, "outlet_master", outlet_master_warnings)
    _write_dataset_outputs(paths, "outlet_coordinates", coordinates_silver, coordinates_rejected)
    coordinate_corrections.to_csv(paths.silver / "outlet_coordinates_corrections.csv", index=False)

    seasonality_raw = read_raw(paths, "seasonality")
    seasonality_silver, seasonality_rejected = clean_seasonality(seasonality_raw, rejected_at)
    _write_dataset_outputs(paths, "distributor_seasonality_details", seasonality_silver, seasonality_rejected)

    holidays_raw = read_raw(paths, "holidays")
    holidays_silver, holidays_rejected = clean_holidays(holidays_raw, rejected_at)
    _write_dataset_outputs(paths, "holiday_list", holidays_silver, holidays_rejected)

    transactions_raw = read_raw(paths, "transactions")
    transactions_silver, transactions_rejected = clean_transactions(
        transactions_raw,
        valid_outlet_ids=set(outlet_master_silver["Outlet_ID"]),
        valid_distributor_ids=EXPECTED_DISTRIBUTORS,
        rejected_at=rejected_at,
    )
    _write_dataset_outputs(paths, "transactions_history_final", transactions_silver, transactions_rejected)

    validate_silver_outputs(paths)
    metrics = build_pipeline_metrics(paths)
    write_schema_contract(paths)
    write_forensics_report(paths, metrics)
    return metrics


def copy_raw_to_bronze(paths: PipelinePaths | None = None) -> None:
    """Copy raw CSV files exactly as provided into the Bronze layer."""

    paths = paths or PipelinePaths()
    _ensure_directories(paths)
    for filename in RAW_FILES.values():
        source = paths.raw / filename
        if not source.exists():
            raise FileNotFoundError(f"Missing raw input: {source}")
        shutil.copy2(source, paths.bronze / filename)


def read_raw(paths: PipelinePaths, dataset_key: str) -> pd.DataFrame:
    filename = RAW_FILES[dataset_key]
    return pd.read_csv(paths.raw / filename)


def clean_outlet_master(df: pd.DataFrame, rejected_at: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source_file = RAW_FILES["outlet_master"]
    cleaned = df.copy()
    outlet_size = cleaned["Outlet_Size"].astype("string").str.strip()
    missing_size_mask = outlet_size.isna() | outlet_size.eq("")
    outlet_size = outlet_size.replace({"small": "Small"})
    cleaned["Outlet_Size"] = outlet_size.mask(missing_size_mask, "Unknown")
    cleaned["outlet_size_status"] = "provided"
    cleaned.loc[missing_size_mask, "outlet_size_status"] = "missing"
    cleaned["Outlet_Type"] = (
        cleaned["Outlet_Type"]
        .astype("string")
        .str.strip()
        .replace({"Grocry": "Grocery", "Bakry": "Bakery"})
    )

    results = [
        null_check(cleaned, ["Outlet_ID"], "outlet_id_required"),
        duplicate_check(cleaned, ["Outlet_ID"], check_name="outlet_id_duplicate"),
        value_set_check(cleaned, "Outlet_Size", SILVER_OUTLET_SIZES, "outlet_size_allowed_values"),
        value_set_check(cleaned, "outlet_size_status", VALID_OUTLET_SIZE_STATUSES, "outlet_size_status_allowed_values"),
        value_set_check(cleaned, "Outlet_Type", VALID_OUTLET_TYPES, "outlet_type_allowed_values"),
        numeric_range_check(cleaned, "Cooler_Count", min_value=0, check_name="cooler_count_non_negative"),
    ]
    warnings = _warning_records(
        cleaned,
        missing_size_mask,
        source_file=source_file,
        check_name="outlet_size_missing_warning",
        failure_reason="Outlet_Size missing; retained in Silver as Unknown for full outlet coverage",
        logged_at=rejected_at,
        action_taken="retained_with_unknown_outlet_size",
    )
    silver, rejected = _silver_and_rejected(cleaned, results, source_file, rejected_at)
    return silver, rejected, warnings


def clean_outlet_coordinates(
    df: pd.DataFrame,
    valid_outlet_ids: set[str],
    rejected_at: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    source_file = RAW_FILES["outlet_coordinates"]
    cleaned = df.copy()
    cleaned["Latitude"] = pd.to_numeric(cleaned["Latitude"], errors="coerce")
    cleaned["Longitude"] = pd.to_numeric(cleaned["Longitude"], errors="coerce")

    valid_original = _within_sri_lanka_bbox(cleaned["Latitude"], cleaned["Longitude"])
    valid_swapped = _within_sri_lanka_bbox(cleaned["Longitude"], cleaned["Latitude"])
    swap_mask = ~valid_original & valid_swapped

    corrections = cleaned.loc[swap_mask, ["Outlet_ID", "Latitude", "Longitude"]].copy()
    corrections = corrections.rename(columns={"Latitude": "Original_Latitude", "Longitude": "Original_Longitude"})
    corrections["Corrected_Latitude"] = corrections["Original_Longitude"]
    corrections["Corrected_Longitude"] = corrections["Original_Latitude"]
    corrections["correction_reason"] = "Latitude/longitude appeared swapped and corrected inside Sri Lanka bounding box"
    corrections["corrected_at"] = rejected_at

    cleaned.loc[swap_mask, ["Latitude", "Longitude"]] = cleaned.loc[swap_mask, ["Longitude", "Latitude"]].to_numpy()
    cleaned["coord_status"] = "valid"
    cleaned.loc[swap_mask, "coord_status"] = "corrected"

    results = [
        null_check(cleaned, ["Outlet_ID", "Latitude", "Longitude"], "coordinate_required_fields"),
        duplicate_check(cleaned, ["Outlet_ID"], check_name="coordinate_outlet_duplicate"),
        referential_integrity_check(cleaned, "Outlet_ID", valid_outlet_ids, "coordinate_outlet_fk"),
        numeric_range_check(cleaned, "Latitude", *SRI_LANKA_LAT_RANGE, check_name="latitude_sri_lanka_bbox"),
        numeric_range_check(cleaned, "Longitude", *SRI_LANKA_LON_RANGE, check_name="longitude_sri_lanka_bbox"),
    ]
    silver, rejected = _silver_and_rejected(cleaned, results, source_file, rejected_at)
    return silver, rejected, corrections


def add_coordinate_status_to_outlets(
    outlet_master: pd.DataFrame,
    raw_coordinates: pd.DataFrame,
    silver_coordinates: pd.DataFrame,
) -> pd.DataFrame:
    """Add POI-readiness fields to Silver outlet master."""

    enriched = outlet_master.copy()
    raw_coord_ids = set(raw_coordinates["Outlet_ID"].dropna())
    usable_coord_ids = set(silver_coordinates["Outlet_ID"].dropna())
    corrected_usable_ids = set(
        silver_coordinates.loc[silver_coordinates["coord_status"].eq("corrected"), "Outlet_ID"].dropna()
    )

    def resolve_status(outlet_id: str) -> str:
        if outlet_id in corrected_usable_ids:
            return "corrected"
        if outlet_id in usable_coord_ids:
            return "valid"
        if outlet_id in raw_coord_ids:
            return "quarantined"
        return "missing"

    enriched["coord_status"] = enriched["Outlet_ID"].map(resolve_status)
    enriched["has_valid_coord"] = enriched["coord_status"].isin({"valid", "corrected"})
    return enriched


def clean_transactions(
    df: pd.DataFrame,
    valid_outlet_ids: set[str],
    valid_distributor_ids: set[str],
    rejected_at: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_file = RAW_FILES["transactions"]
    cleaned = df.copy()
    for column in ["Year", "Month", "Volume_Liters", "Total_Bill_Value"]:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    key = ["Outlet_ID", "Year", "Month", "Distributor_ID", "SKU_ID"]
    results = [
        null_check(cleaned, key + ["Volume_Liters", "Total_Bill_Value"], "transaction_required_fields"),
        duplicate_check(cleaned, key, check_name="transaction_composite_key_duplicate"),
        referential_integrity_check(cleaned, "Outlet_ID", valid_outlet_ids, "transaction_outlet_fk"),
        referential_integrity_check(cleaned, "Distributor_ID", valid_distributor_ids, "transaction_distributor_fk"),
        numeric_range_check(cleaned, "Year", *YEAR_RANGE, check_name="transaction_year_range"),
        numeric_range_check(cleaned, "Month", 1, 12, check_name="transaction_month_range"),
        numeric_range_check(cleaned, "Volume_Liters", min_value=0, inclusive="neither", check_name="volume_positive"),
        numeric_range_check(cleaned, "Total_Bill_Value", min_value=0, inclusive="neither", check_name="bill_value_positive"),
    ]
    silver, rejected = _silver_and_rejected(cleaned, results, source_file, rejected_at)
    silver["Year"] = silver["Year"].astype("int64")
    silver["Month"] = silver["Month"].astype("int64")
    return silver, rejected


def clean_seasonality(df: pd.DataFrame, rejected_at: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_file = RAW_FILES["seasonality"]
    cleaned = df.copy()
    cleaned["Year"] = pd.to_numeric(cleaned["Year"], errors="coerce")
    cleaned["Month"] = pd.to_numeric(cleaned["Month"], errors="coerce")
    cleaned["Seasonality_Index"] = _canonicalize_seasonality(cleaned["Seasonality_Index"])

    results = [
        null_check(cleaned, ["Distributor_ID", "Year", "Month", "Seasonality_Index"], "seasonality_required_fields"),
        duplicate_check(cleaned, ["Distributor_ID", "Year", "Month"], check_name="seasonality_distributor_month_duplicate"),
        referential_integrity_check(cleaned, "Distributor_ID", EXPECTED_DISTRIBUTORS, "seasonality_distributor_fk"),
        numeric_range_check(cleaned, "Year", *YEAR_RANGE, check_name="seasonality_year_range"),
        numeric_range_check(cleaned, "Month", 1, 12, check_name="seasonality_month_range"),
        value_set_check(cleaned, "Seasonality_Index", VALID_SEASONALITY, "seasonality_allowed_values"),
    ]
    silver, rejected = _silver_and_rejected(cleaned, results, source_file, rejected_at)
    silver["Year"] = silver["Year"].astype("int64")
    silver["Month"] = silver["Month"].astype("int64")
    return silver, rejected


def clean_holidays(df: pd.DataFrame, rejected_at: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    source_file = RAW_FILES["holidays"]
    cleaned = df.copy()
    cleaned["Date"] = pd.to_datetime(cleaned["Date"], errors="coerce", utc=True)
    cleaned["Holiday_Name"] = cleaned["Holiday_Name"].astype("string").str.strip()
    cleaned["Holiday_Type"] = cleaned["Holiday_Type"].astype("string").str.strip()

    results = [
        null_check(cleaned, ["Date", "Holiday_Name", "Holiday_Type"], "holiday_required_fields"),
        duplicate_check(cleaned, ["Date", "Holiday_Name", "Holiday_Type"], check_name="holiday_exact_duplicate"),
    ]
    silver, rejected = _silver_and_rejected(cleaned, results, source_file, rejected_at)
    silver["Date"] = silver["Date"].dt.strftime("%Y-%m-%d")
    if "Date" in rejected.columns and not rejected.empty:
        rejected["Date"] = pd.to_datetime(rejected["Date"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    return silver, rejected


def build_pipeline_metrics(paths: PipelinePaths | None = None) -> dict[str, dict[str, int]]:
    paths = paths or PipelinePaths()
    metrics: dict[str, dict[str, int]] = {}
    output_names = {
        "outlet_master": "outlet_master.csv",
        "outlet_coordinates": "outlet_coordinates.csv",
        "distributor_seasonality_details": "distributor_seasonality_details.csv",
        "holiday_list": "holiday_list.csv",
        "transactions_history_final": "transactions_history_final.csv",
    }
    action_taken = {
        "outlet_master": "Standardized outlet categories; retained missing Outlet_Size as Unknown with warning flag.",
        "outlet_coordinates": "Corrected safe lat/lon swaps; removed unusable coordinates from Silver and surfaced coord_status on outlets.",
        "distributor_seasonality_details": "Canonicalized seasonality labels and validated distributor-month keys.",
        "holiday_list": "Removed exact duplicate holidays and preserved distinct same-date holidays.",
        "transactions_history_final": "Rejected non-positive values, duplicate composite keys, invalid dates, and FK violations.",
    }

    for dataset, filename in output_names.items():
        raw_path = paths.raw / filename
        bronze_path = paths.bronze / filename
        silver_path = paths.silver / filename
        rejected_path = paths.rejected / f"{dataset}_rejected.csv"
        warning_path = paths.rejected / f"{dataset}_warnings.csv"

        raw_rows = len(pd.read_csv(raw_path)) if raw_path.exists() else 0
        bronze_rows = len(pd.read_csv(bronze_path)) if bronze_path.exists() else 0
        silver_rows = len(pd.read_csv(silver_path)) if silver_path.exists() else 0
        rejected = pd.read_csv(rejected_path) if rejected_path.exists() else pd.DataFrame()
        warnings = pd.read_csv(warning_path) if warning_path.exists() else pd.DataFrame()
        rejected_events = len(rejected)
        warning_events = len(warnings)

        metrics[dataset] = {
            "raw_rows": raw_rows,
            "bronze_rows": bronze_rows,
            "silver_rows": silver_rows,
            "hard_rejected_rows": _unique_audit_rows(rejected),
            "hard_rejected_events": rejected_events,
            "warning_rows": _unique_audit_rows(warnings),
            "warning_events": warning_events,
            "corrected_rows": _corrected_rows(paths, dataset),
            "action_taken": action_taken[dataset],
        }

    summary_path = paths.reports_eda / "data_quality_summary.json"
    summary_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def validate_silver_outputs(paths: PipelinePaths | None = None) -> None:
    """Fail fast if Silver outputs violate the downstream handoff contract."""

    paths = paths or PipelinePaths()
    outlet_master = pd.read_csv(paths.silver / "outlet_master.csv")
    coordinates = pd.read_csv(paths.silver / "outlet_coordinates.csv")
    transactions = pd.read_csv(paths.silver / "transactions_history_final.csv")
    seasonality = pd.read_csv(paths.silver / "distributor_seasonality_details.csv")
    holidays = pd.read_csv(paths.silver / "holiday_list.csv")

    assert outlet_master["Outlet_ID"].is_unique, "Silver outlet master must have unique Outlet_ID values"
    assert {"Outlet_Size", "outlet_size_status", "coord_status", "has_valid_coord"}.issubset(outlet_master.columns), (
        "Silver outlet master is missing handoff columns"
    )
    assert set(outlet_master["Outlet_Size"]).issubset(SILVER_OUTLET_SIZES), "Invalid Outlet_Size in Silver outlet master"
    assert set(outlet_master["outlet_size_status"]).issubset(VALID_OUTLET_SIZE_STATUSES), (
        "Invalid outlet_size_status in Silver outlet master"
    )
    assert (outlet_master.loc[outlet_master["outlet_size_status"].eq("missing"), "Outlet_Size"] == "Unknown").all(), (
        "Missing outlet sizes must be retained as Unknown"
    )
    assert not outlet_master.loc[outlet_master["outlet_size_status"].eq("provided"), "Outlet_Size"].eq("Unknown").any(), (
        "Only missing outlet sizes may use Unknown"
    )
    assert outlet_master["coord_status"].notna().all(), "Every Silver outlet needs a coord_status"
    assert set(outlet_master["coord_status"]).issubset(VALID_COORD_STATUSES), "Invalid coord_status in Silver outlet master"
    assert set(outlet_master["has_valid_coord"].astype(str).str.lower()).issubset({"true", "false"}), (
        "has_valid_coord must be boolean-like"
    )

    valid_coord_outlets = set(outlet_master.loc[outlet_master["has_valid_coord"].astype(str).str.lower() == "true", "Outlet_ID"])
    silver_coord_outlets = set(coordinates["Outlet_ID"])
    assert valid_coord_outlets == silver_coord_outlets, "Usable coordinate outlets must match has_valid_coord=True outlets"
    assert set(coordinates["coord_status"]).issubset({"valid", "corrected"}), "Silver coordinates must be valid/corrected only"
    assert coordinates["Latitude"].between(*SRI_LANKA_LAT_RANGE).all(), "Silver coordinates include invalid latitudes"
    assert coordinates["Longitude"].between(*SRI_LANKA_LON_RANGE).all(), "Silver coordinates include invalid longitudes"

    blind_outlets = set(outlet_master.loc[outlet_master["coord_status"].isin({"quarantined", "missing"}), "Outlet_ID"])
    assert blind_outlets.isdisjoint(silver_coord_outlets), "Quarantined/missing coordinate outlets leaked into Silver coordinates"
    assert (transactions["Volume_Liters"] > 0).all(), "Silver transactions include non-positive volume"
    assert (transactions["Total_Bill_Value"] > 0).all(), "Silver transactions include non-positive bill value"
    assert set(transactions["Outlet_ID"]).issubset(set(outlet_master["Outlet_ID"])), "Transaction outlet FK violation"
    assert set(transactions["Distributor_ID"]).issubset(EXPECTED_DISTRIBUTORS), "Transaction distributor FK violation"
    assert set(seasonality["Seasonality_Index"]).issubset(VALID_SEASONALITY), "Seasonality labels are not canonical"
    assert not holidays.duplicated(["Date", "Holiday_Name", "Holiday_Type"]).any(), "Exact duplicate holidays remain"


def write_schema_contract(paths: PipelinePaths | None = None) -> None:
    """Write the Silver schema handoff contract for Members 2 and 3."""

    paths = paths or PipelinePaths()
    silver_counts = {
        path.name: len(pd.read_csv(path))
        for path in [
            paths.silver / "outlet_master.csv",
            paths.silver / "outlet_coordinates.csv",
            paths.silver / "transactions_history_final.csv",
            paths.silver / "distributor_seasonality_details.csv",
            paths.silver / "holiday_list.csv",
        ]
        if path.exists()
    }

    lines = [
        "# Silver Schema Contract",
        "",
        "This contract defines the Silver-layer files consumed by POI enrichment and modeling.",
        "",
        "## Row Counts",
        "",
        "| File | Silver Rows | Expectation |",
        "|---|---:|---|",
        f"| outlet_master.csv | {silver_counts.get('outlet_master.csv', 0)} | One row per retained outlet; missing `Outlet_Size` is retained as `Unknown`. |",
        f"| outlet_coordinates.csv | {silver_counts.get('outlet_coordinates.csv', 0)} | Only outlets with usable `valid` or `corrected` coordinates. |",
        f"| transactions_history_final.csv | {silver_counts.get('transactions_history_final.csv', 0)} | Clean transaction history with positive volume/value and valid FKs. |",
        f"| distributor_seasonality_details.csv | {silver_counts.get('distributor_seasonality_details.csv', 0)} | One row per distributor/year/month. |",
        f"| holiday_list.csv | {silver_counts.get('holiday_list.csv', 0)} | Exact duplicate holidays removed; distinct same-date holidays preserved. |",
        "",
        "## File Schemas",
        "",
        "| File | Columns | Domains / Notes |",
        "|---|---|---|",
        "| outlet_master.csv | `Outlet_ID`, `Outlet_Size`, `Cooler_Count`, `Outlet_Type`, `outlet_size_status`, `coord_status`, `has_valid_coord` | `Outlet_Size`: Small/Medium/Large/Extra Large/Unknown. `outlet_size_status`: provided/missing. `coord_status`: valid/corrected/quarantined/missing. |",
        "| outlet_coordinates.csv | `Outlet_ID`, `Latitude`, `Longitude`, `coord_status` | Coordinates are inside Sri Lanka bounds; `coord_status` is valid/corrected only. |",
        "| transactions_history_final.csv | `Outlet_ID`, `Year`, `Month`, `Distributor_ID`, `SKU_ID`, `Volume_Liters`, `Total_Bill_Value` | Year 2023-2025, month 1-12, positive volume and bill value. |",
        "| distributor_seasonality_details.csv | `Distributor_ID`, `Year`, `Month`, `Seasonality_Index` | `Seasonality_Index`: Moderate/Favorable/Un-Favorable after normalization. |",
        "| holiday_list.csv | `Date`, `Holiday_Name`, `Holiday_Type` | `Date` is ISO `YYYY-MM-DD`; exact duplicates removed. |",
        "",
        "## Referential Integrity",
        "",
        "- `transactions_history_final.Outlet_ID` must exist in `outlet_master.Outlet_ID`.",
        "- `transactions_history_final.Distributor_ID` must be one of the 10 competition distributor IDs.",
        "- `outlet_coordinates.Outlet_ID` must exist in `outlet_master.Outlet_ID`.",
        "- `outlet_master[has_valid_coord=True].Outlet_ID` must exactly match `outlet_coordinates.Outlet_ID`.",
        "- Outlets with `coord_status` of `quarantined` or `missing` must not appear in `outlet_coordinates.csv`.",
        "",
    ]
    (paths.reports_eda / "silver_schema_contract.md").write_text("\n".join(lines), encoding="utf-8")


def write_forensics_report(paths: PipelinePaths, metrics: dict[str, dict[str, int]]) -> None:
    lines = [
        "# Data Forensics & Pipeline",
        "",
        "## Pipeline Summary",
        "",
        "Member 1 implemented a reproducible Bronze -> Silver -> Rejected pipeline. Bronze stores exact raw CSV copies. Silver contains cleaned, model-ready tables. Rejected records are written separately with `source_file`, `check_name`, `failure_reason`, and `rejected_at` so no failed record is silently dropped.",
        "",
        "| Dataset | Raw Rows | Bronze Rows | Silver Rows | Hard Rejected Rows | Hard Rejected Events | Warning Events | Corrected Rows | Action Taken |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for dataset, values in metrics.items():
        lines.append(
            f"| {dataset} | {values['raw_rows']} | {values['bronze_rows']} | {values['silver_rows']} | "
            f"{values['hard_rejected_rows']} | {values['hard_rejected_events']} | {values['warning_events']} | "
            f"{values['corrected_rows']} | {values['action_taken']} |"
        )

    lines.extend(
        [
            "",
            "## Main Issues Found",
            "",
            "- `outlet_master.csv`: normalized category typos/spacing (`Grocry`, `Bakry`, ` Eatery `, `small`) and retained missing outlet sizes as `Unknown` with `outlet_size_status = missing`.",
            "- `outlet_coordinates.csv`: detected impossible coordinates, corrected swapped latitude/longitude only when the corrected pair fit Sri Lanka bounds, and exposed `coord_status`/`has_valid_coord` on Silver outlets.",
            "- `transactions_history_final.csv`: rejected non-positive sales values, invalid dates, orphan outlet/distributor IDs, and duplicate outlet-month-distributor-SKU keys after the first occurrence.",
            "- `distributor_seasonality_details.csv`: normalized seasonality casing/hyphenation before validating canonical labels (`Moderate`, `Favorable`, `Un-Favorable`).",
            "- `holiday_list.csv`: parsed holiday dates and removed exact duplicate holiday records while preserving multiple different holidays on the same date.",
            "",
            "## Silver Coordinate Contract",
            "",
            "`coord_status` uses four values: `valid` and `corrected` have usable Silver coordinate rows; `quarantined` had a coordinate row that failed DQ; `missing` means no coordinate row was supplied for that outlet. `has_valid_coord` is true only for `valid` and `corrected` outlets.",
            "",
            "## Business Impact",
            "",
            "The Silver layer protects downstream POI enrichment and latent-potential modeling from legacy SFA/ERP artifacts such as impossible store locations, negative sales, duplicated records, and decayed master data. Outlets marked `quarantined` or `missing` for coordinates are POI-blind, so Members 2 and 3 can treat their geographic potential signals separately instead of silently assuming location quality. Missing outlet size is retained rather than dropped because excluding those outlets would risk incomplete final predictions. The rejected and warning layers preserve auditability for judging and let the team revisit quarantined records later if a modeling recovery rule is justified.",
            "",
        ]
    )
    (paths.reports_eda / "data_forensics_pipeline.md").write_text("\n".join(lines), encoding="utf-8")


def _silver_and_rejected(
    df: pd.DataFrame,
    results: list[CheckResult],
    source_file: str,
    rejected_at: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rejected = build_rejected_records(df, results, source_file, rejected_at)
    failure_mask = combine_failure_masks(results, df.index)
    silver = df.loc[~failure_mask].copy()
    return silver, rejected


def _write_dataset_outputs(paths: PipelinePaths, dataset_name: str, silver: pd.DataFrame, rejected: pd.DataFrame) -> None:
    silver.to_csv(paths.silver / f"{dataset_name}.csv", index=False)
    rejected.to_csv(paths.rejected / f"{dataset_name}_rejected.csv", index=False)


def _write_warning_outputs(paths: PipelinePaths, dataset_name: str, warnings: pd.DataFrame) -> None:
    warnings.to_csv(paths.rejected / f"{dataset_name}_warnings.csv", index=False)


def _warning_records(
    df: pd.DataFrame,
    mask: pd.Series,
    source_file: str,
    check_name: str,
    failure_reason: str,
    logged_at: str,
    action_taken: str,
) -> pd.DataFrame:
    warnings = df.loc[mask].copy()
    warnings["source_file"] = source_file
    warnings["check_name"] = check_name
    warnings["failure_reason"] = failure_reason
    warnings["rejected_at"] = logged_at
    warnings["severity"] = "warning"
    warnings["action_taken"] = action_taken
    return warnings


def _unique_audit_rows(audit_df: pd.DataFrame) -> int:
    if audit_df.empty:
        return 0
    metadata_columns = {"source_file", "check_name", "failure_reason", "rejected_at", "severity", "action_taken"}
    source_columns = [column for column in audit_df.columns if column not in metadata_columns]
    return len(audit_df[source_columns].drop_duplicates())


def _corrected_rows(paths: PipelinePaths, dataset: str) -> int:
    if dataset != "outlet_coordinates":
        return 0
    corrections_path = paths.silver / "outlet_coordinates_corrections.csv"
    if not corrections_path.exists():
        return 0
    return len(pd.read_csv(corrections_path))


def _ensure_directories(paths: PipelinePaths) -> None:
    for path in [paths.raw, paths.bronze, paths.silver, paths.rejected, paths.reports_eda]:
        path.mkdir(parents=True, exist_ok=True)


def _within_sri_lanka_bbox(latitude: pd.Series, longitude: pd.Series) -> pd.Series:
    return (
        latitude.between(*SRI_LANKA_LAT_RANGE, inclusive="both")
        & longitude.between(*SRI_LANKA_LON_RANGE, inclusive="both")
    )


def _canonicalize_seasonality(series: pd.Series) -> pd.Series:
    stripped = series.astype("string").str.strip()

    def normalize_key(value: object) -> str | None:
        if pd.isna(value):
            return None
        return re.sub(r"[^a-z]+", "", str(value).lower())

    keys = stripped.map(normalize_key)
    canonical = keys.map(SEASONALITY_CANONICAL)
    return canonical.astype("string").fillna(stripped)


def main() -> None:
    metrics = run_pipeline()
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
