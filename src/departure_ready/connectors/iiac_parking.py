from __future__ import annotations

from datetime import datetime

from departure_ready.connectors.base import (
    ConnectorContext,
    OfficialConnector,
    as_int,
    extract_items,
    parse_datetime_multi,
)
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import ParkingLotSnapshot

IIAC_PARKING_DOC_URL = "https://www.data.go.kr/data/15095047/openapi.do"
IIAC_PARKING_API_URL = "http://apis.data.go.kr/B551177/StatusOfParking/getTrackingParking"
IIAC_FEE_DOC_URL = "https://www.data.go.kr/data/15095053/openapi.do"
IIAC_FEE_API_URL = "http://apis.data.go.kr/B551177/ParkingChargeInfo/getParkingChargeInformation"
IIAC_SLOT_DOC_URL = "https://www.data.go.kr/data/15107228/openapi.do"
IIAC_SLOT_API_URL = "http://apis.data.go.kr/B551177/ParkLocationData/getParkLocationData"
IIAC_SLOT_SOURCE_NAME = "iiac_t1_parking_slot"


class IiacParkingConnector(OfficialConnector):
    source_name = "iiac_parking_rt"
    source_url = IIAC_PARKING_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None) -> None:
        super().__init__(context, service_key=service_key)

    async def get_parking_status(self) -> list[ParkingLotSnapshot]:
        service_key = self.require_service_key()
        payload = await self.get_payload(
            IIAC_PARKING_API_URL,
            params={"serviceKey": service_key, "pageNo": 1, "numOfRows": 50, "type": "json"},
        )
        return self.parse_status_payload(payload)

    async def get_fee_rules(self) -> list[str]:
        service_key = self.require_service_key()
        payload = await self.get_payload(
            IIAC_FEE_API_URL,
            params={"serviceKey": service_key, "pageNo": 1, "numOfRows": 50, "type": "json"},
        )
        return self.parse_fee_payload(payload)

    async def get_t1_parking_slot_status(self) -> list[ParkingLotSnapshot]:
        service_key = self.require_service_key()
        payload = await self.get_payload(
            IIAC_SLOT_API_URL,
            params={"serviceKey": service_key, "pageNo": 1, "numOfRows": 50, "type": "json"},
        )
        return self.parse_t1_parking_slot_payload(payload)

    def parse_status_payload(self, payload: dict) -> list[ParkingLotSnapshot]:
        rows = extract_items(payload)
        snapshots: list[ParkingLotSnapshot] = []
        for row in rows:
            total = as_int(row.get("parkingarea"))
            occupied = as_int(row.get("parking"))
            available = None
            occupancy = None
            if total is not None and occupied is not None:
                available = max(total - occupied, 0)
                occupancy = round((occupied / total) * 100, 2) if total else None
            floor = row.get("floor") or "Parking lot"
            snapshots.append(
                ParkingLotSnapshot(
                    airport_code="ICN",
                    lot_name=floor,
                    terminal=infer_iiac_terminal(floor),
                    available_spaces=available,
                    occupancy_pct=occupancy,
                    freshness=Freshness.LIVE,
                    updated_at=parse_datetime_multi(
                        row.get("datetm"),
                        "%Y-%m-%d %H:%M:%S",
                        "%Y%m%d%H%M%S",
                    )
                    or datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name=self.source_name,
                            kind=SourceKind.OFFICIAL_API,
                            url=self.source_url,
                        )
                    ],
                    coverage_note="IIAC live parking overview",
                )
            )
        return snapshots

    def parse_fee_payload(self, payload: dict) -> list[str]:
        rules: list[str] = []
        for row in extract_items(payload):
            title = (
                row.get("chardesc")
                or row.get("charnm")
                or row.get("charge")
                or row.get("detail")
            )
            if not title:
                continue

            parts: list[str] = [str(title)]
            extra = _join_present(
                [
                    row.get("weekday"),
                    row.get("weekend"),
                    row.get("time"),
                    row.get("note"),
                ]
            )
            if extra:
                parts.append(extra)
            rules.append(" - ".join(parts))
        return rules

    def parse_t1_parking_slot_payload(self, payload: dict) -> list[ParkingLotSnapshot]:
        snapshots: list[ParkingLotSnapshot] = []
        for row in extract_items(payload):
            lot_name = _first_present(
                row,
                "floor",
                "parkingName",
                "parkinglotname",
                "parkingAirportCodeName",
                default="T1 short-term",
            )
            terminal = (
                infer_iiac_terminal(lot_name)
                or infer_iiac_terminal(_first_present(row, "terminal", "parkingAirportCodeName"))
                or "T1"
            )
            total = as_int(
                _first_present(
                    row,
                    "parkingarea",
                    "parkingFullSpace",
                    "parkingTotalSpace",
                    "parkingavailable",
                )
            )
            occupied = as_int(
                _first_present(
                    row,
                    "parking",
                    "parkingIstay",
                    "parkingOccupiedSpace",
                    "occupiedSpace",
                )
            )
            available = as_int(
                _first_present(
                    row,
                    "availableSpace",
                    "parkingAvailableSpace",
                    "remainingSpace",
                )
            )
            if available is None and total is not None and occupied is not None:
                available = max(total - occupied, 0)

            occupancy_pct = None
            if total is not None and occupied is not None:
                occupancy_pct = round((occupied / total) * 100, 2) if total else None

            snapshots.append(
                ParkingLotSnapshot(
                    airport_code="ICN",
                    lot_name=lot_name,
                    terminal=terminal,
                    available_spaces=available,
                    occupancy_pct=occupancy_pct,
                    status=_slot_status_from_row(row, available),
                    freshness=Freshness.LIVE,
                    updated_at=parse_datetime_multi(
                        _first_present(row, "datetm", "updated_at", "timestamp"),
                        "%Y-%m-%d %H:%M:%S",
                        "%Y%m%d%H%M%S",
                    )
                    or datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name=IIAC_SLOT_SOURCE_NAME,
                            kind=SourceKind.OFFICIAL_API,
                            url=IIAC_SLOT_DOC_URL,
                        )
                    ],
                    coverage_note="IIAC T1 parking slot status",
                )
            )
        return snapshots


def _join_present(values: list[str | None]) -> str | None:
    present = [str(value) for value in values if value]
    if not present:
        return None
    return ", ".join(present)


def _first_present(row: dict[str, object], *keys: str, default: str | None = None) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return default or ""


def _slot_status_from_row(row: dict[str, object], available: int | None) -> str:
    raw_status = _first_present(
        row,
        "parkingStatus",
        "parkingState",
        "status",
        "parkingCongestion",
        default="",
    ).lower()

    if raw_status:
        if any(token in raw_status for token in ("full", "만차", "closed", "폐쇄")):
            return "full"
        if any(token in raw_status for token in ("available", "open", "여유", "원활", "가능")):
            return "available"
        if any(token in raw_status for token in ("limited", "혼잡", "보통", "주의", "busy")):
            return "limited"
        if any(token in raw_status for token in ("unavailable", "불가", "미운영")):
            return "unavailable"

    if available is None:
        return "unknown"
    if available <= 0:
        return "full"
    if available <= 10:
        return "limited"
    return "available"


def infer_iiac_terminal(value: str | None) -> str | None:
    if not value:
        return None
    upper_value = value.upper()
    if "T1" in upper_value or "제1" in value or "P03" in upper_value:
        return "T1"
    if "T2" in upper_value or "제2" in value or "P02" in upper_value:
        return "T2"
    return None
