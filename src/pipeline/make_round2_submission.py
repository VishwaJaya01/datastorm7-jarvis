"""Create the two required Round 2 submission outputs."""

from __future__ import annotations

from pathlib import Path

from src.optimization.budget_allocator import allocate_budget
from src.pipeline.make_submission import make_submission


PREDICTION_OUTPUT_PATH = Path("submissions/jarvis_predictions.csv")
BUDGET_OUTPUT_PATH = Path("submissions/jarvis_budget_allocations.csv")


def make_round2_submission(
    prediction_output_path: Path = PREDICTION_OUTPUT_PATH,
    budget_output_path: Path = BUDGET_OUTPUT_PATH,
) -> tuple[object, object]:
    """Generate Round 2 latent-potential predictions and spend allocations."""

    print("Generating Round 2 prediction output...")
    predictions = make_submission(output_path=prediction_output_path)

    print("\nGenerating Round 2 budget allocation output...")
    allocations = allocate_budget(
        predictions_path=prediction_output_path,
        output_path=budget_output_path,
    )

    print("\nRound 2 outputs created successfully.")
    print(f"Prediction output: {prediction_output_path}")
    print(f"Budget allocation output: {budget_output_path}")
    return predictions, allocations


def main() -> None:
    make_round2_submission()


if __name__ == "__main__":
    main()
