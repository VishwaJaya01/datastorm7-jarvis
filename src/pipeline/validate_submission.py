"""Validate the Team Jarvis final submission file."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


OUTLET_MASTER_PATH = Path("data/silver/outlet_master.csv")
SUBMISSION_PATH = Path("submissions/teamname_predictions.csv")
REQUIRED_COLUMNS = ["Outlet_ID", "Maximum_Monthly_Liters"]


def validate_submission(
    submission_path: Path = SUBMISSION_PATH,
    outlet_master_path: Path = OUTLET_MASTER_PATH,
) -> bool:
    """Validate submission format, row coverage, and prediction sanity."""

    if not submission_path.exists():
        raise FileNotFoundError(f"Submission file does not exist: {submission_path}")
    if not outlet_master_path.exists():
        raise FileNotFoundError(f"Silver outlet master does not exist: {outlet_master_path}")

    submission = pd.read_csv(submission_path)
    outlet_master = pd.read_csv(outlet_master_path)

    errors: list[str] = []
    if list(submission.columns) != REQUIRED_COLUMNS:
        errors.append(
            f"Submission columns must be exactly {REQUIRED_COLUMNS}; found {list(submission.columns)}"
        )
    if "Outlet_ID" not in outlet_master.columns:
        errors.append("outlet_master.csv must contain Outlet_ID")

    if "Outlet_ID" in submission.columns:
        if submission["Outlet_ID"].isna().any():
            errors.append("Outlet_ID contains missing values")
        duplicate_count = int(submission["Outlet_ID"].duplicated().sum())
        if duplicate_count:
            errors.append(f"Outlet_ID contains {duplicate_count} duplicates")

    if "Maximum_Monthly_Liters" in submission.columns:
        predictions = pd.to_numeric(submission["Maximum_Monthly_Liters"], errors="coerce")
        if predictions.isna().any():
            errors.append("Maximum_Monthly_Liters contains missing or non-numeric values")
        if predictions.le(0).any():
            errors.append("Maximum_Monthly_Liters contains zero or negative values")
    else:
        predictions = pd.Series(dtype=float)

    if "Outlet_ID" in outlet_master.columns and "Outlet_ID" in submission.columns:
        expected_ids = set(outlet_master["Outlet_ID"].dropna())
        submitted_ids = set(submission["Outlet_ID"].dropna())
        if len(submission) != len(outlet_master):
            errors.append(
                f"Submission row count {len(submission)} does not match outlet_master row count {len(outlet_master)}"
            )
        missing_ids = expected_ids.difference(submitted_ids)
        extra_ids = submitted_ids.difference(expected_ids)
        if missing_ids:
            errors.append(f"Submission is missing {len(missing_ids)} outlet IDs from outlet_master")
        if extra_ids:
            errors.append(f"Submission includes {len(extra_ids)} outlet IDs not found in outlet_master")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise ValueError("Submission validation failed")

    print("Submission validation passed.")
    print_distribution_summary(predictions)
    return True


def print_distribution_summary(predictions: pd.Series) -> None:
    """Print prediction distribution summary for review."""

    print(f"Rows: {len(predictions)}")
    print(f"Min: {predictions.min():.4f}")
    print(f"P25: {predictions.quantile(0.25):.4f}")
    print(f"Median: {predictions.median():.4f}")
    print(f"Mean: {predictions.mean():.4f}")
    print(f"P75: {predictions.quantile(0.75):.4f}")
    print(f"P90: {predictions.quantile(0.90):.4f}")
    print(f"Max: {predictions.max():.4f}")


def main() -> None:
    validate_submission()


if __name__ == "__main__":
    main()
