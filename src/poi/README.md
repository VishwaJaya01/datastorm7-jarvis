# Point of Interest (POI) Advanced Feature Engineering

This module governs the high-performance calculation of continuous spatial signals for 20,000 traditional retail outlets. Moving beyond the flat, binary catchment counts utilized in the preliminary round, this phase implements non-linear distance-decay functions and competitor density matrix calculations to model true market potential.

---

## 💡 Core Architecture & Design Decisions

### 1. The Pivot to Continuous Distance-Decay Math
* **The Limitation of Flat Counts:** In preliminary models, counting POIs within a rigid circle (e.g., 500m) treated an anchor right outside a kade (20m away) identically to an anchor on the absolute perimeter (490m away). Real-world retail footfall does not drop off a cliff at an arbitrary boundary line; instead, its influence fades continuously as distance increases.
* **The Mathematical Solution:** We implemented a continuous **Exponential Distance-Decay Function**:
    
    $$\text{decay\_weight} = e^{-\left(\frac{\text{distance}}{\text{scale}}\right)}$$

    This approach treats distance as a continuous variable. A point of interest right outside the storefront yields a decay weight close to `1.0`. As the calculated Haversine distance increases, its mathematical weight smoothly drops toward `0.0`, dynamically matching true human transit patterns.

### 2. Strategic Feature Grouping & No Reduction
To optimize machine learning model performance, the 11 raw POI categories collected by our scraping layer are dynamically mapped into 4 cohesive, low-noise density vectors:
* `school_decay_score`: Isolates **schools** to capture concentrated student footfall cycles, utilizing a tight `scale_meters=150.0` to model immediate walkability boundaries.
* `transit_decay_score`: Groups **bus stops** and **railway stations** to track major commuter flow hubs (`scale_meters=200.0`).
* `commercial_decay_score`: Combines the economic traction of **supermarkets**, **markets**, **restaurants** (including cafes/fast food), and **banks/ATMs** into a unified local commercial hotspot metric (`scale_meters=300.0`).
* `overall_spatial_gravity_score`: Runs an all-inclusive mathematical sweep across every single available map anchor—including **hospitals/clinics**, **fuel stations**, **religious places**, and **tourism places**—to capture a location's absolute geographic pull vector (`scale_meters=250.0`).

*By grouping highly related features, we preserve 100% of the raw 22,870 scraped POI data points while drastically shrinking the feature space, protecting downstream algorithms from overfitting on sparse columns.*

### 3. Internal Competitor Catchment Density
An outlet's true capacity is highly dependent on whether it operates inside an isolated micro-market or a heavily saturated town center. The script runs a vectorized, internal **store-to-store spatial matrix comparison** across all 20,000 outlets. For each shop, `competitor_catchment_density` tracks exactly how many *other* competing outlets from the master dataset sit within an immediate 500m radius, giving the model clear context on local market crowding.

### 4. Dependency on Silver Coordinates
The feature builder runs directly against `data/silver/outlet_coordinates.csv`. This ensures that we calculate decay scores using coordinates that have already been vetted by our data forensics layer (where inverted latitude/longitude index errors are pre-resolved). 

---

## 🏃‍♂️ Operational Execution Guide

### Pipeline Prerequisites
Before calculating your decay features, ensure you have pulled Member 1's cleaned core datasets down to your local environment and executed the cleaning pipeline:
```bash
# 1. Pull the latest round 2 branch updates
git fetch origin
git checkout round2/data-competitor-density
git pull origin round2/data-competitor-density

# 2. Run the upstream cleaning pipeline to generate the Silver coordinates base
python -m src.data.silver_pipeline
```

---

## Running the Advanced Spatial Pipeline

Execute the continuous decay feature builder from the repository root directory using your terminal:

```bash
python -m src.features.build_spatial_decay
```

> **Note:** Ensure a synchronized duplicate copy of this script sits at `src/poi/build_spatial_decay.py` to maintain modular transparency for reviewers.

---

## Expected Pipeline Outputs

Upon successful compilation, the script will output a new optimized data file:

```
📁 data/silver/
└── 📄 outlet_spatial_decay_features.csv
```

This file contains exactly **20,000 rows** mapped to the following **6 production columns:**

