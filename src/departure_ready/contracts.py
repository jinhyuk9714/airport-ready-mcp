from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Generic, Literal, Protocol, TypeVar

from pydantic import BaseModel


class AirportCode(StrEnum):
    ICN = "ICN"
    GMP = "GMP"
    CJU = "CJU"
    PUS = "PUS"
    CJJ = "CJJ"
    TAE = "TAE"


class Freshness(StrEnum):
    LIVE = "live"
    FORECAST = "forecast"
    DAILY = "daily"
    STATIC = "static"
    POLICY = "policy"


class SourceKind(StrEnum):
    OFFICIAL_API = "official_api"
    OFFICIAL_WEB = "official_web"
    FILE_DATA = "file_data"
    INTERNAL = "internal"


class SourceRef(BaseModel):
    name: str
    kind: SourceKind
    url: str


class ResponseMeta(BaseModel):
    source: list[SourceRef]
    freshness: Freshness
    updated_at: datetime
    coverage_note: str


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    ok: bool = True
    meta: ResponseMeta
    data: T


class ErrorData(BaseModel):
    code: str
    message: str
    hint: str | None = None


class ErrorEnvelope(BaseModel):
    ok: Literal[False] = False
    meta: ResponseMeta
    data: ErrorData


class SupportsTrustFields(Protocol):
    source: list[SourceRef]
    freshness: Freshness
    updated_at: datetime
    coverage_note: str


FRESHNESS_PRIORITY: dict[Freshness, int] = {
    Freshness.LIVE: 5,
    Freshness.FORECAST: 4,
    Freshness.DAILY: 3,
    Freshness.STATIC: 2,
    Freshness.POLICY: 1,
}


def merge_response_meta(
    items: list[SupportsTrustFields],
    default_note: str,
    default_freshness: Freshness = Freshness.STATIC,
    default_source: list[SourceRef] | None = None,
) -> ResponseMeta:
    if not items:
        return ResponseMeta(
            source=default_source or [],
            freshness=default_freshness,
            updated_at=datetime.now(UTC),
            coverage_note=default_note,
        )

    deduped_sources: list[SourceRef] = []
    seen_sources: set[tuple[str, SourceKind, str]] = set()
    coverage_notes: list[str] = []
    freshest = default_freshness
    updated_at = items[0].updated_at

    for item in items:
        if item.updated_at > updated_at:
            updated_at = item.updated_at
        if FRESHNESS_PRIORITY[item.freshness] > FRESHNESS_PRIORITY[freshest]:
            freshest = item.freshness
        note = item.coverage_note.strip()
        if note and note not in coverage_notes:
            coverage_notes.append(note)
        for source in item.source:
            key = (source.name, source.kind, source.url)
            if key in seen_sources:
                continue
            seen_sources.add(key)
            deduped_sources.append(source)

    return ResponseMeta(
        source=deduped_sources or (default_source or []),
        freshness=freshest,
        updated_at=updated_at,
        coverage_note=" | ".join(coverage_notes) if coverage_notes else default_note,
    )
