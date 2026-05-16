# GenAI Usage Log

This file records how Team Jarvis used generative AI during the DataStorm 7.0 Storming Round.

## Log Format

| Time | Member | Tool | Purpose | Prompt Summary | Output Used? | Validation Done |
|---|---|---|---|---|---|---|
| Hour 2 | Judith | Gemini | Generate boilerplate Overpass API scraping script for POI extraction. | "Write a Python script to query Overpass API for schools, bus stops, and hospitals within 500m of a given lat/lon. Parse the JSON and return counts." | Yes (Refactored) | Added `time.sleep()` to prevent rate limiting, combined multiple API calls into a single union query for optimization, and implemented `.get()` for fault-tolerant JSON parsing to prevent pipeline crashes. |
| Hour 2 | Judith | Gemini | Debug Overpass API rejection (`406 Client Error`). | "The script returned a 406 Not Acceptable error for every coordinate. How do I fix the Overpass API request?" | Yes (Implemented) | Identified that the public API blocked the default Python `requests` signature. Implemented a custom HTTP `User-Agent` header (`DataStorm_TeamJarvis...`) to authenticate our pipeline and bypass the security block. |
| Hour 3 | Judith | Gemini | Debug API URL encoding failure (`406 Not Acceptable`). | "The API is still returning 406 even with the User-Agent header. The URL looks extremely long with URL-encoded characters." | Yes (Refactored) | Identified that passing the large Overpass QL query via a `GET` request caused URL encoding corruption/length rejection by the server. Refactored the Python pipeline to utilize `requests.post()`, sending the query safely in the request body. |
| Hour 6 | Judith | Gemini | Implement Adaptive Backoff & Retry Logic for API stability. | "The script is hitting too many 429 and 504 errors. How do I make it smarter so I don't get zeros for half the outlets?" | Yes | Refactored the scraper to identify 429 errors and trigger a 30-second "cool-down" period before retrying. Added a 5-second pause for 504 Gateway Timeouts. This ensures higher data density for the modeling phase, rather than allowing the pipeline to proceed with missing values. |
| Hour 14 | Judith | Gemini | Strategies for managing persistent API rate limits and local session disconnects. | "The script is hitting continuous 429/504 errors and disconnecting at row 12,500. Gemini suggested implementing an inline retry loop and restarting the scrape from index 0 in Colab." | Yes (Overrode AI advice for infrastructure execution) | **Human-in-the-Loop Override:** Critically evaluated the AI's suggestion to rerun inside the same interactive Colab notebook. Determined that local session vulnerabilities and network overhead would still create a deployment bottleneck. Overrode the AI's local rerun approach; instead, packaged the AI-optimized code into a headless execution script and deployed it on an isolated machine with stable, dedicated bandwidth. This structural pivot successfully bypassed browser session timeouts, delivering the complete `outlet_poi_features_FINAL.csv` without further data loss. |

## Notes

- AI-generated code must be reviewed before use.
- AI-generated assumptions must be validated against the data.
- Do not blindly trust AI output.
