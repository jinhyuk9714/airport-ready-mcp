from __future__ import annotations

from datetime import datetime

from departure_ready.catalog import normalize_airport_code
from departure_ready.connectors.base import (
    ConnectorContext,
    OfficialConnector,
    extract_items,
    parse_datetime_multi,
)
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import FlightSnapshot

KAC_FLIGHT_DOC_URL = "https://www.data.go.kr/data/15113771/openapi.do"
KAC_FLIGHT_API_URL = "https://api.odcloud.kr/api/FlightStatusListDTL/v1/getFlightStatusListDetail"


class KacFlightConnector(OfficialConnector):
    source_name = "kac_flight_detail_rt"
    source_url = KAC_FLIGHT_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None) -> None:
        super().__init__(context, service_key=service_key)

    async def get_flight_status(
        self,
        airport_code: str,
        flight_no: str | None = None,
    ) -> list[FlightSnapshot]:
        service_key = self.require_service_key()
        normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
        params = {
            "serviceKey": service_key,
            "page": 1,
            "perPage": 50,
            "returnType": "JSON",
            "cond[AIRPORT::EQ]": normalized_airport,
        }
        if flight_no:
            params["cond[AIR_FLN::EQ]"] = flight_no

        payload = await self.get_payload(KAC_FLIGHT_API_URL, params=params)
        return self.parse_flight_payload(payload, normalized_airport)

    def parse_flight_payload(
        self,
        payload: dict,
        airport_code: str,
    ) -> list[FlightSnapshot]:
        rows = extract_items(payload)
        snapshots: list[FlightSnapshot] = []

        for row in rows:
            snapshots.append(
                FlightSnapshot(
                    airport_code=airport_code.upper(),
                    flight_no=row.get("AIR_FLN"),
                    airline=row.get("AIRLINE_KOREAN") or row.get("AIRLINE_ENGLISH"),
                    gate=row.get("GATE"),
                    checkin_counter=row.get("BOARDING_KOR") or row.get("BOARDING_ENG"),
                    scheduled_at=parse_datetime_multi(
                        row.get("STD"),
                        "%Y-%m-%d %H:%M",
                        "%Y%m%d%H%M%S",
                    ),
                    changed_at=parse_datetime_multi(
                        row.get("ETD"),
                        "%Y-%m-%d %H:%M",
                        "%Y%m%d%H%M%S",
                    ),
                    status_label=row.get("RMK_KOR") or row.get("RMK_ENG"),
                    freshness=Freshness.LIVE,
                    updated_at=datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name=self.source_name,
                            kind=SourceKind.OFFICIAL_API,
                            url=self.source_url,
                        )
                    ],
                    coverage_note=f"KAC live flight detail for {airport_code.upper()}",
                )
            )

        return snapshots
