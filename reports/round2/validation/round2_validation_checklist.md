# Round 2 Validation Checklist

This checklist records the final local validation evidence for the current Round 2 pipeline outputs.

## Commands

```bash
python -m src.pipeline.make_round2_submission
python -m src.pipeline.validate_round2_submission
streamlit run app/streamlit_app.py
```

## Output Files

- [x] `submissions/jarvis_predictions.csv` exists.
- [x] `submissions/jarvis_budget_allocations.csv` exists.

## Prediction CSV

- [x] Required columns only: `Outlet_ID`, `Maximum_Monthly_Liters`.
- [x] No missing `Outlet_ID` values.
- [x] No duplicate `Outlet_ID` values.
- [x] No missing predictions.
- [x] Predictions are positive.
- [x] Row count matches `data/silver/outlet_master.csv`.

Evidence:

- Prediction rows: 20,000
- Missing predictions: 0
- Duplicate `Outlet_ID`s: 0
- Median: 111.9846
- Mean: 302.9689
- Max: 1857.8529

## Budget Allocation CSV

- [x] Required columns only: `Outlet_ID`, `Trade_Spend_Allocation_LKR`.
- [x] No missing `Outlet_ID` values.
- [x] No duplicate `Outlet_ID` values.
- [x] Spend allocation values are non-negative.
- [x] Total budget allocation is less than or equal to LKR 5,000,000.
- [x] Western Province filter is applied correctly.

Evidence:

- Western outlets considered: 9,000
- Outlets funded: 300
- Total allocation: LKR 5,000,000
- Remaining budget: LKR 0

## App and XAI

- [x] Web app runs locally.
- [x] XAI fallback works without API key.
- [x] App handles missing local output files with friendly run instructions.

## Documentation

- [x] README has final Round 2 run instructions.
- [x] Generated CSV files are not staged or committed.
