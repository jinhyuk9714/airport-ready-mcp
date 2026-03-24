from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.iiac_parking import (
    IIAC_SLOT_API_URL,
    IIAC_SLOT_DOC_URL,
    IIAC_SLOT_SOURCE_NAME,
    IiacParkingConnector,
)
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import ParkingLotSnapshot
from departure_ready.services.parking import build_parking_envelope


def _parking_lot(
    airport_code: str,
    lot_name: str,
    *,
    terminal: str | None = None,
    available_spaces: int | None = None,
    status: str = "unknown",
    freshness: Freshness = Freshness.LIVE,
) -> ParkingLotSnapshot:
    return ParkingLotSnapshot(
        airport_code=airport_code,
        lot_name=lot_name,
        terminal=terminal,
        available_spaces=available_spaces,
        status=status,  # type: ignore[arg-type]
        freshness=freshness,
        updated_at=datetime(2026, 3, 24, 10, 0, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} lot overview",
    )


@dataclass
class _FakeIiacParkingConnector:
    lots: list[ParkingLotSnapshot]
    slot_lots: list[ParkingLotSnapshot]
    fee_rules: list[str]

    def __post_init__(self) -> None:
        self.status_calls = 0
        self.slot_calls = 0
        self.fee_calls = 0

    async def get_parking_status(self) -> list[ParkingLotSnapshot]:
        self.status_calls += 1
        return self.lots

    async def get_t1_parking_slot_status(self) -> list[ParkingLotSnapshot]:
        self.slot_calls += 1
        return self.slot_lots

    async def get_fee_rules(self) -> list[str]:
        self.fee_calls += 1
        return self.fee_rules


@dataclass
class _FakeIiacParkingConnectorWithoutSlot:
    lots: list[ParkingLotSnapshot]
    fee_rules: list[str]

    def __post_init__(self) -> None:
        self.status_calls = 0
        self.fee_calls = 0

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


@pytest.mark.asyncio
async def test_iiac_parking_connector_fetches_and_parses_t1_slot_status() -> None:
    connector = IiacParkingConnector(
        ConnectorContext(
            timeout_sec=1.0,
            default_headers={},
            max_retries=1,
        ),
        service_key="service-key",
    )

    payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "floor": "T1 short-term",
                            "parkingarea": "100",
                            "parking": "83",
                            "status": "혼잡",
                            "datetm": "2026-03-24 10:00:00",
                        }
                    ]
                }
            }
        }
    }
    requests: list[tuple[str, dict[str, object] | None]] = []

    async def fake_get_payload(
        url: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        requests.append((url, params))
        return payload

    connector.get_payload = fake_get_payload  # type: ignore[assignment]

    lots = await connector.get_t1_parking_slot_status()

    assert requests == [
        (
            IIAC_SLOT_API_URL,
            {
                "serviceKey": "service-key",
                "pageNo": 1,
                "numOfRows": 50,
                "type": "json",
            },
        )
    ]
    assert len(lots) == 1
    slot = lots[0]
    assert slot.airport_code == "ICN"
    assert slot.lot_name == "T1 short-term"
    assert slot.terminal == "T1"
    assert slot.available_spaces == 17
    assert slot.status == "limited"
    assert slot.freshness == Freshness.LIVE
    assert slot.source[0].name == "iiac_t1_parking_slot"
    assert "slot" in slot.coverage_note.lower()


def test_icn_parking_merges_t1_slot_signal_and_fee_notes() -> None:
    connector = _FakeIiacParkingConnector(
        lots=[
            _parking_lot(
                "ICN",
                "T1 short-term",
                terminal="T1",
                available_spaces=12,
                status="available",
            ),
            _parking_lot("ICN", "T2 long-term", terminal="T2", available_spaces=100),
        ],
        slot_lots=[
            _parking_lot(
                "ICN",
                "T1 short-term slot",
                terminal="T1",
                available_spaces=6,
                status="limited",
                freshness=Freshness.LIVE,
            ).model_copy(
                update={
                    "source": [
                        SourceRef(
                            name=IIAC_SLOT_SOURCE_NAME,
                            kind=SourceKind.OFFICIAL_API,
                            url=IIAC_SLOT_DOC_URL,
                        )
                    ]
                }
            )
        ],
        fee_rules=["weekday fee", "weekend fee"],
    )

    envelope = build_parking_envelope("ICN", iiac_connector=connector)

    assert connector.status_calls == 1
    assert connector.slot_calls == 1
    assert connector.fee_calls == 1
    assert envelope.data.policy_notes == []

    lot = envelope.data.lots[0]
    assert lot.lot_name == "T1 short-term"
    assert lot.available_spaces == 6
    assert lot.status == "limited"
    assert lot.fee_note is not None
    assert "parking fee" in lot.fee_note.lower()
    assert "slot" in lot.coverage_note.lower()
    assert any(source.name == "iiac_t1_parking_slot" for source in lot.source)


def test_icn_parking_reports_slot_unavailable_without_guessing() -> None:
    connector = _FakeIiacParkingConnectorWithoutSlot(
        lots=[_parking_lot("ICN", "T1 short-term", terminal="T1", available_spaces=12)],
        fee_rules=["weekday fee"],
    )

    envelope = build_parking_envelope("ICN", iiac_connector=connector)

    lot = envelope.data.lots[0]
    assert lot.available_spaces == 12
    assert lot.status == "unknown"
    assert "slot" in lot.coverage_note.lower()
    assert "unavailable" in lot.coverage_note.lower()
    assert lot.fee_note is not None


def test_kac_parking_exposes_policy_notes_without_numeric_estimates() -> None:
    connector = _FakeKacParkingConnector(
        lots=[_parking_lot("GMP", "Domestic", available_spaces=9)],
    )

    envelope = build_parking_envelope("GMP", kac_connector=connector)

    assert connector.status_calls == ["GMP"]
    assert envelope.data.policy_notes == [
        "kac_parking_discount: official parking discount guidance",
        "kac_parking_reservation: official parking reservation guidance",
    ]
    assert envelope.data.lots[0].estimated_fee_krw is None
    assert envelope.data.lots[0].fee_note is None
