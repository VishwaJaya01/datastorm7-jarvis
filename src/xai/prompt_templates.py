"""Prompt templates for optional LLM-based outlet explanations.

This module only defines prompts. It does not call any API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


STRICT_FACTS_INSTRUCTION = (
    "Use only the provided facts. Do not invent numbers. Do not change predictions. "
    "Do not change budget allocation."
)

OUTLET_EXPLANATION_PROMPT = """You are explaining a DataStorm 7.0 outlet recommendation to a business user.

Rules:
- Use only the provided facts. Do not invent numbers. Do not change predictions. Do not change budget allocation.
- Keep the explanation concise and practical.
- Mention positive demand drivers, limiting factors, and why the trade spend recommendation is reasonable.
- If a fact is missing, say it is unavailable instead of guessing.

Provided facts:
{facts}
"""


def build_outlet_explanation_prompt(facts: Mapping[str, Any]) -> str:
    """Build a strict prompt from structured outlet facts."""

    fact_lines = [f"- {key}: {value}" for key, value in sorted(facts.items())]
    return OUTLET_EXPLANATION_PROMPT.format(facts="\n".join(fact_lines))
