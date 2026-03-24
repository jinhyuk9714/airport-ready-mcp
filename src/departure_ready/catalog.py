from __future__ import annotations

from datetime import UTC, datetime

from departure_ready.contracts import (
    AirportCode,
    Freshness,
    ResponseMeta,
    SourceKind,
    SourceRef,
)

SUPPORT_MATRIX: dict[str, dict[str, object]] = {
    AirportCode.ICN.value: {
        "name_ko": "인천국제공항",
        "coverage": "strong",
        "domains": [
            "flight_status",
            "parking",
            "parking_fee",
            "crowd_forecast",
            "baggage",
            "customs",
            "self_service",
            "priority_lane",
            "facilities",
            "shops",
        ],
    },
    AirportCode.GMP.value: {
        "name_ko": "김포국제공항",
        "coverage": "strong",
        "domains": [
            "flight_status",
            "parking",
            "processing_time",
            "baggage",
            "customs",
            "facilities",
        ],
    },
    AirportCode.CJU.value: {
        "name_ko": "제주국제공항",
        "coverage": "strong",
        "domains": [
            "flight_status",
            "parking",
            "processing_time",
            "baggage",
            "customs",
            "facilities",
        ],
    },
    AirportCode.PUS.value: {
        "name_ko": "김해국제공항",
        "coverage": "selected",
        "domains": [
            "flight_status",
            "parking",
            "crowd_info",
            "baggage",
            "customs",
            "facilities",
        ],
    },
    AirportCode.CJJ.value: {
        "name_ko": "청주국제공항",
        "coverage": "selected",
        "domains": [
            "flight_status",
            "parking",
            "crowd_info",
            "baggage",
            "customs",
            "facilities",
        ],
    },
    AirportCode.TAE.value: {
        "name_ko": "대구국제공항",
        "coverage": "selected",
        "domains": [
            "flight_status",
            "parking",
            "crowd_info",
            "baggage",
            "customs",
            "facilities",
        ],
    },
}

AIRPORT_ALIASES = {
    "인천": AirportCode.ICN.value,
    "인천공항": AirportCode.ICN.value,
    "인천국제공항": AirportCode.ICN.value,
    "김포": AirportCode.GMP.value,
    "김포공항": AirportCode.GMP.value,
    "김포국제공항": AirportCode.GMP.value,
    "제주": AirportCode.CJU.value,
    "제주공항": AirportCode.CJU.value,
    "제주국제공항": AirportCode.CJU.value,
    "김해": AirportCode.PUS.value,
    "김해공항": AirportCode.PUS.value,
    "김해국제공항": AirportCode.PUS.value,
    "부산": AirportCode.PUS.value,
    "청주": AirportCode.CJJ.value,
    "청주공항": AirportCode.CJJ.value,
    "청주국제공항": AirportCode.CJJ.value,
    "대구": AirportCode.TAE.value,
    "대구공항": AirportCode.TAE.value,
    "대구국제공항": AirportCode.TAE.value,
    AirportCode.ICN.value: AirportCode.ICN.value,
    AirportCode.GMP.value: AirportCode.GMP.value,
    AirportCode.CJU.value: AirportCode.CJU.value,
    AirportCode.PUS.value: AirportCode.PUS.value,
    AirportCode.CJJ.value: AirportCode.CJJ.value,
    AirportCode.TAE.value: AirportCode.TAE.value,
}

TERMINAL_ALIASES: dict[str, dict[str, str]] = {
    AirportCode.ICN.value: {
        "T1": "T1",
        "T2": "T2",
        "1": "T1",
        "2": "T2",
        "터미널1": "T1",
        "터미널2": "T2",
        "제1터미널": "T1",
        "제2터미널": "T2",
        "제1여객터미널": "T1",
        "제2여객터미널": "T2",
        "TERMINAL1": "T1",
        "TERMINAL2": "T2",
        "TERMINAL 1": "T1",
        "TERMINAL 2": "T2",
    },
    AirportCode.GMP.value: {
        "국내선": "DOMESTIC",
        "국제선": "INTL",
        "DOMESTIC": "DOMESTIC",
        "INTERNATIONAL": "INTL",
    },
    AirportCode.CJU.value: {
        "국내선": "DOMESTIC",
        "국제선": "INTL",
        "DOMESTIC": "DOMESTIC",
        "INTERNATIONAL": "INTL",
    },
}

CATALOG_SOURCE = SourceRef(
    name="repo_catalog",
    kind=SourceKind.INTERNAL,
    url="https://example.invalid/departure-ready/repo_catalog",
)


def normalize_airport_code(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    upper = normalized.upper()
    compact = normalized.replace(" ", "")

    return (
        AIRPORT_ALIASES.get(upper)
        or AIRPORT_ALIASES.get(compact.upper())
        or AIRPORT_ALIASES.get(compact)
        or AIRPORT_ALIASES.get(normalized)
    )


def normalize_terminal_code(airport_code: str | None, terminal: str | None) -> str | None:
    normalized_airport = normalize_airport_code(airport_code)
    if not normalized_airport or not terminal:
        return None

    lookup = terminal.strip()
    if not lookup:
        return None

    aliases = TERMINAL_ALIASES.get(normalized_airport, {})
    compact_upper = lookup.replace(" ", "").upper()
    return aliases.get(lookup.upper()) or aliases.get(compact_upper) or aliases.get(lookup)


def get_supported_domains(airport_code: str | None) -> list[str]:
    normalized_airport = normalize_airport_code(airport_code)
    if not normalized_airport:
        return []
    return list(SUPPORT_MATRIX.get(normalized_airport, {}).get("domains", []))


def is_domain_supported(airport_code: str | None, domain: str) -> bool:
    return domain in get_supported_domains(airport_code)


def unsupported_coverage_note(airport_code: str | None, domain: str) -> str:
    normalized_airport = normalize_airport_code(airport_code) or str(airport_code or "unknown")
    return (
        f"{normalized_airport} does not have official support for {domain}. "
        "Return unsupported coverage instead of guessing."
    )


def internal_meta(note: str) -> ResponseMeta:
    return ResponseMeta(
        source=[CATALOG_SOURCE],
        freshness=Freshness.STATIC,
        updated_at=datetime.now(UTC),
        coverage_note=note,
    )
