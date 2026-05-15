# Data Forensics & Pipeline

## Pipeline Summary

Member 1 implemented a reproducible Bronze -> Silver -> Rejected pipeline. Bronze stores exact raw CSV copies. Silver contains cleaned, model-ready tables. Rejected records are written separately with `source_file`, `check_name`, `failure_reason`, and `rejected_at` so no failed record is silently dropped.

| Dataset | Raw Rows | Bronze Rows | Silver Rows | Hard Rejected Rows | Hard Rejected Events | Warning Events | Corrected Rows | Action Taken |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| outlet_master | 20000 | 20000 | 20000 | 0 | 0 | 196 | 0 | Standardized outlet categories; retained missing Outlet_Size as Unknown with warning flag. |
| outlet_coordinates | 20000 | 20000 | 19960 | 40 | 80 | 0 | 200 | Corrected safe lat/lon swaps; removed unusable coordinates from Silver and surfaced coord_status on outlets. |
| distributor_seasonality_details | 360 | 360 | 360 | 0 | 0 | 0 | 0 | Canonicalized seasonality labels and validated distributor-month keys. |
| holiday_list | 349 | 349 | 256 | 93 | 93 | 0 | 0 | Removed exact duplicate holidays and preserved distinct same-date holidays. |
| transactions_history_final | 2376389 | 2376389 | 2339409 | 36980 | 41846 | 0 | 0 | Rejected non-positive values, duplicate composite keys, invalid dates, and FK violations. |

## Main Issues Found

- `outlet_master.csv`: normalized category typos/spacing (`Grocry`, `Bakry`, ` Eatery `, `small`) and retained missing outlet sizes as `Unknown` with `outlet_size_status = missing`.
- `outlet_coordinates.csv`: detected impossible coordinates, corrected swapped latitude/longitude only when the corrected pair fit Sri Lanka bounds, and exposed `coord_status`/`has_valid_coord` on Silver outlets.
- `transactions_history_final.csv`: rejected non-positive sales values, invalid dates, orphan outlet/distributor IDs, and duplicate outlet-month-distributor-SKU keys after the first occurrence.
- `distributor_seasonality_details.csv`: normalized seasonality casing/hyphenation before validating canonical labels (`Moderate`, `Favorable`, `Un-Favorable`).
- `holiday_list.csv`: parsed holiday dates and removed exact duplicate holiday records while preserving multiple different holidays on the same date.

## Silver Coordinate Contract

`coord_status` uses four values: `valid` and `corrected` have usable Silver coordinate rows; `quarantined` had a coordinate row that failed DQ; `missing` means no coordinate row was supplied for that outlet. `has_valid_coord` is true only for `valid` and `corrected` outlets.

## Business Impact

The Silver layer protects downstream POI enrichment and latent-potential modeling from legacy SFA/ERP artifacts such as impossible store locations, negative sales, duplicated records, and decayed master data. Outlets marked `quarantined` or `missing` for coordinates are POI-blind, so Members 2 and 3 can treat their geographic potential signals separately instead of silently assuming location quality. Missing outlet size is retained rather than dropped because excluding those outlets would risk incomplete final predictions. The rejected and warning layers preserve auditability for judging and let the team revisit quarantined records later if a modeling recovery rule is justified.
