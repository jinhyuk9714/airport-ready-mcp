from __future__ import annotations

import asyncio
import json
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from departure_ready.api.app import create_app
from departure_ready.contracts import Envelope, Freshness, ResponseMeta, SourceKind, SourceRef
from departure_ready.domain.models import (
    AirportSupport,
    CoveragePayload,
    FacilityMatch,
    FacilityPayload,
    FlightSnapshot,
    ReadinessCard,
)
from departure_ready.settings import get_settings

ORIGINAL_ASYNCIO_RUN = asyncio.run


@asynccontextmanager
async def _remote_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEPARTURE_READY_ENV", "test")
    monkeypatch.setenv("DEPARTURE_READY_PUBLIC_HTTP_URL", "http://testserver")
    monkeypatch.delenv("DEPARTURE_READY_PUBLIC_MCP_URL", raising=False)
    get_settings.cache_clear()

    app = create_app()
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                async with streamable_http_client(
                    "http://testserver/mcp/",
                    http_client=client,
                ) as (read_stream, write_stream, _get_session_id):
                    session = ClientSession(read_stream, write_stream)
                    async with session:
                        await session.initialize()
                        yield session, app
    finally:
        get_settings.cache_clear()


def _tool_payload(result) -> dict[str, object]:
    assert not result.isError
    assert result.content, "expected tool result content"
    return json.loads(result.content[0].text)


def _fake_coverage_envelope() -> Envelope[CoveragePayload]:
    airports = [
        AirportSupport(
            airport_code="ICN",
            name_ko="인천국제공항",
            coverage="strong",
            domains=["flight_status", "parking", "facilities"],
        )
    ]
    payload = CoveragePayload(
        airports=airports,
        contract_summary=["official source first"],
    )
    meta = ResponseMeta(
        source=[
            SourceRef(
                name="repo_catalog",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid/departure-ready/repo_catalog",
            )
        ],
        freshness=Freshness.STATIC,
        updated_at=datetime(2026, 3, 24, 10, 4, tzinfo=UTC),
        coverage_note="Repository support matrix and trust contract.",
    )
    return Envelope(meta=meta, data=payload)


def _run_coroutine_in_thread(coro):
    result: dict[str, object] = {}
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            result["value"] = ORIGINAL_ASYNCIO_RUN(coro)
        except BaseException as exc:  # pragma: no cover - surfaced to caller
            errors.append(exc)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    if errors:
        raise errors[0]
    return result["value"]


def _fake_readiness_envelope(*args, **kwargs) -> Envelope[ReadinessCard]:
    airport_code = args[0]
    flight = FlightSnapshot(
        airport_code=airport_code,
        flight_no="KE123",
        airline="Korean Air",
        terminal="T1",
        gate="12",
        checkin_counter="A1",
        scheduled_at=datetime(2026, 3, 24, 11, 0, tzinfo=UTC),
        changed_at=datetime(2026, 3, 24, 11, 30, tzinfo=UTC),
        status_label="ON TIME",
        signal_kind="live",
        freshness=Freshness.LIVE,
        updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake_readiness_flight",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid/readiness",
            )
        ],
        coverage_note=f"{airport_code} flight",
    )
    facility = FacilityMatch(
        airport_code=airport_code,
        terminal="T1",
        name="Barrier-free elevator",
        category="accessibility",
        location_text="Gate 12",
        freshness=Freshness.STATIC,
        updated_at=datetime(2026, 3, 24, 10, 6, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake_readiness_facility",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid/readiness",
            )
        ],
        coverage_note=f"{airport_code} facility",
    )
    card = ReadinessCard(
        airport_code=airport_code,
        summary=f"{airport_code} readiness summary",
        operational_signal="live",
        operational_signals=[],
        next_actions=["Review flight status before leaving."],
        flight=flight,
        parking=None,
        baggage_warnings=[],
        service_eligibility=[],
        facility_hints=[facility],
        source=[
            SourceRef(
                name="fake_readiness",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid/readiness",
            )
        ],
        freshness=Freshness.LIVE,
        updated_at=datetime(2026, 3, 24, 10, 7, tzinfo=UTC),
        coverage_note=f"{airport_code} readiness",
    )
    meta = ResponseMeta(
        source=card.source,
        freshness=card.freshness,
        updated_at=card.updated_at,
        coverage_note=card.coverage_note,
    )
    return Envelope(meta=meta, data=card)


