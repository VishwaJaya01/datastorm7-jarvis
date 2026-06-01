# DataStorm 7.0 Prototype Round - Team Jarvis

Team Jarvis built an end-to-end outlet decision engine for DataStorm 7.0 Round 2 / Prototype Round. The solution estimates January 2026 latent maximum monthly outlet purchase potential, allocates a fixed Western Province promotional budget, and provides a Streamlit Outlet Intelligence app for business review and explainability.

Core framing:

```text
Observed Sales = min(True Demand Potential, Operational Constraints)
```

Historical sales are treated as censored observations. The goal is not to predict average historical sales, but to estimate hidden outlet potential under fewer operational constraints.

## Round 2 Deliverables

| Deliverable | Path / Command |
|---|---|
| Potential prediction CSV | `submissions/jarvis_predictions.csv` |
| Budget allocation CSV | `submissions/jarvis_budget_allocations.csv` |
| Outlet Intelligence app | `streamlit run app/streamlit_app.py` |
| Technical paper / pitch deck artifacts | `reports/round2/` and final exported files |
| Reproducible codebase | `src/` pipeline, features, modeling, optimization, XAI, and app code |

Prediction CSV columns:

- `Outlet_ID`
- `Maximum_Monthly_Liters`

Budget allocation CSV columns:

- `Outlet_ID`
- `Trade_Spend_Allocation_LKR`

## Final Round 2 Pipeline

Run from the repository root:

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

Pipeline flow:

```text
Raw Kaggle files
-> Bronze raw preservation
-> Silver cleaned and audited data
-> External POI features
-> Spatial distance-decay and competitor-density features
-> Gold master feature table
-> Latent potential prediction
-> Western Province budget optimization
-> Streamlit app and XAI explanations
```

## Validation Snapshot

Latest local validation evidence:

| Check | Result |
|---|---:|
| Prediction rows | 20,000 |
| Missing predictions | 0 |
| Duplicate `Outlet_ID`s | 0 |
| Median prediction | 111.9846 L |
| Mean prediction | 302.9689 L |
| Max prediction | 1857.8529 L |
| Western outlets considered | 9,000 |
| Funded Western Province outlets | 300 |
| Total budget allocated | LKR 5,000,000 |
| Remaining budget | LKR 0 |
| Streamlit app local startup | Passed |

## Team Roles

| Member | Role | Main Ownership |
|---|---|---|
| Jalina Hirushan | Data Architect | Bronze/Silver pipeline, data quality checks, rejected records |
| Judith Fernando | Geospatial & Features Lead | POI data, spatial features, Gold dataset |
| Vishwa Jayasankha | Team Leader / Lead Data Scientist | Latent potential methodology, modeling, optimization, XAI, final outputs |

## Repository Structure

- `data/`: Local raw, Bronze, Silver, Gold, external, and rejected data layers.
- `src/data/`: Bronze/Silver data engineering pipeline.
- `src/poi/`: POI scraping and external geospatial feature generation.
- `src/spatial/`: Competitor-density and spatial signal modules.
- `src/features/`: Gold feature table builders.
- `src/models/`: Explainable latent-potential modeling components.
- `src/optimization/`: Western Province trade-spend allocation.
- `src/pipeline/`: Submission generation and validation orchestration.
- `src/xai/`: Deterministic and optional LLM explanation helpers.
- `app/`: Streamlit Outlet Intelligence app.
- `reports/`: EDA, validation, decision logs, GenAI logs, and final reporting artifacts.
- `submissions/`: Round 2 prediction and budget allocation outputs.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Place the competition dataset files in:

```text
data/raw/
```

## App and XAI

Run the Outlet Intelligence app:

```bash
streamlit run app/streamlit_app.py
```

The app works without an API key by using deterministic XAI fallback explanations from structured outlet facts.

Optional LLM explanations can be enabled with Streamlit secrets or environment variables:

```text
USE_LLM_EXPLANATIONS=true
GEMINI_API_KEY=<gemini_api_key>
```

LLM explanations are constrained to the provided outlet facts and do not change predictions or budget allocations.

## Preliminary Round Foundation

Round 2 builds on the preliminary-round Bronze -> Silver -> Gold foundation. The original prediction-only pipeline remains useful as a baseline and fallback:

```bash
python -m src.pipeline.make_submission
python -m src.pipeline.validate_submission
```

The Silver pipeline writes cleaned datasets, rejected-record audit files, and report summaries. Key handoff outputs include:

- `data/silver/monthly_outlet_volume.csv`
- `data/silver/clean_outlet_locations.csv`
- `data/silver/outlet_base_features.csv`
- `reports/eda/rejection_summary_by_dataset.csv`
- `reports/eda/rejection_summary_by_reason.csv`
- `reports/eda/warning_summary.csv`
- `reports/eda/correction_summary.csv`
