from __future__ import annotations

from datetime import datetime

from departure_ready.catalog import normalize_airport_code
from departure_ready.connectors.base import (
    ConnectorContext,
    OfficialConnector,
    as_int,
    extract_items,
    parse_datetime,
)
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import ParkingLotSnapshot

KAC_PARKING_DOC_URL = "https://www.data.go.kr/data/15056803/openapi.do"
KAC_PARKING_API_URL = "http://openapi.airport.co.kr/service/rest/AirportParking/airportparkingRT"
KAC_CONGESTION_DOC_URL = "https://www.data.go.kr/data/15063437/openapi.do"
KAC_CONGESTION_API_URL = (
    "http://openapi.airport.co.kr/service/rest/AirportParkingCongestion/airportParkingCongestionRT"
)


class KacParkingConnector(OfficialConnector):
    source_name = "kac_parking_rt"
    source_url = KAC_PARKING_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None) -> None:
        super().__init__(context, service_key=service_key)

    async def get_parking_status(self, airport_code: str) -> list[ParkingLotSnapshot]:
        service_key = self.require_service_key()
        normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
        status_payload = await self.get_payload(
            KAC_PARKING_API_URL,
            params={"serviceKey": service_key, "schAirportCode": normalized_airport},
        )
        lots = self.parse_status_payload(status_payload, normalized_airport)

        congestion_payload = await self.get_payload(
            KAC_CONGESTION_API_URL,
            params={
                "ServiceKey": service_key,
                "pageNo": 1,
                "numOfRows": 50,
                "schAirportCode": normalized_airport,
            },
        )
        return self.apply_congestion_payload(lots, congestion_payload)

    def parse_status_payload(
        self,
        payload: dict,
        airport_code: str,
    ) -> list[ParkingLotSnapshot]:
        rows = extract_items(payload)
        snapshots: list[ParkingLotSnapshot] = []

        for row in rows:
            total = as_int(row.get("parkingFullSpace"))
            occupied = as_int(row.get("parkingIstay"))
            available = None
            occupancy = None
            if total is not None and occupied is not None:
                available = max(total - occupied, 0)
                occupancy = round((occupied / total) * 100, 2) if total else None

            snapshots.append(
                ParkingLotSnapshot(
                    airport_code=airport_code.upper(),
                    lot_name=row.get("parkingAirportCodeName") or "Unknown lot",
                    available_spaces=available,
                    occupancy_pct=occupancy,
                    freshness=Freshness.LIVE,
                    updated_at=parse_datetime(
                        row.get("parkingGetdate"),
                        row.get("parkingGettime"),
                        fmt="%Y%m%d%H%M%S",
                    )
                    or datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name=self.source_name,
                            kind=SourceKind.OFFICIAL_API,
                            url=self.source_url,
                        )
                    ],
                    coverage_note=f"KAC live parking status for {airport_code.upper()}",
                )
            )

        return snapshots

    def apply_congestion_payload(
        self,
        lots: list[ParkingLotSnapshot],
        payload: dict,
    ) -> list[ParkingLotSnapshot]:
        congestion_by_name = {
            row.get("parkingAirportCodeName"): row
            for row in extract_items(payload)
            if row.get("parkingAirportCodeName")
        }
        merged: list[ParkingLotSnapshot] = []

        for lot in lots:
            row = congestion_by_name.get(lot.lot_name)
            if row is None:
                merged.append(lot)
                continue

            total = as_int(row.get("parkingTotalSpace"))
            occupied = as_int(row.get("parkingOccupiedSpace"))
            available = lot.available_spaces
            occupancy = lot.occupancy_pct
            if total is not None and occupied is not None:
                available = max(total - occupied, 0)
                occupancy = round((occupied / total) * 100, 2) if total else None

            merged.append(
                lot.model_copy(
                    update={
                        "available_spaces": available,
                        "occupancy_pct": occupancy,
                        "congestion_label": row.get("parkingCongestion"),
                        "source": [
                            *lot.source,
                            SourceRef(
                                name="kac_parking_congestion_rt",
                                kind=SourceKind.OFFICIAL_API,
                                url=KAC_CONGESTION_DOC_URL,
                            ),
                        ],
                        "coverage_note": (f"{lot.coverage_note}; includes KAC congestion signal"),
                    }
                )
            )

        return merged
