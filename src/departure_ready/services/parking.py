from __future__ import annotations

from typing import TypeAlias

from departure_ready.catalog import (
    is_domain_supported,
    normalize_airport_code,
    normalize_terminal_code,
)
from departure_ready.connectors.base import ConnectorContext
from departure_ready.connectors.iiac_parking import (
    IIAC_FEE_DOC_URL,
    IIAC_PARKING_DOC_URL,
    IiacParkingConnector,
)
from departure_ready.connectors.kac_parking import (
    KAC_PARKING_DOC_URL,
    KacParkingConnector,
)
from departure_ready.connectors.policy import (
    KAC_PARKING_DISCOUNT,
    KAC_PARKING_RESERVATION,
)
from departure_ready.contracts import Envelope, ErrorEnvelope, Freshness, SourceKind, SourceRef
from departure_ready.domain.models import ParkingLotSnapshot, ParkingPayload
from departure_ready.services.common import (
    await_if_needed,
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

    if normalized_airport == "ICN":
        lots = _apply_icn_slot_signals(connector, lots)

    fee_rules = _get_fee_rules(connector) if normalized_airport == "ICN" else []
    lots = _apply_fee_notes(normalized_airport, lots, fee_rules)

    payload = ParkingPayload(
        airport_code=normalized_airport,
        terminal=selected_terminal,
        recommendation=_build_recommendation(normalized_airport, lots, selected_terminal, terminal),
        lots=lots,
        missing_inputs=_missing_inputs(selected_terminal, terminal, lots),
        policy_notes=_parking_policy_notes(normalized_airport),
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


def _get_fee_rules(connector: IiacParkingConnector | KacParkingConnector) -> list[str]:
    getter = getattr(connector, "get_fee_rules", None)
    if getter is None:
        return []
    result = _await_if_needed(getter())
    return [str(rule) for rule in result if str(rule).strip()]


def _get_t1_slot_lots(
    connector: IiacParkingConnector | KacParkingConnector,
) -> list[ParkingLotSnapshot] | None:
    getter = getattr(connector, "get_t1_parking_slot_status", None)
    if getter is None:
        return None
    result = _await_if_needed(getter())
    return list(result)


def _await_if_needed(result):
    return await_if_needed(result)


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


def _apply_fee_notes(
    airport_code: str,
    lots: list[ParkingLotSnapshot],
    fee_rules: list[str],
) -> list[ParkingLotSnapshot]:
    if airport_code != "ICN":
        return lots

    note = _build_icn_fee_note(fee_rules)
    if note is None:
        return [
            lot.model_copy(
                update={
                    "fee_note": (
                        f"ICN parking fee criteria unavailable for {lot.lot_name}; "
                        "live parking counts still shown."
                    ),
                    "source": [
                        *lot.source,
                        SourceRef(
                            name="iiac_parking_fee",
                            kind=SourceKind.OFFICIAL_API,
                            url=IIAC_FEE_DOC_URL,
                        ),
                    ],
                    "coverage_note": f"{lot.coverage_note}; fee criteria unavailable",
                }
            )
            for lot in lots
        ]

    return [
        lot.model_copy(
            update={
                "fee_note": f"ICN parking fee criteria for {lot.lot_name}: {note}",
                "source": [
                    *lot.source,
                    SourceRef(
                        name="iiac_parking_fee",
                        kind=SourceKind.OFFICIAL_API,
                        url=IIAC_FEE_DOC_URL,
                    ),
                ],
                "coverage_note": f"{lot.coverage_note}; includes IIAC parking fee criteria",
            }
        )
        for lot in lots
    ]


def _apply_icn_slot_signals(
    connector: IiacParkingConnector | KacParkingConnector,
    lots: list[ParkingLotSnapshot],
) -> list[ParkingLotSnapshot]:
    try:
        slot_lots = _get_t1_slot_lots(connector)
    except Exception as exc:  # noqa: BLE001
        return _annotate_icn_t1_slot_unavailable(
            lots,
            f"IIAC T1 parking slot source unavailable: {exc}",
        )

    if not slot_lots:
        return _annotate_icn_t1_slot_unavailable(
            lots,
            "IIAC T1 parking slot source unavailable",
        )

    merged = _merge_icn_t1_slot_lots(lots, slot_lots)
    if merged == lots:
        return _annotate_icn_t1_slot_unavailable(
            lots,
            "IIAC T1 parking slot source returned no matching T1 rows",
        )
    return merged


def _merge_icn_t1_slot_lots(
    lots: list[ParkingLotSnapshot],
    slot_lots: list[ParkingLotSnapshot],
) -> list[ParkingLotSnapshot]:
    merged: list[ParkingLotSnapshot] = []
    slot_candidates = [slot for slot in slot_lots if _is_icn_t1_short_term_lot(slot)]

    for lot in lots:
        if not _is_icn_t1_short_term_lot(lot):
            merged.append(lot)
            continue

        slot = _match_slot_lot(lot, slot_candidates)
        if slot is None:
            merged.append(
                lot.model_copy(
                    update={
                        "coverage_note": (
                            f"{lot.coverage_note}; IIAC T1 parking slot source unavailable"
                        ),
                    }
                )
            )
            continue

        merged.append(
            lot.model_copy(
                update={
                    "available_spaces": slot.available_spaces
                    if slot.available_spaces is not None
                    else lot.available_spaces,
                    "occupancy_pct": slot.occupancy_pct
                    if slot.occupancy_pct is not None
                    else lot.occupancy_pct,
                    "status": slot.status,
                    "source": _merge_sources(lot.source, slot.source),
                    "coverage_note": f"{lot.coverage_note}; includes IIAC T1 parking slot status",
                }
            )
        )

    return merged


def _annotate_icn_t1_slot_unavailable(
    lots: list[ParkingLotSnapshot],
    note: str,
) -> list[ParkingLotSnapshot]:
    return [
        lot.model_copy(
            update={
                "coverage_note": f"{lot.coverage_note}; {note}"
                if _is_icn_t1_short_term_lot(lot)
                else lot.coverage_note,
            }
        )
        for lot in lots
    ]


def _match_slot_lot(
    lot: ParkingLotSnapshot,
    slot_candidates: list[ParkingLotSnapshot],
) -> ParkingLotSnapshot | None:
    if not slot_candidates:
        return None
    lot_terminal = normalize_terminal_code(lot.airport_code, lot.terminal)
    for slot in slot_candidates:
        if normalize_terminal_code(slot.airport_code, slot.terminal) == lot_terminal:
            return slot
        if slot.lot_name == lot.lot_name:
            return slot
    return slot_candidates[0]


def _merge_sources(
    existing: list[SourceRef],
    extra: list[SourceRef],
) -> list[SourceRef]:
    merged: list[SourceRef] = []
    seen: set[tuple[str, SourceKind, str]] = set()
    for source in [*existing, *extra]:
        key = (source.name, source.kind, source.url)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged


def _is_icn_t1_short_term_lot(lot: ParkingLotSnapshot) -> bool:
    terminal = normalize_terminal_code(lot.airport_code, lot.terminal)
    if terminal == "T1":
        return True
    lot_name = lot.lot_name.upper()
    return "T1" in lot_name or "제1" in lot.lot_name


def _parking_policy_notes(airport_code: str) -> list[str]:
    if airport_code == "ICN":
        return []
    return [
        f"{KAC_PARKING_DISCOUNT.name}: official parking discount guidance",
        f"{KAC_PARKING_RESERVATION.name}: official parking reservation guidance",
    ]


def _build_icn_fee_note(fee_rules: list[str]) -> str | None:
    if not fee_rules:
        return None
    selected = [rule.strip() for rule in fee_rules if rule.strip()][:2]
    if not selected:
        return None
    return "; ".join(selected)


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
