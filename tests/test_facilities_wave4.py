from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from departure_ready.api.app import create_app
from departure_ready.catalog import is_domain_supported
from departure_ready.connectors.base import ConnectorUnavailableError
from departure_ready.contracts import (
    Envelope,
    Freshness,
    ResponseMeta,
    SourceKind,
    SourceRef,
)
from departure_ready.domain.models import FacilityMatch, FacilityPayload
from departure_ready.mcp.server import tool_find_facilities
from departure_ready.services.facilities import build_facilities_envelope
from departure_ready.settings import Settings


def _facility_match(
    airport_code: str,
    name: str,
    *,
    category: str,
    terminal: str | None = None,
) -> FacilityMatch:
    return FacilityMatch(
        airport_code=airport_code,
        terminal=terminal,
        name=name,
        category=category,
        location_text="게이트 인근",
        freshness=Freshness.STATIC,
        updated_at=datetime(2026, 3, 24, 16, 0, tzinfo=UTC),
        source=[
            SourceRef(
                name=(
                    "kac_accessibility_file"
                    if category == "accessibility"
                    else "kac_facility_file"
                ),
                kind=SourceKind.OFFICIAL_API,
                url="https://example.invalid/kac",
            )
        ],
        coverage_note=f"{airport_code} facility lookup",
    )


@dataclass
class _FakeKacFacilityConnector:
    matches: list[FacilityMatch]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str | None, str | None]] = []

    async def find_facilities(
        self,
        airport_code: str,
        *,
        query: str | None = None,
        category: str | None = None,
    ) -> list[FacilityMatch]:
        self.calls.append((airport_code, query, category))
        return self.matches


def test_support_matrix_adds_facilities_for_selected_kac_airports():
    assert is_domain_supported("PUS", "facilities") is True
    assert is_domain_supported("CJJ", "facilities") is True
    assert is_domain_supported("TAE", "facilities") is True


def test_kac_facilities_return_bounded_static_results(monkeypatch):
    connector = _FakeKacFacilityConnector(
        matches=[_facility_match("PUS", "휠체어 리프트", category="accessibility")],
    )

    monkeypatch.setattr(
        "departure_ready.services.facilities.KacFacilityConnector",
        lambda *args, **kwargs: connector,
        raising=False,
    )

    envelope = build_facilities_envelope(
        Settings(env="test"),
        "PUS",
        category="wheelchair",
    )

    if hasattr(envelope, "__await__"):
        import asyncio

        envelope = asyncio.run(envelope)

    assert envelope.ok is True
    assert connector.calls == [("PUS", None, "wheelchair")]
    assert envelope.meta.freshness == Freshness.STATIC
    assert envelope.data.matches[0].category == "accessibility"


def test_kac_facilities_outage_is_bounded_not_unsupported(monkeypatch):
    class _FailingKacFacilityConnector:
        async def find_facilities(self, airport_code: str, *, query=None, category=None):
            raise ConnectorUnavailableError("kac_facility_file unavailable")

    monkeypatch.setattr(
        "departure_ready.services.facilities.KacFacilityConnector",
        lambda *args, **kwargs: _FailingKacFacilityConnector(),
        raising=False,
    )

    envelope = build_facilities_envelope(Settings(env="test"), "CJJ")

    if hasattr(envelope, "__await__"):
        import asyncio

        envelope = asyncio.run(envelope)

    assert envelope.ok is True
    assert envelope.data.airport_code == "CJJ"
    assert envelope.data.matches == []
    assert "unavailable" in envelope.meta.coverage_note.lower()


def test_http_and_mcp_facility_surfaces_keep_parity(monkeypatch):
    async def fake_build_facilities_envelope(settings, airport_code: str, **kwargs):
        return Envelope(
            meta=ResponseMeta(
                source=[
                    SourceRef(
                        name="kac_accessibility_file",
                        kind=SourceKind.OFFICIAL_API,
                        url="https://example.invalid/kac",
                    )
                ],
                freshness=Freshness.STATIC,
                updated_at=datetime(2026, 3, 24, 16, 5, tzinfo=UTC),
                coverage_note=f"{airport_code} facility lookup",
            ),
            data=FacilityPayload(
                airport_code=airport_code,
                terminal=kwargs.get("terminal"),
                matches=[_facility_match(airport_code, "유아휴게실", category="family")],
            ),
        )

    monkeypatch.setattr(
        "departure_ready.api.app.build_facilities_envelope",
        fake_build_facilities_envelope,
    )
    monkeypatch.setattr(
        "departure_ready.mcp.server.build_facilities_envelope",
        fake_build_facilities_envelope,
    )

    client = TestClient(create_app())
    http_payload = client.get(
        "/v1/facilities",
        params={"airport_code": "GMP", "category": "baby"},
    ).json()
    mcp_payload = tool_find_facilities("GMP", category="baby")

    assert http_payload["ok"] is True
    assert mcp_payload["ok"] is True
    assert http_payload["data"]["airport_code"] == mcp_payload["data"]["airport_code"] == "GMP"
    assert http_payload["data"]["matches"][0]["name"] == mcp_payload["data"]["matches"][0]["name"]
