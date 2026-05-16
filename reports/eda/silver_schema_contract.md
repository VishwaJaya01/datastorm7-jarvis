# Silver Schema Contract

This contract defines the Silver-layer files consumed by POI enrichment and modeling.

## Row Counts

| File | Silver Rows | Expectation |
|---|---:|---|
| outlet_master.csv | 20000 | One row per retained outlet; missing `Outlet_Size` is retained as `Unknown`. |
| outlet_coordinates.csv | 19960 | Only outlets with usable `valid` or `corrected` coordinates. |
| transactions_history_final.csv | 2339409 | Clean transaction history with positive volume/value and valid FKs. |
| distributor_seasonality_details.csv | 360 | One row per distributor/year/month. |
| holiday_list.csv | 256 | Exact duplicate holidays removed; distinct same-date holidays preserved. |

## File Schemas

| File | Columns | Domains / Notes |
|---|---|---|
| outlet_master.csv | `Outlet_ID`, `Outlet_Size`, `Cooler_Count`, `Outlet_Type`, `outlet_size_status`, `coord_status`, `has_valid_coord` | `Outlet_Size`: Small/Medium/Large/Extra Large/Unknown. `outlet_size_status`: provided/missing. `coord_status`: valid/corrected/quarantined/missing. |
| outlet_coordinates.csv | `Outlet_ID`, `Latitude`, `Longitude`, `coord_status` | Coordinates are inside Sri Lanka bounds; `coord_status` is valid/corrected only. |
| transactions_history_final.csv | `Outlet_ID`, `Year`, `Month`, `Distributor_ID`, `SKU_ID`, `Volume_Liters`, `Total_Bill_Value` | Year 2023-2025, month 1-12, positive volume and bill value. |
| distributor_seasonality_details.csv | `Distributor_ID`, `Year`, `Month`, `Seasonality_Index` | `Seasonality_Index`: Moderate/Favorable/Un-Favorable after normalization. |
| holiday_list.csv | `Date`, `Holiday_Name`, `Holiday_Type` | `Date` is ISO `YYYY-MM-DD`; exact duplicates removed. |

## Referential Integrity

- `transactions_history_final.Outlet_ID` must exist in `outlet_master.Outlet_ID`.
- `transactions_history_final.Distributor_ID` must be one of the 10 competition distributor IDs.
- `outlet_coordinates.Outlet_ID` must exist in `outlet_master.Outlet_ID`.
- `outlet_master[has_valid_coord=True].Outlet_ID` must exactly match `outlet_coordinates.Outlet_ID`.
- Outlets with `coord_status` of `quarantined` or `missing` must not appear in `outlet_coordinates.csv`.
