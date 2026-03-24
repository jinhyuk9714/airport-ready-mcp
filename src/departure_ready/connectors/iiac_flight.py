from __future__ import annotations

from datetime import datetime

from departure_ready.connectors.base import (
    ConnectorContext,
    OfficialConnector,
    extract_items,
    parse_datetime_multi,
)
from departure_ready.connectors.iiac_parking import infer_iiac_terminal
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import FlightSnapshot, OperationalSignal

IIAC_TODAY_DOC_URL = "https://www.data.go.kr/data/15095093/openapi.do"
IIAC_TODAY_API_URL = (
    "http://apis.data.go.kr/B551177/StatusOfPassengerFlightsOdp/getPassengerDeparturesOdp"
)
IIAC_WEEKLY_DOC_URL = "https://www.data.go.kr/data/15095074/openapi.do"
IIAC_WEEKLY_API_URL = (
    "http://apis.data.go.kr/B551177/StatusOfPassengerFlightsDSOdp/getPassengerDeparturesDSOdp"
)
IIAC_FORECAST_DOC_URL = "https://www.data.go.kr/data/15095066/openapi.do"
IIAC_FORECAST_API_URL = "http://apis.data.go.kr/B551177/passgrAnncmt/getPassgrAnncmt"


class IiacFlightConnector(OfficialConnector):
    source_name = "iiac_flight_today"
    source_url = IIAC_TODAY_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None) -> None:
        super().__init__(context, service_key=service_key)

    async def get_today_flights(self, flight_no: str | None = None) -> list[FlightSnapshot]:
        service_key = self.require_service_key()
        params = {
            "serviceKey": service_key,
            "from_time": "0000",
            "to_time": "2400",
            "lang": "K",
            "type": "json",
        }
        if flight_no:
            params["flight_id"] = flight_no
        payload = await self.get_payload(IIAC_TODAY_API_URL, params=params)
        return self.parse_today_payload(payload)

    async def get_passenger_forecast(self, selectdate: int = 0) -> list[OperationalSignal]:
        service_key = self.require_service_key()
        payload = await self.get_payload(
            IIAC_FORECAST_API_URL,
            params={
                "serviceKey": service_key,
                "selectdate": selectdate,
                "pageNo": 1,
                "numOfRows": 50,
                "type": "json",
            },
        )
        return self.parse_forecast_payload(payload)

    def parse_today_payload(self, payload: dict) -> list[FlightSnapshot]:
        rows = extract_items(payload)
        flights: list[FlightSnapshot] = []
        for row in rows:
            flights.append(
                FlightSnapshot(
                    airport_code="ICN",
                    flight_no=row.get("flightId"),
                    airline=row.get("airline"),
                    terminal=infer_iiac_terminal(row.get("terminalId")),
                    gate=row.get("gatenumber"),
                    checkin_counter=row.get("checkincounter"),
                    scheduled_at=parse_datetime_multi(
                        row.get("scheduleDateTime"),
                        "%Y%m%d%H%M%S",
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    changed_at=parse_datetime_multi(
                        row.get("estimatedDateTime"),
                        "%Y%m%d%H%M%S",
                        "%Y-%m-%d %H:%M:%S",
                    ),
                    status_label=row.get("remark"),
                    freshness=Freshness.LIVE,
                    updated_at=datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name=self.source_name,
                            kind=SourceKind.OFFICIAL_API,
                            url=self.source_url,
                        )
                    ],
                    coverage_note="IIAC same-day passenger flight status",
                )
            )
        return flights

    def parse_forecast_payload(self, payload: dict) -> list[OperationalSignal]:
        rows = extract_items(payload)
        signals: list[OperationalSignal] = []
        for row in rows:
            zone = (
                row.get("termtype")
                or row.get("terminalid")
                or row.get("gateid")
                or row.get("zonenm")
                or "forecast zone"
            )
            count = (
                row.get("forecastcount")
                or row.get("passenger")
                or row.get("forecnt")
                or row.get("sumcnt")
                or "unknown"
            )
            time_text = row.get("timezone") or row.get("stdHour") or row.get("tm")
            signals.append(
                OperationalSignal(
                    airport_code="ICN",
                    signal_type="crowd_forecast",
                    headline=f"{zone} forecast",
                    detail=f"Forecast passengers {count} at {time_text or 'scheduled time'}",
                    freshness=Freshness.FORECAST,
                    updated_at=datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name="iiac_passenger_forecast",
                            kind=SourceKind.OFFICIAL_API,
                            url=IIAC_FORECAST_DOC_URL,
                        )
                    ],
                    coverage_note="IIAC passenger forecast by zone",
                )
            )
        return signals
