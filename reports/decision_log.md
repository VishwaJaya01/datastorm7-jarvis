# Decision Log
This file records important technical and methodology decisions made during the competition.

| Time | Decision | Reason | Owner | Impact |
|---|---|---|---|---|
| Hour 4 | Targeted `school`, `bus_stop`, and `hospital` tags (500m radius) via Overpass API. | Beverage demand is driven by transient/impulse traffic. Schools (afternoon peak), transit (commuters), and hospitals (24/7 baseline) act as high-probability anchors. Excluded broad tags (residential) to prevent feature dilution. | Judith (Geospatial Lead) | Establishes the core geospatial features for the Gold layer and sets the foundational logic for the uncapped potential model. |
