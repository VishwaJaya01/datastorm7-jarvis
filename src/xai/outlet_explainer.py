"""Deterministic outlet explanations for Round 2.

The fallback explainer uses only structured facts passed into the function. It
does not call any API and does not invent missing values.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def explain_outlet(row: Mapping[str, Any]) -> str:
    """Return a concise business explanation for one outlet."""

    facts = dict(row)
    outlet_id = clean_value(facts.get("Outlet_ID"), default="this outlet")
    lines = [f"Outlet {outlet_id} was evaluated using the available prediction, history, spatial, and allocation facts."]

    potential = get_number(facts, "Maximum_Monthly_Liters")
    if potential is not None:
        lines.append(f"Predicted monthly potential is {potential:,.2f} liters.")

    allocation = get_number(facts, "Trade_Spend_Allocation_LKR")
    if allocation is not None:
        if allocation > 0:
            lines.append(f"Recommended trade spend allocation is LKR {allocation:,.2f}.")
        else:
            lines.append("No positive trade spend allocation is recommended for this outlet in the current output.")

    drivers = positive_drivers(facts)
    if drivers:
        lines.append("Positive drivers: " + "; ".join(drivers) + ".")

    limits = limiting_factors(facts)
    if limits:
        lines.append("Limiting factors: " + "; ".join(limits) + ".")

    if len(lines) == 1:
        lines.append("Only limited facts were provided, so the explanation is intentionally conservative.")

    return " ".join(lines)


def positive_drivers(facts: Mapping[str, Any]) -> list[str]:
    """Describe available positive signals without inventing values."""

    drivers: list[str] = []
    add_positive_metric(drivers, facts, "demand_driver_score_1000m", "strong 1000m demand-driver POI score")
    add_positive_metric(drivers, facts, "overall_spatial_gravity_score", "strong spatial gravity score")
    add_positive_metric(drivers, facts, "commercial_decay_score", "nearby commercial activity")
    add_positive_metric(drivers, facts, "Cooler_Count", "cooler capacity")
    add_positive_metric(drivers, facts, "active_month_count", "historical activity coverage")

    poi_available = get_bool(facts, "poi_available")
    if poi_available is True:
        drivers.append("POI/catchment features are available")
    return drivers


def limiting_factors(facts: Mapping[str, Any]) -> list[str]:
    """Describe available caution signals without inventing values."""

    limits: list[str] = []
    poi_available = get_bool(facts, "poi_available")
    if poi_available is False:
        limits.append("POI features are unavailable or the outlet is POI-blind")

    coord_status = clean_value(facts.get("coord_status"))
    if coord_status and coord_status.lower() in {"quarantined", "missing", "invalid"}:
        limits.append(f"coordinate status is {coord_status}")

    add_high_metric(limits, facts, "market_saturation_index", "market saturation is high")
    add_high_metric(limits, facts, "competitor_density_score", "competitor density is high")

    low_activity = get_bool(facts, "low_activity_outlet_flag")
    if low_activity is True:
        limits.append("historical activity is low")
    return limits


def add_positive_metric(drivers: list[str], facts: Mapping[str, Any], column: str, label: str) -> None:
    """Append a positive metric only when a positive value exists."""

    value = get_number(facts, column)
    if value is not None and value > 0:
        drivers.append(f"{label} ({column}={value:,.2f})")


def add_high_metric(limits: list[str], facts: Mapping[str, Any], column: str, label: str) -> None:
    """Append a high-risk metric only when a positive value exists."""

    value = get_number(facts, column)
    if value is not None and value > 0:
        limits.append(f"{label} ({column}={value:,.2f})")


def get_number(facts: Mapping[str, Any], key: str) -> float | None:
    """Safely parse a numeric fact."""

    value = facts.get(key)
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def get_bool(facts: Mapping[str, Any], key: str) -> bool | None:
    """Safely parse a boolean fact."""

    value = facts.get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f"}:
        return False
    return None


def clean_value(value: Any, default: str = "") -> str:
    """Return a readable string for display."""

    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text
