from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette

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
def tool_get_flight_status(
    airport_code: str,
    flight_no: str | None = None,
    travel_date: str | None = None,
) -> dict:
    envelope = build_flight_envelope(
        airport_code,
        flight_no,
        travel_date=travel_date,
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


def create_streamable_http_app(settings=None) -> Starlette:
    runtime_settings = settings or get_settings()
    mcp.settings.streamable_http_path = "/"
    mcp.settings.transport_security = mcp.settings.transport_security.model_copy(
        update={
            "allowed_hosts": _build_allowed_hosts(runtime_settings),
            "allowed_origins": _build_allowed_origins(runtime_settings),
        }
    )
    mcp._session_manager = None
    return mcp.streamable_http_app()


def _build_allowed_hosts(settings) -> list[str]:
    hosts = list(mcp.settings.transport_security.allowed_hosts)
    for value in (settings.resolved_public_http_url, settings.resolved_public_mcp_url):
        hosts.extend(_host_candidates(value))
    return _dedupe(hosts)


def _build_allowed_origins(settings) -> list[str]:
    origins = list(mcp.settings.transport_security.allowed_origins)
    for value in (settings.resolved_public_http_url, settings.resolved_public_mcp_url):
        origins.extend(_origin_candidates(value))
    return _dedupe(origins)


def _host_candidates(url: str | None) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url)
    if not parsed.hostname:
        return []
    candidates = [parsed.hostname]
    if parsed.port is not None:
        candidates.append(f"{parsed.hostname}:{parsed.port}")
    else:
        candidates.append(f"{parsed.hostname}:*")
    return candidates


def _origin_candidates(url: str | None) -> list[str]:
    if not url:
        return []
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return []
    if parsed.port is not None:
        return [f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"]
    return [f"{parsed.scheme}://{parsed.hostname}"]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
