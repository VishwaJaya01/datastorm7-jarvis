# Modeling Methodology Draft

## Objective

Team Jarvis estimates each outlet's latent maximum monthly purchase potential in liters for January 2026.

## Why Historical Sales Are Censored

Observed historical sales are not always equal to true demand. An outlet may have wanted to purchase more volume but been constrained by stockouts, credit limits, delivery capacity, assortment gaps, or operational rules.

```text
Observed Sales = min(True Demand Potential, Constraints)
```

The modeling goal is therefore to estimate hidden potential, not simply reproduce average historical sales.

## Baseline Potential

The first model starts with an explainable Silver-only baseline. Transactions are aggregated to outlet-month volume, then each outlet receives summary statistics such as average, median, p75, p90, max monthly volume, active month count, total volume, and average bill value.

The baseline potential uses a conservative uncapping formula:

```text
max(
  recent average monthly volume,
  p75 monthly volume,
  0.85 * p90 monthly volume,
  0.70 * max monthly volume
)
```

A small activity-based uplift is applied when the outlet has enough historical coverage. Sparse outlets are not aggressively uplifted.

## Seasonality

The target month is January 2026. Distributor-level January seasonality is inferred from historical January records using simple multipliers:

- Favorable: 1.08
- Moderate: 1.00
- Un-Favorable: 0.92

Missing seasonality defaults to 1.00. This keeps the adjustment transparent and avoids overfitting.

## Peer Benchmarking

Peer benchmarking compares each outlet with similar outlets using `Outlet_Type` and `Outlet_Size`. The method uses conservative peer p75/p90 benchmarks and fallback groups:

1. `Outlet_Type` + `Outlet_Size`
2. `Outlet_Type`
3. Global benchmark

Peer estimates are capped relative to the outlet baseline when historical data exists, preventing unrealistic jumps.

## Avoiding Overinflation

The first version avoids overinflating potential by:

- Using p75 and discounted p90/max terms instead of raw maximum sales.
- Applying only small activity uplifts.
- Capping peer benchmark impact for outlets with history.
- Blending baseline, seasonality, and peer values with conservative weights.
- Enforcing positive predictions and a high-percentile distribution cap.

## Gold and POI Integration

If `data/gold/master_features.csv` becomes available, the pipeline can run in Gold-enhanced mode. It safely detects numeric Gold columns without assuming exact POI names and applies only a small conservative multiplier. This allows Member 2's POI/catchment signals to improve ranking later without replacing the Silver evidence.

## Baseline V1 Result

The first working model is a **Silver-only explainable baseline**. It estimates latent outlet potential using cleaned historical transaction data, January seasonality adjustment, and peer benchmarking.

The baseline passed the submission validation checks:

- 20,000 outlet predictions generated
- No missing predictions
- No duplicate `Outlet_ID`s
- All predictions are positive
- Output contains the required columns only: `Outlet_ID` and `Maximum_Monthly_Liters`

The prediction distribution was reasonable for a first conservative model:

- Median: 112.21 liters
- Mean: 302.45 liters
- P90: 746.95 liters
- Max: 1854.00 liters

The outlet-size sanity check also showed a logical increasing pattern:

- Small outlets: approximately 95L mean potential
- Medium outlets: approximately 238L mean potential
- Large outlets: approximately 736L mean potential
- Extra Large outlets: approximately 1665L mean potential

This gives confidence that the baseline captures basic outlet capacity differences without requiring a black-box model.

## Gold-Enhanced Final Candidate Result

The Gold-enhanced model validation passed with 20,000 outlet predictions, no missing predictions, no duplicate `Outlet_ID`s, and all positive values. The final median potential was 111.92L, mean was 303.13L, P90 was 749.35L, and max was 1860.17L.

The Gold table is generated from all Silver outlet master rows and joined with POI v2 features. Outlets without valid coordinates are preserved as POI-blind rather than dropped, keeping the submission aligned with the required 20,000-outlet coverage.

## Methodology Summary

Our first model is a Silver-only explainable baseline. It estimates outlet potential using high-but-credible historical monthly sales, January distributor seasonality, and peer benchmarking. It avoids overinflating predictions through conservative blending and sanity caps.

Historical sales are treated as censored observations because observed sales may be limited by stockouts, credit limits, delivery constraints, or poor outlet execution. Therefore, the model does not simply use average historical sales. Instead, it uses high but credible historical performance signals, then blends them with peer-group potential and seasonality.

This baseline acts as a safe fallback model. Once the Gold feature table from Member 2 is available, the model can be rerun in Gold-enhanced mode to incorporate POI and catchment signals.

## Limitations

This first version is a transparent baseline, not a final optimized model. It does not yet learn nonlinear interactions, SKU mix effects, explicit constraint probabilities, or detailed POI feature importance. It is designed to produce a valid, explainable first submission and create a stable foundation for later model improvements.
