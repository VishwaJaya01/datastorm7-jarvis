# Features

Feature engineering code for building the Gold modeling dataset.

## Gold Master Feature Builder

`build_master_features.py` creates the reproducible Gold feature table used by the final modeling pipeline.

Run from the repository root:

```bash
python -m src.features.build_master_features
```

Inputs:

- `data/silver/outlet_master.csv`
- `data/silver/outlet_base_features.csv` if available
- `data/external/outlet_poi_features_v2.csv`

Output:

- `data/gold/master_features.csv`

The Gold table starts from all 20,000 rows in Silver `outlet_master.csv`, so every required outlet remains represented. POI v2 features only cover valid/corrected coordinate outlets, so outlets with missing or quarantined coordinates are retained as POI-blind rows, with POI counts/scores filled safely to `0` and `poi_available=False`.

The builder also adds explainable derived POI features such as log-transformed POI totals, percentile ranks, demand-score ranks, and `catchment_class`.
