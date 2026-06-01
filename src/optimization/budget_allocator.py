"""Western Province trade-spend allocation for Round 2.

The allocator is intentionally simple and explainable. It combines predicted
latent potential, historical outlet scale, spatial demand signals, confidence
signals, and a saturation penalty into a bounded priority score.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PREDICTIONS_PATH = Path("submissions/jarvis_predictions.csv")
GOLD_FEATURES_PATH = Path("data/gold/master_features.csv")
TRANSACTIONS_PATH = Path("data/silver/transactions_history_final.csv")
OUTPUT_PATH = Path("submissions/jarvis_budget_allocations.csv")

TOTAL_BUDGET_LKR = 5_000_000.0
MAX_ALLOCATION_PER_OUTLET_LKR = 100_000.0
MIN_ALLOCATION_LKR = 5_000.0
TARGET_ALLOCATION_OUTLETS = 300
ROUNDING_UNIT_LKR = 100.0
WESTERN_DISTRIBUTORS = {"DIST_W_01", "DIST_W_02", "DIST_W_03"}

PREDICTION_COLUMNS = ["Outlet_ID", "Maximum_Monthly_Liters"]
BUDGET_COLUMNS = ["Outlet_ID", "Trade_Spend_Allocation_LKR"]


def allocate_budget(
    predictions_path: Path = PREDICTIONS_PATH,
    gold_features_path: Path = GOLD_FEATURES_PATH,
    output_path: Path = OUTPUT_PATH,
    transactions_path: Path = TRANSACTIONS_PATH,
    total_budget_lkr: float = TOTAL_BUDGET_LKR,
    max_allocation_per_outlet_lkr: float = MAX_ALLOCATION_PER_OUTLET_LKR,
    min_allocation_lkr: float = MIN_ALLOCATION_LKR,
    target_outlet_count: int = TARGET_ALLOCATION_OUTLETS,
    rounding_unit_lkr: float = ROUNDING_UNIT_LKR,
) -> pd.DataFrame:
    """Allocate the Round 2 trade-spend budget to eligible Western outlets."""

    predictions = read_required_csv(predictions_path, PREDICTION_COLUMNS)
    gold = read_required_csv(gold_features_path, ["Outlet_ID"])

    frame = predictions.merge(
        gold.drop_duplicates("Outlet_ID"),
        on="Outlet_ID",
        how="left",
        validate="one_to_one",
    )
    frame = attach_distributor_from_transactions(frame, transactions_path)

    western_mask, western_source = infer_western_mask(frame)
    eligible = frame.loc[western_mask].copy()
    if eligible.empty:
        raise ValueError(f"No Western Province outlets were found using {western_source}.")

    eligible = build_priority_scores(eligible)
    eligible = eligible.loc[eligible["spend_priority_score"] > 0].copy()
    if eligible.empty:
        raise ValueError("No outlets have a positive spend priority score after filtering.")

    candidates = select_allocation_candidates(
        eligible,
        total_budget_lkr=total_budget_lkr,
        min_allocation_lkr=min_allocation_lkr,
        target_outlet_count=target_outlet_count,
    )
    allocations = allocate_with_constraints(
        candidates["spend_priority_score"],
        total_budget=total_budget_lkr,
        cap=max_allocation_per_outlet_lkr,
        minimum=min_allocation_lkr,
        rounding_unit=rounding_unit_lkr,
    )
    candidates["Trade_Spend_Allocation_LKR"] = allocations

    output = candidates.loc[candidates["Trade_Spend_Allocation_LKR"] > 0, BUDGET_COLUMNS].copy()
    output = output.sort_values("Trade_Spend_Allocation_LKR", ascending=False).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(output_path, index=False)
    print_budget_summary(
        output=output,
        output_path=output_path,
        western_outlets_considered=len(eligible),
        candidate_outlets_selected=len(candidates),
        total_budget_lkr=total_budget_lkr,
        western_source=western_source,
    )
    return output


def read_required_csv(path: Path, required_columns: list[str]) -> pd.DataFrame:
    """Read a CSV and validate required columns."""

    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    df = pd.read_csv(path)
    missing = set(required_columns).difference(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return df


def attach_distributor_from_transactions(frame: pd.DataFrame, transactions_path: Path) -> pd.DataFrame:
    """Attach dominant Distributor_ID if Gold features do not already provide it."""

    if "Distributor_ID" in frame.columns:
        return frame
    if not transactions_path.exists():
        return frame

    usecols = ["Outlet_ID", "Distributor_ID"]
    transactions = pd.read_csv(transactions_path, usecols=lambda col: col in usecols)
    if not set(usecols).issubset(transactions.columns):
        return frame

    distributor = (
        transactions.dropna(subset=["Outlet_ID", "Distributor_ID"])
        .groupby("Outlet_ID")["Distributor_ID"]
        .agg(lambda values: values.mode().iat[0] if not values.mode().empty else values.iloc[0])
        .reset_index()
    )
    return frame.merge(distributor, on="Outlet_ID", how="left")


def infer_western_mask(frame: pd.DataFrame) -> tuple[pd.Series, str]:
    """Infer Western Province eligibility from Province or Distributor_ID."""

    province_column = find_column(frame, ["Province", "province"])
    if province_column:
        province = frame[province_column].fillna("").astype(str).str.strip().str.lower()
        return province.eq("western") | province.eq("western province"), province_column

    distributor_column = find_column(frame, ["Distributor_ID", "distributor_id"])
    if distributor_column:
        distributor = frame[distributor_column].fillna("").astype(str).str.strip()
        return distributor.isin(WESTERN_DISTRIBUTORS), distributor_column

    raise ValueError(
        "Western Province filtering cannot be performed because neither Province "
        "nor Distributor_ID is available in Gold features or Silver transactions."
    )


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Return the first matching column, case-insensitively."""

    lower_to_original = {column.lower(): column for column in df.columns}
    for candidate in candidates:
        match = lower_to_original.get(candidate.lower())
        if match:
            return match
    return None


