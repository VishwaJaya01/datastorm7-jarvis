# Decision Log

This file records important technical and methodology decisions made during the competition.

| Time | Decision | Reason | Owner | Impact |
|---|---|---|---|---|
| 2026-05-16 | Added Silver handoff files for monthly outlet volume, clean outlet locations, and outlet base features. | Members 2 and 3 need stable POI/modeling inputs without rerunning ad hoc aggregations. | Member 1 | Unblocks POI joins and modeling feature work from reproducible Silver outputs. |
| 2026-05-16 | Added soft modeling flags instead of hard-filtering risky outlets. | Missing months, low activity, sudden drops, spikes, variability, and coordinate quality are useful model signals but should not remove required outlets. | Member 1 | Preserves full outlet coverage while giving Member 3 explicit DQ/activity controls. |
| 2026-05-16 | Added report-ready rejection, warning, and correction summary CSVs. | Final reporting needs compact audit tables by dataset, reason, warning, and correction type. | Member 1 | Reduces manual report prep and keeps EDA numbers tied to pipeline output. |
| 2026-05-16 | Added `.gitattributes` to normalize project text files to LF. | Avoid CRLF/LF diff noise across operating systems and generated reports. | Member 1 | Cleaner handoff diffs and reproducible text outputs. |
