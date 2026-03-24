from __future__ import annotations

from datetime import datetime

from departure_ready.catalog import normalize_airport_code, normalize_terminal_code
from departure_ready.connectors.base import (
    ConnectorContext,
    OfficialConnector,
    extract_items,
)
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import FacilityMatch

KAC_FACILITY_DOC_URL = "https://www.data.go.kr/dataset/15002685/fileData.do"
KAC_ACCESSIBILITY_DOC_URL = "https://www.data.go.kr/en/data/15105780/fileData.do"


class KacFacilitiesConnector(OfficialConnector):
    source_name = "kac_facility_file"
    source_url = KAC_FACILITY_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None = None) -> None:
        super().__init__(context, service_key=service_key)

    async def get_facility_file(self, airport_code: str | None = None) -> list[FacilityMatch]:
        payload = await self.get_payload(KAC_FACILITY_DOC_URL)
        matches = self.parse_facility_payload(payload, airport_code=airport_code)
        return _dedupe_matches(matches)

    async def get_accessibility_file(
        self,
        airport_code: str | None = None,
    ) -> list[FacilityMatch]:
        payload = await self.get_payload(KAC_ACCESSIBILITY_DOC_URL)
        matches = self.parse_accessibility_payload(payload, airport_code=airport_code)
        return _dedupe_matches(matches)

    async def get_facility_matches(self, airport_code: str | None = None) -> list[FacilityMatch]:
        facility_matches = await self.get_facility_file(airport_code)
        accessibility_matches = await self.get_accessibility_file(airport_code)
        return _dedupe_matches([*facility_matches, *accessibility_matches])

    async def find_facilities(
        self,
        airport_code: str,
        *,
        query: str | None = None,
        category: str | None = None,
    ) -> list[FacilityMatch]:
        matches = await self.get_facility_matches(airport_code)
        normalized_category = _normalize_category_query(category)
        normalized_query = query.strip().lower() if query and query.strip() else None
        filtered: list[FacilityMatch] = []
        for match in matches:
            if normalized_category and match.category != normalized_category:
                continue
            if normalized_query and normalized_query not in _match_search_text(match):
                continue
            filtered.append(match)
        return filtered

    def parse_facility_payload(
        self,
        payload: dict,
        airport_code: str | None = None,
    ) -> list[FacilityMatch]:
        return [
            match
            for row in extract_items(payload)
            if (match := _build_facility_match(row, airport_code=airport_code, accessibility=False))
        ]

    def parse_accessibility_payload(
        self,
        payload: dict,
        airport_code: str | None = None,
    ) -> list[FacilityMatch]:
        return [
            match
            for row in extract_items(payload)
            if (match := _build_facility_match(row, airport_code=airport_code, accessibility=True))
        ]


def _build_facility_match(
    row: dict[str, object],
    *,
    airport_code: str | None,
    accessibility: bool,
) -> FacilityMatch | None:
    resolved_airport = _resolve_airport_code(row, airport_code)
    if resolved_airport is None:
        return None

    name = _first_str(
        row,
        "name",
        "facilitynm",
        "facility_name",
        "item_name",
        "title",
        "entrpskoreannm",
    )
    if not name:
        return None

    terminal = _resolve_terminal(row, resolved_airport)
    location_text = _first_str(
        row,
        "location_text",
        "location",
        "lcnm",
        "addr",
        "address",
        "detail",
        "description",
    ) or ""
    category = "accessibility" if accessibility else _normalize_category(row)

    return FacilityMatch(
        airport_code=resolved_airport,
        terminal=terminal,
        name=name,
        category=category,
        location_text=location_text,
        inout=_normalize_inout(_first_str(row, "inout", "arrordep", "direction")),
        floor=_first_str(row, "floor", "floorinfo", "floor_nm"),
        operating_hours=_first_str(row, "operating_hours", "servicetime", "hours"),
        phone=_first_str(row, "phone", "tel", "contact"),
        freshness=Freshness.STATIC,
        updated_at=datetime.now().astimezone(),
        source=[
            SourceRef(
                name="kac_accessibility_file" if accessibility else "kac_facility_file",
                kind=SourceKind.FILE_DATA,
                url=KAC_ACCESSIBILITY_DOC_URL if accessibility else KAC_FACILITY_DOC_URL,
            )
        ],
        coverage_note=(
            "KAC accessibility facility information"
            if accessibility
            else "KAC airport facility information"
        ),
    )


def _resolve_airport_code(row: dict[str, object], airport_code: str | None) -> str | None:
    for key in ("airport_code", "airportcode", "airport", "airport_name", "aprkor", "apkor"):
        value = _first_str(row, key)
        if value:
            normalized = normalize_airport_code(value)
            if normalized:
                return normalized
    if airport_code:
        return normalize_airport_code(airport_code) or airport_code.upper()
    return None


def _resolve_terminal(row: dict[str, object], airport_code: str) -> str | None:
    for key in ("terminal", "terminal_nm", "terminal_name", "terminalid", "terminal_id"):
        value = _first_str(row, key)
        if not value:
            continue
        normalized = normalize_terminal_code(airport_code, value)
        if normalized:
            return normalized
        return value.strip() or None
    return None


def _normalize_category(row: dict[str, object]) -> str:
    raw = _first_str(
        row,
        "category",
        "facility_category",
        "facilitycategory",
        "lcategorynm",
        "mcategorynm",
        "scategorynm",
        "type",
    )
    if not raw:
        return "facility"

    lowered = raw.strip().lower()
    if lowered in {"accessibility", "wheelchair", "disabled", "barrier-free"}:
        return "accessibility"
    return lowered


def _normalize_category_query(category: str | None) -> str | None:
    if category is None:
        return None
    lowered = category.strip().lower()
    if not lowered:
        return None
    if lowered in {"accessibility", "wheelchair", "disabled", "barrier-free"}:
        return "accessibility"
    return lowered


def _normalize_inout(value: str | None) -> str | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if not lowered:
        return None
    if lowered in {"d", "departure", "출발"}:
        return "departure"
    if lowered in {"a", "arrival", "도착"}:
        return "arrival"
    return lowered


def _dedupe_matches(matches: list[FacilityMatch]) -> list[FacilityMatch]:
    deduped: list[FacilityMatch] = []
    seen: set[tuple[str, str | None, str, str, str]] = set()
    for match in matches:
        key = (
            match.airport_code,
            match.terminal,
            match.name,
            match.location_text,
            match.category,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)
    return deduped


def _match_search_text(match: FacilityMatch) -> str:
    return " ".join(
        [
            match.name.lower(),
            match.category.lower(),
            match.location_text.lower(),
            (match.floor or "").lower(),
        ]
    )


def _first_str(row: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
