# Round 2 Validation Checklist

This checklist tracks checks that still require final local validation after the Round 2 pipeline is run. Do not mark items complete unless the command output has been reviewed.

## Commands

```bash
python -m src.pipeline.make_round2_submission
python -m src.pipeline.validate_round2_submission
streamlit run app/streamlit_app.py
```

## Output Files

- [ ] `submissions/jarvis_predictions.csv` exists.
- [ ] `submissions/jarvis_budget_allocations.csv` exists.

## Prediction CSV

- [ ] Required columns only: `Outlet_ID`, `Maximum_Monthly_Liters`.
- [ ] No missing `Outlet_ID` values.
- [ ] No duplicate `Outlet_ID` values.
- [ ] No missing predictions.
- [ ] Predictions are positive.
- [ ] Row count matches `data/silver/outlet_master.csv`.

## Budget Allocation CSV

- [ ] Required columns only: `Outlet_ID`, `Trade_Spend_Allocation_LKR`.
- [ ] No missing `Outlet_ID` values.
- [ ] No duplicate `Outlet_ID` values.
- [ ] Spend allocation values are non-negative.
- [ ] Total budget allocation is less than or equal to LKR 5,000,000.
- [ ] Western Province filter is applied correctly.

## App and XAI

- [ ] Web app runs locally.
- [ ] XAI fallback works without API key.
- [ ] App handles missing local output files with friendly run instructions.

## Documentation

- [ ] README has final Round 2 run instructions.
- [ ] Generated CSV files are not staged or committed.
