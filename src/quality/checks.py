"""Reusable data quality checks for the Bronze -> Silver pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


@dataclass(frozen=True)
class CheckResult:
    """Rows that failed one data quality rule."""

    mask: pd.Series
    check_name: str
    failure_reason: str


def _empty_mask(df: pd.DataFrame) -> pd.Series:
    return pd.Series(False, index=df.index)


def _missing_columns(df: pd.DataFrame, columns: Sequence[str]) -> list[str]:
    return [column for column in columns if column not in df.columns]


def null_check(
    df: pd.DataFrame,
    columns: Sequence[str],
    check_name: str = "null_check",
) -> CheckResult:
    """Flag rows where mandatory fields are null or blank strings."""

    missing = _missing_columns(df, columns)
    if missing:
        return CheckResult(
            mask=pd.Series(True, index=df.index),
            check_name=check_name,
            failure_reason=f"Required columns missing from dataset: {', '.join(missing)}",
        )

    mask = _empty_mask(df)
    for column in columns:
        values = df[column]
        if pd.api.types.is_string_dtype(values) or values.dtype == object:
            mask |= values.isna() | values.astype(str).str.strip().eq("")
        else:
            mask |= values.isna()

    return CheckResult(
        mask=mask,
        check_name=check_name,
        failure_reason=f"Mandatory field is null/blank: {', '.join(columns)}",
    )


def duplicate_check(
    df: pd.DataFrame,
    key_columns: Sequence[str],
    keep: str | bool = "first",
    check_name: str = "duplicate_check",
) -> CheckResult:
    """Flag duplicate rows based on a configurable key."""

    missing = _missing_columns(df, key_columns)
    if missing:
        return CheckResult(
            mask=pd.Series(True, index=df.index),
            check_name=check_name,
            failure_reason=f"Duplicate key columns missing: {', '.join(missing)}",
        )

    mask = df.duplicated(subset=list(key_columns), keep=keep)
    return CheckResult(
        mask=mask,
        check_name=check_name,
        failure_reason=f"Duplicate record for key: {', '.join(key_columns)}",
    )


def numeric_range_check(
    df: pd.DataFrame,
    column: str,
    min_value: float | None = None,
    max_value: float | None = None,
    inclusive: str = "both",
    check_name: str | None = None,
) -> CheckResult:
    """Flag values outside an expected numeric range."""

    resolved_name = check_name or f"{column}_range_check"
    if column not in df.columns:
        return CheckResult(
            mask=pd.Series(True, index=df.index),
            check_name=resolved_name,
            failure_reason=f"Numeric range column missing: {column}",
        )

    numeric_values = pd.to_numeric(df[column], errors="coerce")
    mask = numeric_values.isna()

    if min_value is not None:
        if inclusive in {"both", "left"}:
            mask |= numeric_values < min_value
        else:
            mask |= numeric_values <= min_value

    if max_value is not None:
        if inclusive in {"both", "right"}:
            mask |= numeric_values > max_value
        else:
            mask |= numeric_values >= max_value

    range_text = _format_range(min_value, max_value, inclusive)
    return CheckResult(
        mask=mask,
        check_name=resolved_name,
        failure_reason=f"{column} is non-numeric or outside expected range {range_text}",
    )


def value_set_check(
    df: pd.DataFrame,
    column: str,
    allowed_values: Iterable[object],
    check_name: str | None = None,
) -> CheckResult:
    """Flag rows where a column is not in an allowed value set."""

    resolved_name = check_name or f"{column}_allowed_values_check"
    if column not in df.columns:
        return CheckResult(
            mask=pd.Series(True, index=df.index),
            check_name=resolved_name,
            failure_reason=f"Allowed-value column missing: {column}",
        )

    allowed = set(allowed_values)
    mask = ~df[column].isin(allowed)
    return CheckResult(
        mask=mask,
        check_name=resolved_name,
        failure_reason=f"{column} is not one of: {', '.join(map(str, sorted(allowed)))}",
    )


def referential_integrity_check(
    df: pd.DataFrame,
    column: str,
    valid_values: Iterable[object],
    check_name: str | None = None,
) -> CheckResult:
    """Flag foreign-key values that do not exist in a reference dataset."""

    resolved_name = check_name or f"{column}_referential_integrity_check"
    if column not in df.columns:
        return CheckResult(
            mask=pd.Series(True, index=df.index),
            check_name=resolved_name,
            failure_reason=f"Foreign-key column missing: {column}",
        )

    valid = set(valid_values)
    mask = ~df[column].isin(valid)
    return CheckResult(
        mask=mask,
        check_name=resolved_name,
        failure_reason=f"{column} does not exist in reference dataset",
    )


def build_rejected_records(
    df: pd.DataFrame,
    results: Sequence[CheckResult],
    source_file: str,
    rejected_at: str,
) -> pd.DataFrame:
    """Convert failed checks to the standard rejected-record shape."""

    rejected_frames: list[pd.DataFrame] = []
    for result in results:
        failed = df.loc[result.mask].copy()
        if failed.empty:
            continue
        failed["source_file"] = source_file
        failed["check_name"] = result.check_name
        failed["failure_reason"] = result.failure_reason
        failed["rejected_at"] = rejected_at
        rejected_frames.append(failed)

    if not rejected_frames:
        return pd.DataFrame(columns=list(df.columns) + ["source_file", "check_name", "failure_reason", "rejected_at"])

    return pd.concat(rejected_frames, ignore_index=True)


def combine_failure_masks(results: Sequence[CheckResult], index: pd.Index) -> pd.Series:
    """Return one mask for rows that failed at least one check."""

    mask = pd.Series(False, index=index)
    for result in results:
        mask |= result.mask
    return mask


def _format_range(min_value: float | None, max_value: float | None, inclusive: str) -> str:
    left = "[" if inclusive in {"both", "left"} else "("
    right = "]" if inclusive in {"both", "right"} else ")"
    low = "-inf" if min_value is None else str(min_value)
    high = "inf" if max_value is None else str(max_value)
    return f"{left}{low}, {high}{right}"
