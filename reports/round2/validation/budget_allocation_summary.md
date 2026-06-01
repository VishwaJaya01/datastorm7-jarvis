# Round 2 Budget Allocation Summary

## Output Files

| Output | Path | Status |
|---|---|---|
| Prediction CSV | `submissions/jarvis_predictions.csv` | Generated locally |
| Budget allocation CSV | `submissions/jarvis_budget_allocations.csv` | Generated locally |

## Prediction Validation Evidence

| Check | Result |
|---|---:|
| Prediction rows | 20,000 |
| Missing predictions | 0 |
| Duplicate `Outlet_ID`s | 0 |
| Median `Maximum_Monthly_Liters` | 111.9846 |
| Mean `Maximum_Monthly_Liters` | 302.9689 |
| Max `Maximum_Monthly_Liters` | 1857.8529 |

## Budget Allocation Evidence

| Check | Result |
|---|---:|
| Western outlets considered | 9,000 |
| Candidate outlets selected | 300 |
| Outlets funded | 300 |
| Total allocation | LKR 5,000,000 |
| Remaining budget | LKR 0 |
| Minimum allocation | LKR 15,500 |
| Median allocation | LKR 16,500 |
| Mean allocation | LKR 16,666.67 |
| Maximum allocation | LKR 19,100 |

## Allocation Method

The Round 2 allocator filters to Western Province outlets using `Province` when available, otherwise using Western distributor IDs: `DIST_W_01`, `DIST_W_02`, and `DIST_W_03`.

Eligible outlets are ranked with an explainable priority score using available facts:

- opportunity gap between predicted potential and historical baseline
- predicted monthly potential
- historical baseline strength
- POI and spatial demand signals
- active transaction history and cooler capacity
- competitor density and market saturation penalties

The final allocation funds the top 300 eligible outlets by priority score, applies a minimum meaningful allocation, caps each outlet at LKR 100,000, rounds to LKR 100 units, and redistributes rounding remainder without exceeding the LKR 5,000,000 budget.

## App Evidence

The Streamlit app starts locally with:

```bash
streamlit run app/streamlit_app.py
```

The app does not require an API key. It uses deterministic explanations by default and only attempts optional LLM explanations when `USE_LLM_EXPLANATIONS=true` and `GEMINI_API_KEY` are configured.
