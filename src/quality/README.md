# Quality

Data quality checks, anomaly detection rules, and validation reports for competition datasets.

Reusable checks live in `checks.py` and return standard `CheckResult` objects.
Each check can be applied consistently across datasets and converted into the
standard rejected-record shape with:

- `source_file`
- `check_name`
- `failure_reason`
- `rejected_at`
