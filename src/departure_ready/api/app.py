from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.concurrency import run_in_threadpool

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

ListQuery = Annotated[list[str] | None, Query()]


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Departure Ready MCP",
        version="0.1.0",
        summary="Official-source-first airport departure readiness HTTP API",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"ok": True, "service": "departure-ready-api", "env": settings.env}

    @app.get("/v1/coverage")
    async def get_coverage() -> dict[str, object]:
        return build_coverage_envelope().model_dump(mode="json")

    @app.get("/v1/guide")
    async def get_guide() -> dict[str, object]:
        return build_guide_envelope().model_dump(mode="json")

    @app.get("/v1/parking")
    async def get_parking(
        airport_code: str,
        terminal: str | None = None,
    ) -> dict[str, object]:
        envelope = await run_in_threadpool(
            build_parking_envelope,
            airport_code,
            terminal,
            settings=settings,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/flight-status")
    async def get_flight_status(
        airport_code: str,
        flight_no: str | None = None,
    ) -> dict[str, object]:
        envelope = await run_in_threadpool(
            build_flight_envelope,
            airport_code,
            flight_no,
            settings=settings,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/baggage-check")
    async def get_baggage_check(
        trip_type: str,
        item_query: str,
        liquid_ml: float | None = None,
        battery_wh: float | None = None,
    ) -> dict[str, object]:
        envelope = await run_in_threadpool(
            build_baggage_envelope,
            item_query,
            trip_type,
            liquid_ml=liquid_ml,
            battery_wh=battery_wh,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/customs-rules")
    async def get_customs_rules(
        item_query: str | None = None,
        purchase_value_usd: float | None = None,
        alcohol_liters: float | None = None,
        perfume_ml: float | None = None,
        cigarette_count: int | None = None,
    ) -> dict[str, object]:
        envelope = await run_in_threadpool(
            build_customs_envelope,
            item_query,
            purchase_value_usd,
            alcohol_liters,
            perfume_ml,
            cigarette_count,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/self-service-options")
    async def get_self_service_options(
        airport_code: str,
        airline: str | None = None,
    ) -> dict[str, object]:
        envelope = await run_in_threadpool(
            build_self_service_envelope,
            airport_code,
            airline,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/priority-lane-eligibility")
    async def get_priority_lane_eligibility(
        airport_code: str,
        user_profile: str | None = None,
        traveler_flags: ListQuery = None,
    ) -> dict[str, object]:
        flags = _collect_traveler_flags(user_profile, traveler_flags)
        envelope = await run_in_threadpool(
            build_priority_lane_envelope,
            airport_code,
            flags,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/facilities")
    async def get_facilities(
        airport_code: str,
        terminal: str | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> dict[str, object]:
        envelope = await build_facilities_envelope(
            settings,
            airport_code,
            terminal=terminal,
            category=category,
            query=query,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/shops")
    async def get_shops(
        airport_code: str,
        terminal: str | None = None,
        category: str | None = None,
        query: str | None = None,
    ) -> dict[str, object]:
        envelope = await build_shops_envelope(
            settings,
            airport_code,
            terminal=terminal,
            category=category,
            query=query,
        )
        return envelope.model_dump(mode="json")

    @app.get("/v1/readiness")
    async def get_readiness(
        airport_code: str,
        flight_no: str | None = None,
        going_by_car: bool = False,
        items: ListQuery = None,
        traveler_flags: ListQuery = None,
    ) -> dict[str, object]:
        envelope = await run_in_threadpool(
            build_readiness_envelope,
            airport_code,
            flight_no=flight_no,
            going_by_car=going_by_car,
            items=items,
            traveler_flags=traveler_flags,
            settings=settings,
        )
        return envelope.model_dump(mode="json")

    return app


def _collect_traveler_flags(
    user_profile: str | None,
    traveler_flags: list[str] | None,
) -> list[str]:
    flags = {flag.strip().lower() for flag in (traveler_flags or []) if flag.strip()}
    profile = (user_profile or "").lower()
    if "pregnant" in profile:
        flags.add("pregnant")
    if "infant" in profile or "baby" in profile:
        flags.add("infant")
    if "child" in profile:
        flags.add("child")
    if "disabled" in profile or "wheelchair" in profile:
        flags.add("disabled")
    if "mobility" in profile:
        flags.add("mobility_impaired")
    return sorted(flags)


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "departure_ready.api.app:create_app",
        factory=True,
        host=settings.http_host,
        port=settings.http_port,
        reload=False,
    )