| Column | Description |
|---|---|
| `Outlet_ID` | Unique outlet identifier |
| `school_decay_score` | Decay score relative to schools |
| `transit_decay_score` | Decay score relative to transit |
| `commercial_decay_score` | Decay score relative to commercial zones |
| `overall_spatial_gravity_score` | Composite spatial gravity score |
| `competitor_catchment_density` | Competitor density within catchment area |

---

## 🤝 Gold Layer Hand-off & Multi-Modal Feature Fusion

Following the background execution of the standalone vectorized script (`src/features/build_spatial_decay.py`), the downstream multi-modal relational integration is orchestrated interactively inside **`notebooks/02_gold_feature_fusion.ipynb`**. 

This stage bridges your advanced spatial features with internal operational streams to construct the finalized modeling asset.

### 1. Sequential Pipeline Ingestion & Relational Merging

The notebook systematically ingests the three core clean data structures from the Silver storage layer:
* `outlet_master.csv`: Primary structural matrix containing invariant store profiles.
* `transactions_history_final.csv`: Granular time-series transaction histories capturing historical sales averages.
* `outlet_spatial_decay_features.csv`: Your newly engineered advanced distance-decay and competitive density vectors.

To construct the unified table without altering the row footprint, the notebook compresses the millions of granular time-series transactions into individual, high-level outlet summaries (`lifetime_volume_liters`, `lifetime_revenue_lkr`, `avg_transaction_size_liters`, and `active_transaction_months`). It then executes a deterministic relational **Left-Join** using `Outlet_ID` as the primary joining index key. Newly onboarded outlets featuring no historical sales data are safely imputed with zero counts to protect dataset integrity.

### 2. Statistical Fault-Recovery Guardrail (Median Imputation)
During the core data cleaning pipeline, **40 unique outlets** were systematically quarantined due to unresolvable, corrupted raw coordinate strings[cite: 75]. To comply with strict evaluation guidelines requiring the absolute preservation of all 20,000 outlets[cite: 31], these locations were maintained inside the core master table. 

* **The Bottleneck:** Because these 40 outlets lack valid coordinates, they fail to map to OpenStreetMap point-of-interest tokens or nearby competing outlets, generating blank `NaN` cells across your fresh spatial columns. Passing these empty matrices into tree-based gradient boosting frameworks (e.g., XGBoost, LightGBM) will cause runtime compilation failures.
* **The Mitigation:** The notebook deploys a non-biasing, automated statistical global median imputation guardrail. It isolates the missing spatial cells and populates them with the true population median of the respective columns. This safely immunizes the data structure and prevents downstream model crashes without shifting feature variance or introducing synthetic data bias.

### 3. Production Unit Testing Matrix
Prior to promoting the dataset to the Gold repository for model training, the notebook runs four parameterized enterprise assertions to guarantee strict structural compliance with the competition's design layout[cite: 74]:

| Test Identifier | Validation Target | Success Metric | Failure Risk |
| :--- | :--- | :--- | :--- |
| **Unit Test 1** | Strict Population Footprint | Matrix length equals exactly `20000` | Dropped active outlet records [cite: 31] |
| **Unit Test 2** | Primary Key Completeness | `0` missing `Outlet_ID` records | Identifier fragmentation |
| **Unit Test 3** | Primary Key Uniqueness | `0` duplicate `Outlet_ID` rows | Relational index collisions |
| **Unit Test 4** | Global Matrix Completeness | `0` unhandled missing `NaN` cells | Downstream model training crashes |

---

## 🏃‍♂️ Notebook Execution Flow

To cleanly run and verify the final data fusion workspace, follow these steps inside your interactive development environment:

1.  Open your terminal and verify the background script successfully built the dependency asset:
    ```bash
    python -m src.features.build_spatial_decay
    ```
2.  Navigate to the `notebooks/` directory and open `02_gold_feature_fusion.ipynb`.
3.  Execute all cells sequentially from the top down (`Run All`).
4.  **Verify Final Output Promotion:** Ensure the final cell passes all four structural unit assertions, matches the expected footprint geometry (**20,000 rows × 40 columns**), and successfully writes the master modeling file to:
    ```text
    data/gold/master_feature_table.csv
    ```