def build_priority_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Create explainable spend priority components and final score."""

    scored = frame.copy()
    predicted = numeric(scored, "Maximum_Monthly_Liters")
    historical = first_available_numeric(
        scored,
        [
            "recent_avg_monthly_volume_liters",
            "avg_monthly_volume_liters",
            "median_monthly_volume_liters",
            "total_volume_liters",
        ],
    )
    if "total_volume_liters" in scored.columns and historical.name == "total_volume_liters":
        active_months = numeric(scored, "active_month_count").replace(0, np.nan)
        historical = (historical / active_months).fillna(0.0)

    scored["opportunity_gap_liters"] = (predicted - historical).clip(lower=0.0)

    opportunity_score = percentile_score(scored["opportunity_gap_liters"])
    potential_score = percentile_score(predicted)
    historical_score = percentile_score(historical)
    spatial_score = mean_available_scores(
        scored,
        [
            "demand_driver_score_1000m",
            "overall_spatial_gravity_score",
            "commercial_decay_score",
        ],
    )
    confidence_score = mean_available_scores(
        scored,
        [
            "active_transaction_months",
            "active_month_count",
            "Cooler_Count",
        ],
    )
    competition_pressure = mean_available_scores(
        scored,
        [
            "competitor_density_score",
            "market_saturation_index",
        ],
    )
    saturation_penalty = (1.0 - 0.40 * competition_pressure).clip(lower=0.60, upper=1.0)
    low_confidence_penalty = (0.75 + 0.25 * confidence_score).clip(lower=0.75, upper=1.0)

    scored["spatial_demand_score"] = spatial_score
    scored["historical_strength_score"] = historical_score
    scored["confidence_score"] = confidence_score
    scored["competition_pressure_score"] = competition_pressure
    scored["saturation_penalty"] = saturation_penalty
    scored["spend_priority_score"] = (
        0.40 * opportunity_score
        + 0.20 * potential_score
        + 0.18 * spatial_score
        + 0.12 * historical_score
        + 0.10 * confidence_score
    ) * saturation_penalty * low_confidence_penalty

    fallback = percentile_score(predicted)
    scored.loc[scored["spend_priority_score"].le(0), "spend_priority_score"] = fallback
    return scored


def select_allocation_candidates(
    eligible: pd.DataFrame,
    total_budget_lkr: float,
    min_allocation_lkr: float,
    target_outlet_count: int,
) -> pd.DataFrame:
    """Select a practical top-N candidate set before allocating spend."""

    if min_allocation_lkr <= 0:
        max_meaningful_outlets = len(eligible)
    else:
        max_meaningful_outlets = int(total_budget_lkr // min_allocation_lkr)

    candidate_count = min(len(eligible), target_outlet_count, max_meaningful_outlets)
    if candidate_count <= 0:
        raise ValueError("Budget is too small to fund even one outlet at the configured minimum allocation.")

    return (
        eligible.sort_values(
            ["spend_priority_score", "opportunity_gap_liters", "Maximum_Monthly_Liters"],
            ascending=False,
        )
        .head(candidate_count)
        .copy()
    )


def numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric column or a zero series if unavailable."""

    if column not in df.columns:
        return pd.Series(0.0, index=df.index, name=column)
    return pd.to_numeric(df[column], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)


