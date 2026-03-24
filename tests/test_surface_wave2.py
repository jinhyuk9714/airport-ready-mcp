from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from departure_ready.contracts import (
    Envelope,
    Freshness,
    ResponseMeta,
    SourceKind,
    SourceRef,
)
from departure_ready.domain.models import FacilityPayload, ParkingLotSnapshot, ShopMatch
from departure_ready.mcp.server import mcp, tool_find_shops
from departure_ready.services.parking import build_parking_envelope


@dataclass
class _FakeIiacParkingConnector:
    lots: list[ParkingLotSnapshot]
    fee_rules: list[str]

    def __post_init__(self) -> None:
        self.status_calls: int = 0
        self.fee_calls: int = 0

    async def get_parking_status(self) -> list[ParkingLotSnapshot]:
        self.status_calls += 1
        return self.lots

    async def get_fee_rules(self) -> list[str]:
        self.fee_calls += 1
        return self.fee_rules


@dataclass
class _FakeKacParkingConnector:
    lots: list[ParkingLotSnapshot]

    def __post_init__(self) -> None:
        self.status_calls: list[str] = []

    async def get_parking_status(self, airport_code: str | None = None) -> list[ParkingLotSnapshot]:
        self.status_calls.append(airport_code or "GMP")
        return self.lots


def _parking_lot(
    airport_code: str,
    lot_name: str,
    *,
    terminal: str | None = None,
    available_spaces: int | None = None,
) -> ParkingLotSnapshot:
    return ParkingLotSnapshot(
        airport_code=airport_code,
        lot_name=lot_name,
        terminal=terminal,
        available_spaces=available_spaces,
        freshness=Freshness.LIVE,
        updated_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} lot",
    )


def test_icn_parking_fee_notes_are_enriched_without_estimate():
    connector = _FakeIiacParkingConnector(
        lots=[_parking_lot("ICN", "T1 short-term", terminal="T1", available_spaces=12)],
        fee_rules=["T1 short-term uses a flat weekday fee", "Weekend fee applies after 30 minutes"],
    )

    envelope = build_parking_envelope("ICN", iiac_connector=connector)

    assert envelope.ok is True
    assert connector.status_calls == 1
    assert connector.fee_calls == 1
    lot = envelope.data.lots[0]
    assert lot.estimated_fee_krw is None
    assert lot.fee_note is not None
    assert "parking fee" in lot.fee_note.lower()
    assert "weekday" in lot.fee_note.lower()


def test_kac_parking_keeps_existing_semantics_without_fee_note():
    connector = _FakeKacParkingConnector(
        lots=[_parking_lot("GMP", "Domestic", available_spaces=9)],
    )

    envelope = build_parking_envelope("GMP", kac_connector=connector)

    assert envelope.ok is True
    assert connector.status_calls == ["GMP"]
    lot = envelope.data.lots[0]
    assert lot.estimated_fee_krw is None
    assert lot.fee_note is None


def test_mcp_registers_and_forwards_shops_tool(monkeypatch):
    tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert "tool_find_shops" in tool_names

    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_build_shops_envelope(settings, airport_code: str, **kwargs):
        calls.append((airport_code, kwargs))
        payload = FacilityPayload(
            airport_code=airport_code,
            terminal=kwargs.get("terminal"),
            matches=[
                ShopMatch(
                    airport_code=airport_code,
                    terminal=kwargs.get("terminal"),
                    name="약국",
                    brand="약국",
                    category="shop",
                    location_text="T1",
                    freshness=Freshness.DAILY,
                    updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
                    source=[
                        SourceRef(
                            name="fake_shop",
                            kind=SourceKind.INTERNAL,
                            url="https://example.invalid",
                        )
                    ],
                    coverage_note="ICN shop lookup",
                )
            ],
        )
        return Envelope(
            meta=ResponseMeta(
                source=[
                    SourceRef(
                        name="fake_shop",
                        kind=SourceKind.INTERNAL,
                        url="https://example.invalid",
                    )
                ],
                freshness=Freshness.DAILY,
                updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
                coverage_note="ICN shop lookup",
            ),
            data=payload,
        )

    monkeypatch.setattr(
        "departure_ready.mcp.server.build_shops_envelope",
        fake_build_shops_envelope,
    )

    payload = tool_find_shops("ICN", query="약국")

    assert calls == [("ICN", {"terminal": None, "category": None, "query": "약국"})]
    assert payload["ok"] is True
    assert payload["data"]["airport_code"] == "ICN"
    assert payload["data"]["matches"][0]["name"] == "약국"


def test_mcp_shops_tool_reports_unsupported_airport():
    payload = tool_find_shops("XYZ")

    assert payload["ok"] is False
    assert payload["data"]["code"] == "unsupported_coverage"
    assert "shops" in payload["meta"]["coverage_note"]
