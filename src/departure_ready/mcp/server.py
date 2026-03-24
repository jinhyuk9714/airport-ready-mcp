from __future__ import annotations

import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from departure_ready.services.baggage import build_baggage_envelope
from departure_ready.services.customs import build_customs_envelope
from departure_ready.services.facilities import (
    build_facilities_envelope,
    build_shops_envelope,
)
from departure_ready.services.flight import build_flight_envelope
from departure_ready.services.guide import build_coverage_envelope, build_guide_envelope
from departure_ready.services.parking import build_parking_envelope
from departure_ready.services.readiness import build_readiness_envelope
from departure_ready.services.self_service import (
    build_priority_lane_envelope,
    build_self_service_envelope,
)
from departure_ready.settings import get_settings

logger = logging.getLogger(__name__)
mcp = FastMCP("departure-ready")


@mcp.tool()
def tool_get_coverage() -> dict:
    """Return the current support matrix and trust contract."""
    return build_coverage_envelope().model_dump(mode="json")


@mcp.tool()
def tool_get_guide() -> dict:
    """Return the product guide and out-of-scope list."""
    return build_guide_envelope().model_dump(mode="json")


@mcp.tool()
def tool_get_departure_readiness(
    airport_code: str,
    flight_no: str | None = None,
    going_by_car: bool = False,
    items: list[str] | None = None,
    traveler_flags: list[str] | None = None,
) -> dict:
    envelope = build_readiness_envelope(
        airport_code,
        flight_no=flight_no,
        going_by_car=going_by_car,
        items=items,
        traveler_flags=traveler_flags,
        settings=get_settings(),
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_get_parking_status(airport_code: str, terminal: str | None = None) -> dict:
    envelope = build_parking_envelope(
        airport_code,
        terminal,
        settings=get_settings(),
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_get_flight_status(airport_code: str, flight_no: str | None = None) -> dict:
    envelope = build_flight_envelope(
        airport_code,
        flight_no,
        settings=get_settings(),
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_check_baggage_rules(
    item_query: str,
    trip_type: str,
    liquid_ml: float | None = None,
    battery_wh: float | None = None,
) -> dict:
    envelope = build_baggage_envelope(
        item_query,
        trip_type,
        liquid_ml=liquid_ml,
        battery_wh=battery_wh,
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_get_customs_rules(
    item_query: str | None = None,
    purchase_value_usd: float | None = None,
    alcohol_liters: float | None = None,
    perfume_ml: float | None = None,
    cigarette_count: int | None = None,
) -> dict:
    envelope = build_customs_envelope(
        item_query,
        purchase_value_usd,
        alcohol_liters,
        perfume_ml,
        cigarette_count,
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_get_self_service_options(airport_code: str, airline: str | None = None) -> dict:
    envelope = build_self_service_envelope(airport_code, airline)
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_get_priority_lane_eligibility(
    airport_code: str,
    traveler_flags: list[str] | None = None,
) -> dict:
    envelope = build_priority_lane_envelope(
        airport_code,
        traveler_flags=traveler_flags,
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_find_facilities(
    airport_code: str,
    terminal: str | None = None,
    category: str | None = None,
    query: str | None = None,
) -> dict:
    envelope = asyncio.run(
        build_facilities_envelope(
            get_settings(),
            airport_code,
            terminal=terminal,
            category=category,
            query=query,
        )
    )
    return envelope.model_dump(mode="json")


@mcp.tool()
def tool_find_shops(
    airport_code: str,
    terminal: str | None = None,
    category: str | None = None,
    query: str | None = None,
) -> dict:
    envelope = asyncio.run(
        build_shops_envelope(
            get_settings(),
            airport_code,
            terminal=terminal,
            category=category,
            query=query,
        )
    )
    return envelope.model_dump(mode="json")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run(transport="stdio")
