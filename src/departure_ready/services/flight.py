from __future__ import annotations

from pydantic import BaseModel, Field

from departure_ready.catalog import is_domain_supported, normalize_airport_code
from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.iiac_flight import (
    IIAC_FORECAST_DOC_URL,
    IIAC_TODAY_DOC_URL,
    IiacFlightConnector,
)
from departure_ready.connectors.kac_flight import KAC_FLIGHT_DOC_URL, KacFlightConnector
from departure_ready.contracts import (
    Envelope,
    ErrorEnvelope,
    Freshness,
    SourceKind,
    SourceRef,
)
from departure_ready.domain.models import FlightSnapshot, OperationalSignal
from departure_ready.services.common import (
    envelope_from_items,
    error_envelope,
    unsupported_domain_envelope,
)
from departure_ready.settings import Settings, get_settings


class FlightPayload(BaseModel):
    airport_code: str
    status: str
    summary: str
    live_flights: list[FlightSnapshot] = Field(default_factory=list)
    forecast_signals: list[OperationalSignal] = Field(default_factory=list)
    selected_flight: FlightSnapshot | None = None
    missing_inputs: list[str] = Field(default_factory=list)


def build_flight_envelope(
    airport_code: str,
    flight_no: str | None = None,
    *,
    settings: Settings | None = None,
    iiac_connector: IiacFlightConnector | None = None,
    kac_connector: KacFlightConnector | None = None,
) -> Envelope[FlightPayload] | ErrorEnvelope:
    settings = settings or get_settings()
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()

    if not is_domain_supported(normalized_airport, "flight_status"):
        return unsupported_domain_envelope(normalized_airport, "flight_status")

    connector = _resolve_connector(
        normalized_airport,
        settings=settings,
        iiac_connector=iiac_connector,
        kac_connector=kac_connector,
    )
    if connector is None:
        return error_envelope(
            code="live_source_unavailable",
            message=f"No live flight connector configured for {normalized_airport}.",
            coverage_note=f"Official flight data for {normalized_airport} is unavailable.",
            hint="Check the configured airport coverage and source keys.",
            source=_flight_sources(normalized_airport),
            freshness=Freshness.STATIC,
        )

    try:
        live_flights, forecast_signals = _load_flight_data(
            connector,
            normalized_airport,
            flight_no=flight_no,
        )
    except Exception as exc:  # noqa: BLE001
        return error_envelope(
            code="live_source_unavailable",
            message=str(exc),
            coverage_note=(
                f"Official flight data for {normalized_airport} is unavailable right now."
            ),
            hint="The live source failed or returned invalid data. Try again later.",
            source=_flight_sources(normalized_airport),
            freshness=Freshness.STATIC,
        )

    selected_flight = _select_flight(live_flights, flight_no)
    status = _status_for(live_flights, forecast_signals)
    summary = _summary_for(normalized_airport, status, live_flights, forecast_signals, flight_no)
    missing_inputs = []
    if flight_no and not selected_flight:
        missing_inputs.append(f"flight_no:{flight_no}")

    payload = FlightPayload(
        airport_code=normalized_airport,
        status=status,
        summary=summary,
        live_flights=live_flights,
        forecast_signals=forecast_signals,
        selected_flight=selected_flight,
        missing_inputs=missing_inputs,
    )

    items: list[FlightSnapshot | OperationalSignal] = [*live_flights, *forecast_signals]
    if items:
        envelope = envelope_from_items(
            payload,
            items,
            default_note=f"Official flight data for {normalized_airport}.",
            default_source=_flight_sources(normalized_airport),
            default_freshness=Freshness.FORECAST if forecast_signals else Freshness.LIVE,
        )
        if forecast_signals:
            envelope.meta.freshness = Freshness.FORECAST
        return envelope

    return envelope_from_items(
        payload,
        [],
        default_note=f"Official flight data for {normalized_airport} is currently unavailable.",
        default_source=_flight_sources(normalized_airport),
    )


def _resolve_connector(
    airport_code: str,
    *,
    settings: Settings,
    iiac_connector: IiacFlightConnector | None,
    kac_connector: KacFlightConnector | None,
) -> IiacFlightConnector | KacFlightConnector | None:
    context = ConnectorContext(
        timeout_sec=settings.http_timeout_sec,
        default_headers={"User-Agent": "departure-ready-mcp/0.1.0"},
        max_retries=settings.http_max_retries,
    )

    if airport_code == "ICN":
        return iiac_connector or IiacFlightConnector(context, settings.iiac_service_key)
    return kac_connector or KacFlightConnector(context, settings.kac_service_key)


def _load_flight_data(
    connector: IiacFlightConnector | KacFlightConnector,
    airport_code: str,
    *,
    flight_no: str | None,
) -> tuple[list[FlightSnapshot], list[OperationalSignal]]:
    if airport_code == "ICN":
        live_flights = _ensure_list(connector.get_today_flights(flight_no))
        forecast_signals = _ensure_list(connector.get_passenger_forecast())
        return live_flights, forecast_signals

    live_flights = _ensure_list(connector.get_flight_status(airport_code, flight_no))
    return live_flights, []


def _ensure_list(result):
    import asyncio

    if hasattr(result, "__await__"):
        return asyncio.run(result)
    return result


def _select_flight(
    live_flights: list[FlightSnapshot],
    flight_no: str | None,
) -> FlightSnapshot | None:
    if not live_flights:
        return None
    if not flight_no:
        return live_flights[0]
    for flight in live_flights:
        if flight.flight_no == flight_no:
            return flight
    return None


def _status_for(
    live_flights: list[FlightSnapshot],
    forecast_signals: list[OperationalSignal],
) -> str:
    if live_flights and forecast_signals:
        return "mixed"
    if live_flights:
        return "live"
    if forecast_signals:
        return "forecast"
    return "unavailable"


def _summary_for(
    airport_code: str,
    status: str,
    live_flights: list[FlightSnapshot],
    forecast_signals: list[OperationalSignal],
    flight_no: str | None,
) -> str:
    if status == "mixed":
        return (
            f"{airport_code} has live flight rows and forecast crowd signals from official sources."
        )
    if status == "live":
        if flight_no:
            return f"{airport_code} live flight status is available for {flight_no}."
        return f"{airport_code} live flight status is available from the official source."
    if status == "forecast":
        return f"{airport_code} has only forecast signals from the official source right now."
    return f"{airport_code} flight data is unavailable from official sources right now."


def _flight_sources(airport_code: str) -> list[SourceRef]:
    if airport_code == "ICN":
        return [
            SourceRef(
                name="iiac_flight_today",
                kind=SourceKind.OFFICIAL_API,
                url=IIAC_TODAY_DOC_URL,
            ),
            SourceRef(
                name="iiac_passenger_forecast",
                kind=SourceKind.OFFICIAL_API,
                url=IIAC_FORECAST_DOC_URL,
            ),
        ]
    return [
        SourceRef(
            name="kac_flight_detail_rt",
            kind=SourceKind.OFFICIAL_API,
            url=KAC_FLIGHT_DOC_URL,
        )
    ]
