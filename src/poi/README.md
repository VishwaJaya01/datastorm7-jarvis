# Point of Interest (POI) Engineering Module

This module governs the high-performance extraction, spatial buffering, and indexing of external OpenStreetMap (OSM) data used to build geographical demand features for the 20,000 retail outlets.

---

## Tiled Overpass POI Scrapers

To maximize pipeline stability and circumvent public API rate throttling, execution has been refactored into two modular scripts located under `src/poi/`:

- **`tiled_overpass_poi_scraper.py` (v1):** Preserves the baseline simple query space, tracking schools, bus stops, and hospitals within a strict 500m radius. Kept purely for downstream legacy compatibility.
- **`scrape_poi_features.py` (v2):** **[Current Production Standard]** Features an expanded 11-category POI taxonomy mapped across dual 500m and 1000m catchment buffers, computing explainable demand-driver scoring weights.

> ⚠️ **Pipeline Enforcement:** Always execute **v2** for building the active Gold modeling layer.

---

## Production Execution Commands

### V1 Baseline Extraction

Run from the repository root:

```bash
python -m src.poi.tiled_overpass_poi_scraper
```

**Expected Input:** `data/silver/outlet_coordinates.csv`

**Outputs Compiled:**
- `data/external/osm_pois.csv` — Raw spatial reference points
- `data/silver/outlet_poi_features_v1.csv` — Baseline counts

---

### V2 Enriched Feature Extraction

Run from the repository root:

```bash
python -m src.poi.scrape_poi_features
```

**Expected Input:** `data/silver/outlet_coordinates.csv`

**Outputs Compiled:**
- `data/external/osm_pois_v2.csv` — Raw 11-category spatial points
- `data/silver/outlet_poi_features_FINAL.csv` — Master geospatial feature array

---

## Core Architecture Choices

### 1. Dependency on Silver Coordinates

The scraper explicitly runs using `data/silver/outlet_coordinates.csv` rather than raw files. The Silver Data Forensics pipeline run by Member 1 corrects safe coordinate index swaps and flags unresolvable, corrupted coordinate strings. Scraping against the Silver layer ensures zero network waste on bad coordinates and maintains alignment with downstream datasets.

### 2. Tiled Spatial Querying vs. Iterative Polling

**The Problem:** Querying public Overpass servers via a single iterative loop per store results in continuous `429 Too Many Requests` rate throttling and unrecoverable network drops across 20,000 points.

**The Solution:** The tiled framework splits the Sri Lankan coordinate boundary box into localized `0.25° x 0.25°` grid tiles. It pulls all matching spatial shapes within that block in a single query, caches them locally, and uses a fast scikit-learn BallTree haversine matrix to compute store-level counts offline.

**The Impact:** Cuts total network runtime from 6.5 hours to minutes, while allowing localized re-indexing without making fresh API calls.

### Useful Optimization Flags

```bash
# Expand the grid search tile footprint for lower API call counts
python -m src.poi.scrape_poi_features --tile-size 0.5

# Force-evict the local cache and query OpenStreetMap fresh
python -m src.poi.scrape_poi_features --refresh-overpass
```

> By default, if `osm_pois_v2.csv` is present, the script skips API calls and safely runs local distance calculations.

---

## V2 Taxonomy & Gold Integration Map

The V2 production pipeline extracts 11 distinct socio-economic anchors:

| Category | POI Types |
|---|---|
| **Logistics & Transit** | bus_stops, railway_stations |
| **Public Anchors** | schools, hospitals (includes clinics), religious_places |
| **Commercial Drivers** | supermarkets, markets, restaurants (includes cafes/fast-food), banks_atms, fuel_stations, tourism (hotels/attractions) |

### Extracted Target Features per Store

For every unique outlet, the v2 scraper maps the frequency counts across both 500m and 1000m vectors alongside aggregate metrics:

| Feature | Description |
|---|---|
| `total_poi_500m` / `total_poi_1000m` | Total spatial density |
| `demand_driver_score_500m` / `demand_driver_score_1000m` | Explainable, linearly weighted summation of traffic potential using business-domain rules |
| `poi_available` | Binary flag (True/False) indicating if any external POIs were caught in the catchment area |

---

## Gold Layer Hand-off Instructions

Member 2 handles the ingestion of `data/silver/outlet_poi_features_FINAL.csv` inside `notebooks/02_poi_features.ipynb` to merge it with transaction histories into the final model-ready file: `data/gold/master_feature_table.csv`.

- **Merge Guardrail:** Execute an explicit relational **Left Join** using `Outlet_ID` as the joining primary key.
- **Data Hygiene Requirement:** Stores showing `poi_available = False` represent real isolated retail spots. They contain valid zeros and must **not** be dropped or filtered out of the modeling matrix. Outlets quarantined by data forensics with missing coordinate values are safely handled in the Gold layer notebook using median statistical imputation.