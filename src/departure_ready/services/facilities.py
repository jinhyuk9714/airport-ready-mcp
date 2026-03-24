from __future__ import annotations

from departure_ready.catalog import is_domain_supported, normalize_airport_code
from departure_ready.connectors.base import ConnectorContext, ConnectorUnavailableError
from departure_ready.connectors.iiac_facilities import (
    IIAC_FACILITIES_DOC_URL,
    IIAC_SHOPS_DOC_URL,
    IiacFacilityConnector,
)
from departure_ready.connectors.kac_facilities import (
    KAC_ACCESSIBILITY_DOC_URL,
    KAC_FACILITY_DOC_URL,
)
from departure_ready.connectors.kac_facilities import (
    KacFacilitiesConnector as KacFacilityConnector,
)
from departure_ready.contracts import Envelope, Freshness, SourceKind, SourceRef
from departure_ready.domain.models import FacilityPayload
from departure_ready.services.common import envelope_from_items, unsupported_domain_envelope
from departure_ready.settings import Settings


def _empty_payload(airport_code: str, terminal: str | None = None) -> FacilityPayload:
    return FacilityPayload(airport_code=airport_code, terminal=terminal, matches=[])


async def build_facilities_envelope(
    settings: Settings,
    airport_code: str,
    *,
    terminal: str | None = None,
    category: str | None = None,
    query: str | None = None,
) -> Envelope[FacilityPayload]:
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
    if not is_domain_supported(normalized_airport, "facilities"):
        return unsupported_domain_envelope(normalized_airport, "facilities")

    try:
        if normalized_airport == "ICN":
            connector = IiacFacilityConnector(
                ConnectorContext(
                    timeout_sec=settings.http_timeout_sec,
                    default_headers={},
                    max_retries=settings.http_max_retries,
                ),
                settings.iiac_service_key,
            )
            matches = await connector.find_facilities(query=query, category=category)
        else:
            connector = KacFacilityConnector(
                ConnectorContext(
                    timeout_sec=settings.http_timeout_sec,
                    default_headers={},
                    max_retries=settings.http_max_retries,
                ),
                settings.kac_service_key,
            )
            matches = await connector.find_facilities(
                normalized_airport,
                query=query,
                category=category,
            )
    except ConnectorUnavailableError:
        matches = []

    payload = _empty_payload(normalized_airport, terminal)
    payload.matches = [match for match in matches if terminal is None or match.terminal == terminal]

    if payload.matches:
        return envelope_from_items(
            payload,
            payload.matches,
            default_note=f"{normalized_airport} facility lookup",
            default_freshness=Freshness.DAILY if normalized_airport == "ICN" else Freshness.STATIC,
        )

    # Bounded unavailable state: airport supports the domain, but live/daily data is absent.
    fallback_model = FacilityPayload(
        airport_code=normalized_airport,
        terminal=terminal,
        matches=[],
    )
    return envelope_from_items(
        fallback_model,
        [],
        default_note=(
            f"{normalized_airport} facility data is currently unavailable or empty. "
            "No unofficial fallback was used."
        ),
        default_source=(
            [
                SourceRef(
                    name="iiac_facilities",
                    kind=SourceKind.OFFICIAL_API,
                    url=IIAC_FACILITIES_DOC_URL,
                )
            ]
            if normalized_airport == "ICN"
            else [
                SourceRef(
                    name="kac_facility_file",
                    kind=SourceKind.FILE_DATA,
                    url=KAC_FACILITY_DOC_URL,
                ),
                SourceRef(
                    name="kac_accessibility_file",
                    kind=SourceKind.FILE_DATA,
                    url=KAC_ACCESSIBILITY_DOC_URL,
                ),
            ]
        ),
        default_freshness=Freshness.DAILY if normalized_airport == "ICN" else Freshness.STATIC,
    )


async def build_shops_envelope(
    settings: Settings,
    airport_code: str,
    *,
    terminal: str | None = None,
    category: str | None = None,
    query: str | None = None,
) -> Envelope[FacilityPayload]:
    normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
    if not is_domain_supported(normalized_airport, "shops"):
        return unsupported_domain_envelope(normalized_airport, "shops")

    connector = IiacFacilityConnector(
        ConnectorContext(
            timeout_sec=settings.http_timeout_sec,
            default_headers={},
            max_retries=settings.http_max_retries,
        ),
        settings.iiac_service_key,
    )

    try:
        matches = await connector.find_shops(query=query, category=category)
    except ConnectorUnavailableError:
        matches = []

    payload = _empty_payload(normalized_airport, terminal)
    payload.matches = [match for match in matches if terminal is None or match.terminal == terminal]

    return envelope_from_items(
        payload,
        payload.matches,
        default_note=(
            f"{normalized_airport} shop data is currently unavailable or empty. "
            "No unofficial fallback was used."
        ),
        default_source=[
            SourceRef(
                name="iiac_shops",
                kind=SourceKind.OFFICIAL_API,
                url=IIAC_SHOPS_DOC_URL,
            )
        ],
        default_freshness=Freshness.DAILY,
    )
