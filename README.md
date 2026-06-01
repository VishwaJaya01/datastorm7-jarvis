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

Run the final reproducible pipeline from the repository root:

```bash
python -m src.data.silver_pipeline
python -m src.poi.scrape_poi_features
python -m src.features.build_master_features
python -m src.pipeline.make_submission
python -m src.pipeline.validate_submission
```

The Silver command expects the Kaggle CSV files in `data/raw/` and writes cleaned Silver tables, rejected-record audit files, and report summaries. Key handoff outputs are:

- `data/silver/monthly_outlet_volume.csv`
- `data/silver/clean_outlet_locations.csv`
- `data/silver/outlet_base_features.csv`
- `reports/eda/rejection_summary_by_dataset.csv`
- `reports/eda/rejection_summary_by_reason.csv`
- `reports/eda/warning_summary.csv`
- `reports/eda/correction_summary.csv`

## Member 3 Modeling Pipeline

Generate the final Team Jarvis submission:

```bash
python -m src.pipeline.make_submission
```

Validate the submission file:

```bash
python -m src.pipeline.validate_submission
```

The modeling pipeline uses `data/gold/master_features.csv` when available and falls back to the Silver-only baseline if the Gold table is missing.

## Round 2 / Prototype Round Extension

This repository continues from the DataStorm 7.0 preliminary round. The existing Round 1 Bronze -> Silver -> Gold pipeline remains the foundation for Round 2 work.

Round 2 adds:

- Distance-decay spatial features
- Competitor density and market saturation features
- Western Province LKR 5 million spend optimization
- XAI explanations
- Outlet Intelligence Web App
- Round 2 prediction and budget allocation outputs

Final Round 2 commands:

```bash
python -m src.data.silver_pipeline
python -m src.spatial.competitor_density
python -m src.poi.scrape_poi_features
python -m src.features.build_spatial_decay
python -m src.features.build_master_features
python -m src.pipeline.make_round2_submission
python -m src.pipeline.validate_round2_submission
streamlit run app/streamlit_app.py
```

Round 2 outputs:

- `submissions/jarvis_predictions.csv`
- `submissions/jarvis_budget_allocations.csv`

The app can run without an API key using deterministic XAI fallback explanations from structured outlet facts. An optional LLM/API explanation layer can be added later, but generated explanations must use only provided facts and must not change predictions or budget allocations.

Optional LLM explanations can be enabled locally with Streamlit secrets or environment variables:

```text
USE_LLM_EXPLANATIONS=true
GEMINI_API_KEY=your_local_key_here
```

Do not commit API keys or local secrets.

Raw files, generated intermediate datasets, and submission CSV outputs should not be committed.

## Final Deliverables

- `submissions/teamname_predictions.csv`
- Reproducible codebase
- `reports/final/final_report.pdf`

## Notes

Raw data files and generated intermediate datasets are not committed to GitHub.
