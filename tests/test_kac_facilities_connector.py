from __future__ import annotations

import pytest

from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.kac_facilities import (
    KAC_ACCESSIBILITY_DOC_URL,
    KAC_FACILITY_DOC_URL,
    KacFacilitiesConnector,
)
from departure_ready.contracts import Freshness, SourceKind


@pytest.mark.asyncio
async def test_kac_facilities_connector_parses_facility_rows() -> None:
    connector = KacFacilitiesConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    requests: list[tuple[str, dict[str, object] | None]] = []

    async def fake_get_payload(
        url: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        requests.append((url, params))
        return {
            "data": [
                {
                    "airport_code": "GMP",
                    "terminal": "T1",
                    "name": "약국",
                    "category": "pharmacy",
                    "location_text": "1층 국내선",
                    "floor": "1F",
                    "phone": "02-000-0000",
                }
            ]
        }

    connector.get_payload = fake_get_payload  # type: ignore[assignment]

    matches = await connector.get_facility_file("GMP")

    assert requests == [(KAC_FACILITY_DOC_URL, None)]
    assert len(matches) == 1
    match = matches[0]
    assert match.airport_code == "GMP"
    assert match.terminal == "T1"
    assert match.name == "약국"
    assert match.category == "pharmacy"
    assert match.location_text == "1층 국내선"
    assert match.freshness == Freshness.STATIC
    assert match.source[0].name == "kac_facility_file"
    assert match.source[0].kind == SourceKind.FILE_DATA


@pytest.mark.asyncio
async def test_kac_facilities_accessibility_rows_keep_terminal_none() -> None:
    connector = KacFacilitiesConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")

    async def fake_get_payload(
        url: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        assert url == KAC_ACCESSIBILITY_DOC_URL
        return {
            "data": [
                {
                    "airport_name": "김해공항",
                    "name": "휠체어",
                    "location_text": "도착층 안내데스크 옆",
                    "floor": "1F",
                }
            ]
        }

    connector.get_payload = fake_get_payload  # type: ignore[assignment]

    matches = await connector.get_accessibility_file("PUS")

    assert len(matches) == 1
    match = matches[0]
    assert match.airport_code == "PUS"
    assert match.terminal is None
    assert match.name == "휠체어"
    assert match.category == "accessibility"
    assert match.location_text == "도착층 안내데스크 옆"
    assert match.freshness == Freshness.STATIC
    assert match.source[0].name == "kac_accessibility_file"


@pytest.mark.asyncio
async def test_kac_facilities_connector_preserves_missing_terminal_and_location() -> None:
    connector = KacFacilitiesConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")

    async def fake_get_payload(
        url: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "data": [
                {
                    "airport_code": "CJJ",
                    "name": "화장실",
                    "category": "restroom",
                }
            ]
        }

    connector.get_payload = fake_get_payload  # type: ignore[assignment]

    matches = await connector.get_facility_file("CJJ")

    assert len(matches) == 1
    match = matches[0]
    assert match.terminal is None
    assert match.location_text == ""
    assert match.name == "화장실"
    assert match.category == "restroom"


@pytest.mark.asyncio
async def test_kac_facilities_connector_combines_and_deduplicates_rows() -> None:
    connector = KacFacilitiesConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    calls: list[str] = []

    async def fake_get_payload(
        url: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, object]:
        calls.append(url)
        if url == KAC_FACILITY_DOC_URL:
            return {
                "data": [
                    {
                        "airport_code": "TAE",
                        "terminal": "T1",
                        "name": "라운지",
                        "category": "lounge",
                        "location_text": "출발층",
                    },
                    {
                        "airport_code": "TAE",
                        "terminal": "T1",
                        "name": "라운지",
                        "category": "lounge",
                        "location_text": "출발층",
                    },
                ]
            }
        return {
            "data": [
                {
                    "airport_code": "TAE",
                    "name": "휠체어",
                    "category": "accessibility",
                    "location_text": "안내데스크",
                },
                {
                    "airport_code": "TAE",
                    "name": "휠체어",
                    "category": "accessibility",
                    "location_text": "안내데스크",
                },
            ]
        }

    connector.get_payload = fake_get_payload  # type: ignore[assignment]

    matches = await connector.get_facility_matches("TAE")

    assert calls == [KAC_FACILITY_DOC_URL, KAC_ACCESSIBILITY_DOC_URL]
    assert len(matches) == 2
    assert [match.category for match in matches] == ["lounge", "accessibility"]
    assert all(match.updated_at.tzinfo is not None for match in matches)
