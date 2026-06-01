# Spatial Features

Round 2 spatial modules will extend the preliminary-round POI features into richer location intelligence.

Planned modules:

- `distance_decay_features.py`: distance-decay POI features where closer POIs have stronger impact than farther POIs.
- `competitor_density.py`: nearby outlet density, competitor pressure, market saturation, isolated outlet flags, and local density ranks.

Expected inputs:

- Cleaned Silver outlet coordinates and outlet master data.
- Curated POI feature outputs from the existing POI pipeline.
- Future competitor/outlet density reference tables if approved.

Expected outputs:

- Outlet-level spatial feature tables for the Gold layer.
- Feature documentation for modeling and XAI.

Use cleaned Silver coordinates only. Do not use raw coordinates for spatial feature generation.
