# Baseline V1 Validation Summary

## Model Version

**Version:** Baseline V1  
**Mode:** Silver-only baseline  
**Generated from:** Cleaned Silver data  
**Output file:** `submissions/teamname_predictions.csv`

## Validation Result

The Silver-only baseline submission passed validation successfully.

| Check | Result |
|---|---|
| Total outlet predictions | 20,000 |
| Missing predictions | 0 |
| Duplicate Outlet_IDs | 0 |
| Negative / zero predictions | 0 |
| Required columns present | Yes |
| Output columns | `Outlet_ID`, `Maximum_Monthly_Liters` |

## Prediction Distribution

| Metric | Maximum_Monthly_Liters |
|---|---:|
| Min | 27.9198 |
| P25 | 84.7895 |
| Median | 112.2097 |
| Mean | 302.4475 |
| P75 | 253.6888 |
| P90 | 746.9462 |
| P95 | 830.4214 |
| P99 | 1721.3879 |
| Max | 1853.9992 |

## Outlet Size Sanity Check

The baseline output shows a sensible relationship between outlet size and estimated potential:

| Outlet Size | Mean Monthly Potential |
|---|---:|
| Small | 95.23 |
| Medium | 238.15 |
| Large | 735.56 |
| Extra Large | 1664.50 |
| Unknown | 99.82 |

This is directionally reasonable because larger outlets are expected to have higher monthly purchase potential.

## Notes

- The first baseline uses only Silver-layer data.
- It does not yet use Member 2’s Gold/POI feature table.
- The output is valid for submission format, but it should be improved using Gold features once available.
- The top predictions are capped around 1854 liters, which prevents uncontrolled extreme values.
- The baseline is explainable and conservative, making it useful as a fallback model.

## Gold-Enhanced Final Candidate Validation

## Model Version

**Version:** Gold-enhanced final candidate  
**Mode:** Gold-enhanced  
**Generated from:** Cleaned Silver data plus Gold/POI features  
**Output file:** `submissions/teamname_predictions.csv`

## Validation Result

The Gold-enhanced final candidate passed validation successfully.

| Check | Result |
|---|---|
| Total outlet predictions | 20,000 |
| Missing predictions | 0 |
| Duplicate Outlet_IDs | 0 |
| Negative / zero predictions | 0 |
| Required columns present | Yes |
| Output columns | `Outlet_ID`, `Maximum_Monthly_Liters` |

## Prediction Distribution

| Metric | Maximum_Monthly_Liters |
|---|---:|
| Min | 27.7537 |
| P25 | 84.6281 |
| Median | 111.9242 |
| Mean | 303.1323 |
| P75 | 253.9870 |
| P90 | 749.3471 |
| Max | 1860.1664 |

## Notes

- The final candidate uses the Gold feature table generated from Silver outlets and POI v2 features.
- All 20,000 required outlets are represented.
- POI-blind outlets are retained with safe zero-filled POI signals.
- The prediction distribution remains close to the Silver-only baseline while incorporating the Gold feature layer.
