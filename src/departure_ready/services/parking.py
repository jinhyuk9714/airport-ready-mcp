from __future__ import annotations

from typing import TypeAlias

from departure_ready.catalog import (
    is_domain_supported,
    normalize_airport_code,
    normalize_terminal_code,
)
from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.iiac_parking import (
    IIAC_PARKING_DOC_URL,
    IiacParkingConnector,
)
from departure_ready.connectors.kac_parking import (
    KAC_PARKING_DOC_URL,
    KacParkingConnector,
)
from departure_ready.contracts import Envelope, ErrorEnvelope, Freshness, SourceKind, SourceRef
from departure_ready.domain.models import ParkingLotSnapshot, ParkingPayload
from departure_ready.services.common import (
    envelope_from_items,
    unsupported_domain_envelope,
)
from departure_ready.settings import Settings, get_settings


def build_parking_envelope(
    airport_code: str,
    terminal: str | None = None,
    *,
    settings: Settings | None = None,
    iiac_connector: IiacParkingConnector | None = None,
    kac_connector: KacParkingConnector | None = None,
) -> ParkingEnvelope:
    settings = settings or get_settings()
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
    selected_terminal = normalize_terminal_code(normalized_airport, terminal)

    if not is_domain_supported(normalized_airport, "parking"):
        return unsupported_domain_envelope(normalized_airport, "parking")

    connector = _resolve_connector(
        normalized_airport,
        settings=settings,
        iiac_connector=iiac_connector,
        kac_connector=kac_connector,
    )
    if connector is None:
        return _unavailable_parking_envelope(
            normalized_airport,
            selected_terminal=selected_terminal,
            requested_terminal=terminal,
            coverage_note=(
                f"Official parking data for {normalized_airport} is currently unavailable. "
                "The live connector is not configured."
            ),
        )

    try:
        lots = _get_lots(connector, normalized_airport)
    except Exception as exc:  # noqa: BLE001
        return _unavailable_parking_envelope(
            normalized_airport,
            selected_terminal=selected_terminal,
            requested_terminal=terminal,
            coverage_note=(
                f"Official parking data for {normalized_airport} is currently unavailable. "
                f"Live source failure: {exc}"
            ),
        )

    filtered_lots = _filter_lots_by_terminal(lots, selected_terminal)
    if selected_terminal and filtered_lots:
        lots = filtered_lots

    payload = ParkingPayload(
        airport_code=normalized_airport,
        terminal=selected_terminal,
        recommendation=_build_recommendation(normalized_airport, lots, selected_terminal, terminal),
        lots=lots,
        missing_inputs=_missing_inputs(selected_terminal, terminal, lots),
    )

    if lots:
        return envelope_from_items(
            payload,
            lots,
            default_note=f"Official parking data for {normalized_airport}.",
            default_source=_parking_sources(normalized_airport),
        )

    return envelope_from_items(
        payload,
        [],
        default_note=f"Official parking data for {normalized_airport} is currently unavailable.",
        default_source=_parking_sources(normalized_airport),
    )


def _unavailable_parking_envelope(
    airport_code: str,
    *,
    selected_terminal: str | None,
    requested_terminal: str | None,
    coverage_note: str,
) -> Envelope[ParkingPayload]:
    payload = ParkingPayload(
        airport_code=airport_code,
        terminal=selected_terminal,
        recommendation=f"Official parking data for {airport_code} is currently unavailable.",
        lots=[],
        missing_inputs=_missing_inputs(selected_terminal, requested_terminal, []),
    )
    return envelope_from_items(
        payload,
        [],
        default_note=coverage_note,
        default_source=_parking_sources(airport_code),
        default_freshness=Freshness.STATIC,
    )


def _resolve_connector(
    airport_code: str,
    *,
    settings: Settings,
    iiac_connector: IiacParkingConnector | None,
    kac_connector: KacParkingConnector | None,
) -> IiacParkingConnector | KacParkingConnector | None:
    context = ConnectorContext(
        timeout_sec=settings.http_timeout_sec,
        default_headers={"User-Agent": "departure-ready-mcp/0.1.0"},
        max_retries=settings.http_max_retries,
    )

    if airport_code == "ICN":
        return iiac_connector or IiacParkingConnector(context, settings.iiac_service_key)
    return kac_connector or KacParkingConnector(context, settings.kac_service_key)


def _get_lots(
    connector: IiacParkingConnector | KacParkingConnector,
    airport_code: str,
) -> list[ParkingLotSnapshot]:
    if airport_code == "ICN":
        return _await_if_needed(connector.get_parking_status())
    return _await_if_needed(connector.get_parking_status(airport_code))  # type: ignore[arg-type]


def _await_if_needed(result):
    import asyncio

    if hasattr(result, "__await__"):
        return asyncio.run(result)
    return result


def _filter_lots_by_terminal(
    lots: list[ParkingLotSnapshot],
    terminal: str | None,
) -> list[ParkingLotSnapshot]:
    if not terminal:
        return lots
    filtered = [
        lot
        for lot in lots
        if normalize_terminal_code(lot.airport_code, lot.terminal) == terminal
        or normalize_terminal_code(lot.airport_code, lot.lot_name) == terminal
    ]
    return filtered


def _build_recommendation(
    airport_code: str,
    lots: list[ParkingLotSnapshot],
    selected_terminal: str | None,
    requested_terminal: str | None,
) -> str:
    if not lots:
        return f"Official parking data for {airport_code} is currently unavailable."

    best = max(
        lots,
        key=lambda lot: lot.available_spaces if lot.available_spaces is not None else -1,
    )
    if best.available_spaces is None:
        return f"Official parking data for {airport_code} returned lot rows without live counts."

    prefix = "Best official lot"
    if selected_terminal:
        prefix = f"Best official lot for {selected_terminal}"
    elif requested_terminal:
        prefix = f"Best official lot for requested terminal {requested_terminal}"
    return f"{prefix}: {best.lot_name} with {best.available_spaces} spaces open."


def _missing_inputs(
    selected_terminal: str | None,
    requested_terminal: str | None,
    lots: list[ParkingLotSnapshot],
) -> list[str]:
    missing: list[str] = []
    if requested_terminal and not selected_terminal:
        missing.append(f"terminal:{requested_terminal}")
    if requested_terminal and selected_terminal and not lots:
        missing.append(f"terminal:{requested_terminal}")
    return missing


def _parking_sources(airport_code: str) -> list[SourceRef]:
    if airport_code == "ICN":
        return [
            SourceRef(
                name="iiac_parking_rt",
                kind=SourceKind.OFFICIAL_API,
                url=IIAC_PARKING_DOC_URL,
            )
        ]
    return [
        SourceRef(
            name="kac_parking_rt",
            kind=SourceKind.OFFICIAL_API,
            url=KAC_PARKING_DOC_URL,
        )
    ]


ParkingEnvelope: TypeAlias = Envelope[ParkingPayload] | ErrorEnvelope
