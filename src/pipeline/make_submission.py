"""Generate Team Jarvis January 2026 potential predictions."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.models.baseline_potential import build_baseline_potential, load_transactions
from src.models.final_blend import build_final_predictions, load_gold_features
from src.models.peer_benchmark import build_peer_benchmarks
from src.models.seasonality import apply_january_seasonality, load_seasonality


OUTLET_MASTER_PATH = Path("data/silver/outlet_master.csv")
TRANSACTIONS_PATH = Path("data/silver/transactions_history_final.csv")
SEASONALITY_PATH = Path("data/silver/distributor_seasonality_details.csv")
GOLD_FEATURES_PATH = Path("data/gold/master_features.csv")
OUTPUT_PATH = Path("submissions/teamname_predictions.csv")


def load_outlet_master(path: Path = OUTLET_MASTER_PATH) -> pd.DataFrame:
    """Load Silver outlet master and validate minimum required fields."""

    if not path.exists():
        raise FileNotFoundError(
            f"Silver outlet master not found: {path}. "
            "Run the Data Architect Silver pipeline before modeling."
        )

    outlet_master = pd.read_csv(path)
    required = {"Outlet_ID"}
    missing = required.difference(outlet_master.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return outlet_master


def make_submission(
    outlet_master_path: Path = OUTLET_MASTER_PATH,
    transactions_path: Path = TRANSACTIONS_PATH,
    seasonality_path: Path = SEASONALITY_PATH,
    gold_features_path: Path = GOLD_FEATURES_PATH,
    output_path: Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Run the Silver-only or Gold-enhanced modeling pipeline."""

    outlet_master = load_outlet_master(outlet_master_path)
    transactions = load_transactions(transactions_path)
    seasonality = load_seasonality(seasonality_path)
    gold_features = load_gold_features(gold_features_path)

    baseline = build_baseline_potential(transactions)
    seasonality_adjusted = apply_january_seasonality(baseline, transactions, seasonality)
    peer_benchmark = build_peer_benchmarks(outlet_master, baseline)
    predictions = build_final_predictions(
        outlet_master=outlet_master,
        baseline=baseline,
        seasonality_adjusted=seasonality_adjusted,
        peer_benchmark=peer_benchmark,
        gold_features=gold_features,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output_path, index=False)
    print_submission_summary(predictions, output_path, gold_features is not None)
    return predictions


def print_submission_summary(predictions: pd.DataFrame, output_path: Path, used_gold_features: bool) -> None:
    """Print the core diagnostics needed before submission."""

    values = pd.to_numeric(predictions["Maximum_Monthly_Liters"], errors="coerce")
    print(f"Mode: {'Gold-enhanced' if used_gold_features else 'Silver-only baseline'}")
    print(f"Number of outlets in output: {len(predictions)}")
    print(f"Number of missing predictions: {int(values.isna().sum())}")
    print(f"Number of duplicate Outlet_IDs: {int(predictions['Outlet_ID'].duplicated().sum())}")
    print(f"Min prediction: {values.min():.4f}")
    print(f"Median prediction: {values.median():.4f}")
    print(f"Mean prediction: {values.mean():.4f}")
    print(f"Max prediction: {values.max():.4f}")
    print(f"Output path: {output_path}")


def main() -> None:
    make_submission()


if __name__ == "__main__":
    main()
