# DataStorm 7.0 - Team Jarvis

## Project Overview

This project estimates latent maximum monthly purchase potential in liters for retail outlets for January 2026.

Core idea:

```text
Observed Sales = min(True Demand Potential, Constraints)
```

Therefore, the goal is to estimate hidden true demand potential, not simply historical sales.

## Team Roles

| Member | Role | Main Ownership |
|---|---|---|
| Member 1 | Data Architect | Bronze/Silver pipeline, data quality checks, rejected records |
| Member 2 | Geospatial & Features Lead | POI data, feature engineering, Gold dataset |
| Member 3 | Lead Data Scientist | Latent potential methodology, modeling, final predictions |

## Repository Structure

- `data/`: Local data layers for raw, Bronze, Silver, Gold, external, and rejected records.
- `notebooks/`: Starter notebooks for forensics, POI features, modeling, and final validation.
- `src/`: Python packages for reusable data, quality, POI, feature, model, and pipeline code.
- `reports/`: EDA notes, final report assets, GenAI usage log, and decision log.
- `submissions/`: Final competition submission files.

## Setup Instructions

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Download dataset files from Kaggle and place them inside `data/raw/`. Raw data files are not committed to GitHub.

## Pipeline Plan

```text
Raw data
-> Bronze
-> Silver
-> Gold
-> Modeling
-> Final submission CSV
```

Run the Member 1 Bronze/Silver handoff pipeline from the repository root:

```bash
python3 -m src.data.silver_pipeline
```

The command expects the Kaggle CSV files in `data/raw/` and writes cleaned Silver tables, rejected-record audit files, and report summaries. Key handoff outputs are:

- `data/silver/monthly_outlet_volume.csv`
- `data/silver/clean_outlet_locations.csv`
- `data/silver/outlet_base_features.csv`
- `reports/eda/rejection_summary_by_dataset.csv`
- `reports/eda/rejection_summary_by_reason.csv`
- `reports/eda/warning_summary.csv`
- `reports/eda/correction_summary.csv`

## Final Deliverables

- `submissions/teamname_predictions.csv`
- Reproducible codebase
- `reports/final/final_report.pdf`

## Notes

Raw data files and generated intermediate datasets are not committed to GitHub.
