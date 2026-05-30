# XAI

Round 2 XAI modules will explain model predictions and budget allocation recommendations for the Outlet Intelligence Web App.

Planned explanation modes:

- Deterministic fallback explanation using structured feature facts.
- Optional hosted LLM/API explanation when an API key is configured.

The app must run even without an API key. LLM-generated explanations must only explain provided structured facts and must not invent numbers, change predictions, or change budget allocations.
