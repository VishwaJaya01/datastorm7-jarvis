# Data

Utilities for loading raw inputs, creating Bronze and Silver datasets, and tracking rejected records.

Run the Member 1 pipeline from the repository root:

```bash
python3 -m src.data.silver_pipeline
```

The pipeline copies raw CSVs into `data/bronze/`, writes cleaned Silver CSVs into
`data/silver/`, and writes rejected-record audit files into `data/rejected/`.
