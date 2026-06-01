"""Validate Round 2 prediction and budget allocation outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.optimization.budget_allocator import (
    BUDGET_COLUMNS,
    GOLD_FEATURES_PATH,
    PREDICTION_COLUMNS,
TOTAL_BUDGET_LKR,
    TRANSACTIONS_PATH,
    attach_distributor_from_transactions,
    infer_western_mask,
)


OUTLET_MASTER_PATH = Path("data/silver/outlet_master.csv")
PREDICTION_PATH = Path("submissions/jarvis_predictions.csv")
BUDGET_PATH = Path("submissions/jarvis_budget_allocations.csv")
LOW_BUDGET_UTILIZATION_WARNING_LKR = 4_950_000.0
LOW_FUNDED_OUTLET_WARNING_COUNT = 50


def validate_round2_submission(
    prediction_path: Path = PREDICTION_PATH,
    budget_path: Path = BUDGET_PATH,
    outlet_master_path: Path = OUTLET_MASTER_PATH,
    gold_features_path: Path = GOLD_FEATURES_PATH,
    transactions_path: Path = TRANSACTIONS_PATH,
    total_budget_lkr: float = TOTAL_BUDGET_LKR,
) -> bool:
    """Validate both Round 2 CSV outputs."""

    outlet_master = read_csv_if_exists(outlet_master_path)
    predictions = validate_predictions(prediction_path, outlet_master)
    budget = validate_budget_allocations(
        budget_path=budget_path,
        gold_features_path=gold_features_path,
        transactions_path=transactions_path,
        total_budget_lkr=total_budget_lkr,
    )

    print("\nRound 2 validation passed.")
    print(f"Prediction rows: {len(predictions)}")
    print(f"Budget allocation rows: {len(budget)}")
    return True


def validate_predictions(path: Path, outlet_master: pd.DataFrame | None) -> pd.DataFrame:
    """Validate prediction CSV format and outlet coverage."""

    prediction = read_required_csv(path)
    errors: list[str] = []

    if list(prediction.columns) != PREDICTION_COLUMNS:
        errors.append(f"Prediction columns must be exactly {PREDICTION_COLUMNS}; found {list(prediction.columns)}")

    if "Outlet_ID" in prediction.columns:
        if prediction["Outlet_ID"].isna().any():
            errors.append("Prediction file contains missing Outlet_ID values")
        duplicates = int(prediction["Outlet_ID"].duplicated().sum())
        if duplicates:
            errors.append(f"Prediction file contains {duplicates} duplicate Outlet_ID values")

    if "Maximum_Monthly_Liters" in prediction.columns:
        values = pd.to_numeric(prediction["Maximum_Monthly_Liters"], errors="coerce")
        if values.isna().any():
            errors.append("Prediction file contains missing or non-numeric predictions")
        if values.le(0).any():
            errors.append("Prediction file contains zero or negative predictions")
    else:
        values = pd.Series(dtype=float)

    if outlet_master is not None and "Outlet_ID" in outlet_master.columns and "Outlet_ID" in prediction.columns:
        if len(prediction) != len(outlet_master):
            errors.append(
                f"Prediction row count {len(prediction)} does not match outlet_master row count {len(outlet_master)}"
            )
        expected_ids = set(outlet_master["Outlet_ID"].dropna())
        actual_ids = set(prediction["Outlet_ID"].dropna())
        missing_ids = expected_ids.difference(actual_ids)
        extra_ids = actual_ids.difference(expected_ids)
        if missing_ids:
            errors.append(f"Prediction file is missing {len(missing_ids)} outlet IDs")
        if extra_ids:
            errors.append(f"Prediction file contains {len(extra_ids)} unexpected outlet IDs")

    fail_if_errors(errors, "Prediction validation failed")
    print("Prediction CSV validation passed.")
    print_distribution(values, label="Maximum_Monthly_Liters")
    return prediction


def validate_budget_allocations(
    budget_path: Path,
    gold_features_path: Path,
    transactions_path: Path,
    total_budget_lkr: float,
) -> pd.DataFrame:
    """Validate budget CSV format, spend sanity, and Western eligibility."""

    budget = read_required_csv(budget_path)
    errors: list[str] = []

    if list(budget.columns) != BUDGET_COLUMNS:
        errors.append(f"Budget columns must be exactly {BUDGET_COLUMNS}; found {list(budget.columns)}")

    if "Outlet_ID" in budget.columns:
        if budget["Outlet_ID"].isna().any():
            errors.append("Budget file contains missing Outlet_ID values")
        duplicates = int(budget["Outlet_ID"].duplicated().sum())
        if duplicates:
            errors.append(f"Budget file contains {duplicates} duplicate Outlet_ID values")

    if "Trade_Spend_Allocation_LKR" in budget.columns:
        allocations = pd.to_numeric(budget["Trade_Spend_Allocation_LKR"], errors="coerce")
        if allocations.isna().any():
            errors.append("Budget file contains missing or non-numeric allocation values")
        if allocations.lt(0).any():
            errors.append("Budget file contains negative allocation values")
        total_allocated = float(allocations.sum())
        if total_allocated > total_budget_lkr + 0.01:
            errors.append(f"Budget total {total_allocated:.2f} exceeds {total_budget_lkr:.2f}")
        funded_outlets = int(allocations.gt(0).sum())
    else:
        allocations = pd.Series(dtype=float)
        total_allocated = 0.0
        funded_outlets = 0

    western_errors = validate_western_only(budget, gold_features_path, transactions_path)
    errors.extend(western_errors)

    fail_if_errors(errors, "Budget allocation validation failed")
    print("\nBudget allocation CSV validation passed.")
    print(f"Total allocation: {total_allocated:.2f} LKR")
    if total_allocated < LOW_BUDGET_UTILIZATION_WARNING_LKR:
        print(
            "WARNING: Total allocation is below "
            f"{LOW_BUDGET_UTILIZATION_WARNING_LKR:.2f} LKR. "
            "This is allowed by hard validation but may be business-suboptimal."
        )
    if funded_outlets < LOW_FUNDED_OUTLET_WARNING_COUNT:
        print(
            "WARNING: Fewer than "
            f"{LOW_FUNDED_OUTLET_WARNING_COUNT} outlets receive allocation. "
            "This is allowed by hard validation but may be too concentrated."
        )
    print_distribution(allocations, label="Trade_Spend_Allocation_LKR")
    return budget


def validate_western_only(
    budget: pd.DataFrame,
    gold_features_path: Path,
    transactions_path: Path,
) -> list[str]:
    """Ensure budget rows are Western Province outlets when eligibility can be inferred."""

    if "Outlet_ID" not in budget.columns:
        return []
    if not gold_features_path.exists():
        return [f"Gold feature file not found for Western validation: {gold_features_path}"]

    gold = pd.read_csv(gold_features_path)
    if "Outlet_ID" not in gold.columns:
        return [f"{gold_features_path} is missing Outlet_ID"]

    eligibility_frame = gold[["Outlet_ID"] + [col for col in gold.columns if col.lower() in {"province", "distributor_id"}]]
    eligibility_frame = attach_distributor_from_transactions(eligibility_frame, transactions_path)

    try:
        western_mask, western_source = infer_western_mask(eligibility_frame)
    except ValueError as exc:
        return [str(exc)]

    western_ids = set(eligibility_frame.loc[western_mask, "Outlet_ID"].dropna())
    budget_ids = set(budget["Outlet_ID"].dropna())
    non_western_ids = budget_ids.difference(western_ids)
    if non_western_ids:
        return [
            f"Budget file contains {len(non_western_ids)} outlets outside Western eligibility based on {western_source}"
        ]
    print(f"Western Province budget filter validation passed using {western_source}.")
    return []


def read_required_csv(path: Path) -> pd.DataFrame:
    """Read a required CSV file."""

    if not path.exists():
        raise FileNotFoundError(f"Required file does not exist: {path}")
    return pd.read_csv(path)


def read_csv_if_exists(path: Path) -> pd.DataFrame | None:
    """Read an optional CSV file."""

    if not path.exists():
        print(f"Optional validation reference not found: {path}")
        return None
    return pd.read_csv(path)


def fail_if_errors(errors: list[str], heading: str) -> None:
    """Raise a single clear validation error."""

    if not errors:
        return
    for error in errors:
        print(f"ERROR: {error}")
    raise ValueError(heading)


def print_distribution(values: pd.Series, label: str) -> None:
    """Print compact distribution summary."""

    numeric_values = pd.to_numeric(values, errors="coerce").dropna()
    if numeric_values.empty:
        print(f"{label}: no numeric values available")
        return
    print(f"{label} rows: {len(numeric_values)}")
    print(f"{label} min: {numeric_values.min():.4f}")
    print(f"{label} median: {numeric_values.median():.4f}")
    print(f"{label} mean: {numeric_values.mean():.4f}")
    print(f"{label} max: {numeric_values.max():.4f}")


def main() -> None:
    validate_round2_submission()


if __name__ == "__main__":
    main()
