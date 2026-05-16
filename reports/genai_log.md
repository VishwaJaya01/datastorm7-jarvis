# GenAI Usage Log

This file records how Team Jarvis used generative AI during the DataStorm 7.0 Storming Round.

## Log Format

| Time | Member | Tool | Purpose | Prompt Summary | Output Used? | Validation Done |
|---|---|---|---|---|---|---|
| 2026-05-16 | Member 1 | Codex | Silver pipeline handoff readiness | Continue Silver pipeline by fixing line-ending noise, creating POI/modeling handoff files, adding report summaries and soft modeling flags, and updating logs/docs. | Yes | Ran `python3 -m src.data.silver_pipeline`; pipeline assertions validate Silver and handoff contracts; checked generated summary/output files. |
| Hour 2 | Member 2 | Gemini | Generate boilerplate Overpass API scraping script for POI extraction. | "Write a Python script to query Overpass API for schools, bus stops, and hospitals within 500m of a given lat/lon. Parse the JSON and return counts." | Yes (Refactored) | Added `time.sleep()` to prevent rate limiting, combined multiple API calls into a single union query for optimization, and implemented `.get()` for fault-tolerant JSON parsing to prevent pipeline crashes. |
| Hour 2 | Member 2  | Gemini | Debug Overpass API rejection (`406 Client Error`). | "The script returned a 406 Not Acceptable error for every coordinate. How do I fix the Overpass API request?" | Yes (Implemented) | Identified that the public API blocked the default Python `requests` signature. Implemented a custom HTTP `User-Agent` header (`DataStorm_TeamJarvis...`) to authenticate our pipeline and bypass the security block. |
| Hour 3 | Member 2  | Gemini | Debug API URL encoding failure (`406 Not Acceptable`). | "The API is still returning 406 even with the User-Agent header. The URL looks extremely long with URL-encoded characters." | Yes (Refactored) | Identified that passing the large Overpass QL query via a `GET` request caused URL encoding corruption/length rejection by the server. Refactored the Python pipeline to utilize `requests.post()`, sending the query safely in the request body. |
| Hour 15 | Member 2  | Gemini | Refactoring interactive notebooks into automated production pipelines with custom feature engineering. | "I have the scraping code and the feature engineering code in my notebook. Should I create two different .py files?" | Yes (Overrode local execution advice) | **Architectural Strategy & Code Promotion:** Critically evaluated the AI's suggestion to keep rerunning code blocks within an interactive notebook. Determined that local network vulnerabilities and browser timeouts create a engineering bottleneck. Overrode the local execution path; instead, packaged the optimized Overpass API scraper into a standalone, tile-based execution runner (`src/features/scrape_poi_features.py`) and orchestrated its deployment on a stable, external host. Successfully recovered and unzipped the 20,000-row geospatial payload (`outlet_poi_features_FINAL.csv`), imported it back into the interactive notebook, and engineered advanced multi-modal demand indices to deliver a clean, model-ready Gold dataset. |


## Notes

- AI-generated code must be reviewed before use.
- AI-generated assumptions must be validated against the data.
- Do not blindly trust AI output.