async def _fake_facilities_envelope(*args, **kwargs) -> Envelope[FacilityPayload]:
    airport_code = args[1]
    category = kwargs.get("category")
    match = FacilityMatch(
        airport_code=airport_code,
        terminal=None,
        name="Family lounge",
        category=category or "family",
        location_text="1F",
        freshness=Freshness.STATIC,
        updated_at=datetime(2026, 3, 24, 10, 8, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake_facilities",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid/facilities",
            )
        ],
        coverage_note=f"{airport_code} facility lookup",
    )
    payload = FacilityPayload(
        airport_code=airport_code,
        terminal=kwargs.get("terminal"),
        matches=[match],
    )
    meta = ResponseMeta(
        source=match.source,
        freshness=Freshness.STATIC,
        updated_at=match.updated_at,
        coverage_note=match.coverage_note,
    )
    return Envelope(meta=meta, data=payload)


@pytest.mark.asyncio
async def test_remote_mcp_lists_tools_and_matches_coverage_contract(monkeypatch):
    monkeypatch.setattr(
        "departure_ready.api.app.build_coverage_envelope",
        _fake_coverage_envelope,
    )
    monkeypatch.setattr(
        "departure_ready.mcp.server.build_coverage_envelope",
        _fake_coverage_envelope,
    )

    async with _remote_session(monkeypatch) as (session, app):
        tool_names = {tool.name for tool in (await session.list_tools()).tools}
        remote = _tool_payload(await session.call_tool("tool_get_coverage", {}))

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            http = (await client.get("/v1/coverage")).json()

    assert "tool_get_coverage" in tool_names
    assert "tool_get_departure_readiness" in tool_names
    assert "tool_find_facilities" in tool_names
    assert remote["ok"] is True
    assert remote["meta"] == http["meta"]
    assert remote["data"]["airports"] == http["data"]["airports"]


@pytest.mark.asyncio
async def test_remote_mcp_readiness_matches_http_contract(monkeypatch):
    monkeypatch.setattr(
        "departure_ready.api.app.build_readiness_envelope",
        _fake_readiness_envelope,
    )
    monkeypatch.setattr(
        "departure_ready.mcp.server.build_readiness_envelope",
        _fake_readiness_envelope,
    )

    async with _remote_session(monkeypatch) as (session, app):
        remote = _tool_payload(
            await session.call_tool(
                "tool_get_departure_readiness",
                {
                    "airport_code": "GMP",
                    "going_by_car": True,
                    "traveler_flags": ["wheelchair"],
                },
            )
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            http = (
                await client.get(
                    "/v1/readiness",
                    params={
                        "airport_code": "GMP",
                        "going_by_car": True,
                        "traveler_flags": ["wheelchair"],
                    },
                )
            ).json()

    assert remote["ok"] is True
    assert remote["meta"] == http["meta"]
    assert remote["data"]["airport_code"] == http["data"]["airport_code"] == "GMP"
    assert remote["data"]["summary"] == http["data"]["summary"]
    assert remote["data"]["operational_signal"] == http["data"]["operational_signal"]
    assert remote["data"]["facility_hints"] == http["data"]["facility_hints"]
    assert remote["data"]["next_actions"] == http["data"]["next_actions"]


@pytest.mark.asyncio
async def test_remote_mcp_facilities_matches_http_contract(monkeypatch):
    monkeypatch.setattr(
        "departure_ready.api.app.build_facilities_envelope",
        _fake_facilities_envelope,
    )
    monkeypatch.setattr(
        "departure_ready.mcp.server.build_facilities_envelope",
        _fake_facilities_envelope,
    )
    monkeypatch.setattr(
        "departure_ready.mcp.server.asyncio.run",
        _run_coroutine_in_thread,
    )

    async with _remote_session(monkeypatch) as (session, app):
        remote = _tool_payload(
            await session.call_tool(
                "tool_find_facilities",
                {
                    "airport_code": "GMP",
                    "category": "baby",
                },
            )
        )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            http = (
                await client.get(
                    "/v1/facilities",
                    params={"airport_code": "GMP", "category": "baby"},
                )
            ).json()

    assert remote["ok"] is True
    assert remote["meta"] == http["meta"]
    assert remote["data"]["airport_code"] == http["data"]["airport_code"] == "GMP"
    assert remote["data"]["matches"] == http["data"]["matches"]
    assert remote["data"]["matches"][0]["name"] == "Family lounge"