def first_available_numeric(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Return the first available numeric signal from a candidate list."""

    for column in columns:
        if column in df.columns:
            return numeric(df, column)
    return pd.Series(0.0, index=df.index, name="missing_historical_baseline")


def mean_available_scores(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Average percentile scores for columns that exist."""

    scores = [percentile_score(numeric(df, column)) for column in columns if column in df.columns]
    if not scores:
        return pd.Series(0.5, index=df.index)
    return pd.concat(scores, axis=1).mean(axis=1).fillna(0.5)


def percentile_score(values: pd.Series) -> pd.Series:
    """Convert a numeric series to a 0-1 percentile score."""

    numeric_values = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    if numeric_values.nunique(dropna=True) <= 1:
        return pd.Series(0.5 if numeric_values.max() > 0 else 0.0, index=values.index)
    return numeric_values.rank(pct=True, method="average").fillna(0.0).clip(0.0, 1.0)


def capped_proportional_allocation(scores: pd.Series, total_budget: float, cap: float) -> pd.Series:
    """Allocate proportionally while enforcing a per-outlet cap."""

    remaining_budget = float(total_budget)
    remaining_scores = pd.to_numeric(scores, errors="coerce").fillna(0.0).clip(lower=0.0)
    allocation = pd.Series(0.0, index=scores.index)

    while remaining_budget > 0 and remaining_scores.gt(0).any():
        weights = remaining_scores / remaining_scores.sum()
        proposed = weights * remaining_budget
        capped = proposed >= cap

        if not capped.any():
            allocation += proposed
            break

        capped_index = proposed.loc[capped].index
        allocation.loc[capped_index] += cap
        remaining_budget -= cap * len(capped_index)
        remaining_scores.loc[capped_index] = 0.0

        if remaining_budget <= 0:
            break

    return allocation.clip(lower=0.0, upper=cap)


def allocate_with_constraints(
    scores: pd.Series,
    total_budget: float,
    cap: float,
    minimum: float,
    rounding_unit: float,
) -> pd.Series:
    """Allocate nearly the full budget with cap, minimum, and rounding rules."""

    active_scores = pd.to_numeric(scores, errors="coerce").fillna(0.0).clip(lower=0.0)
    active_scores = active_scores.loc[active_scores > 0]
    if active_scores.empty:
        return pd.Series(0.0, index=scores.index)

    while True:
        raw = capped_proportional_allocation(active_scores, total_budget=total_budget, cap=cap)
        below_minimum = raw.loc[(raw > 0) & (raw < minimum)]
        if below_minimum.empty or len(raw) == 1:
            break

        active_scores = active_scores.drop(index=below_minimum.index)
        if active_scores.empty:
            top_index = pd.to_numeric(scores, errors="coerce").idxmax()
            active_scores = pd.Series({top_index: 1.0})
        continue

    rounded = round_down_to_unit(raw, rounding_unit=rounding_unit).clip(lower=0.0, upper=cap)
    rounded.loc[(rounded > 0) & (rounded < minimum)] = 0.0
    rounded = distribute_rounding_remainder(
        allocations=rounded,
        scores=active_scores,
        total_budget=total_budget,
        cap=cap,
        minimum=minimum,
        rounding_unit=rounding_unit,
    )

    output = pd.Series(0.0, index=scores.index)
    output.loc[rounded.index] = rounded
    return output


def round_down_to_unit(values: pd.Series, rounding_unit: float) -> pd.Series:
    """Round down to the configured unit so total spend never exceeds budget."""

    if rounding_unit <= 0:
        return pd.to_numeric(values, errors="coerce").fillna(0.0)
    numeric_values = pd.to_numeric(values, errors="coerce").fillna(0.0)
    return np.floor(numeric_values / rounding_unit) * rounding_unit


def distribute_rounding_remainder(
    allocations: pd.Series,
    scores: pd.Series,
    total_budget: float,
    cap: float,
    minimum: float,
    rounding_unit: float,
) -> pd.Series:
    """Redistribute rounded remainder without exceeding caps or budget."""

    adjusted = allocations.copy()
    if rounding_unit <= 0:
        return adjusted

    priority_order = scores.sort_values(ascending=False).index.tolist()
    while total_budget - float(adjusted.sum()) >= rounding_unit:
        changed = False
        for index in priority_order:
            remainder = total_budget - float(adjusted.sum())
            if remainder < rounding_unit:
                break
            current = float(adjusted.get(index, 0.0))
            if current <= 0 and remainder < minimum:
                continue
            if current + rounding_unit <= cap:
                adjusted.loc[index] = current + rounding_unit
                changed = True
        if not changed:
            break
    return adjusted


def print_budget_summary(
    output: pd.DataFrame,
    output_path: Path,
    western_outlets_considered: int,
    candidate_outlets_selected: int,
    total_budget_lkr: float,
    western_source: str,
) -> None:
    """Print spend allocation diagnostics."""

    allocations = pd.to_numeric(output["Trade_Spend_Allocation_LKR"], errors="coerce").fillna(0.0)
    total_allocated = float(allocations.sum())
    print(f"Western filter source: {western_source}")
    print(f"Western outlets considered: {western_outlets_considered}")
    print(f"Candidate outlets selected: {candidate_outlets_selected}")
    print(f"Outlets receiving allocation: {len(output)}")
    print(f"Total allocated: {total_allocated:.2f} LKR")
    print(f"Remaining budget: {total_budget_lkr - total_allocated:.2f} LKR")
    if len(output):
        print(f"Min allocation: {allocations.min():.2f}")
        print(f"Median allocation: {allocations.median():.2f}")
        print(f"Mean allocation: {allocations.mean():.2f}")
        print(f"Max allocation: {allocations.max():.2f}")
        print("Top 10 allocations:")
        print(output.head(10).to_string(index=False))
    print(f"Output path: {output_path}")


def main() -> None:
    allocate_budget()


if __name__ == "__main__":
    main()
