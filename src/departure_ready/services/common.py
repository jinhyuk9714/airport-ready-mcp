from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar

from departure_ready.catalog import CATALOG_SOURCE, unsupported_coverage_note
from departure_ready.contracts import (
    Envelope,
    ErrorData,
    ErrorEnvelope,
    Freshness,
    ResponseMeta,
    SourceRef,
    merge_response_meta,
)
from departure_ready.domain.models import TrustStampedModel

T = TypeVar("T")


def envelope_from_model(data: T, model: TrustStampedModel) -> Envelope[T]:
    return Envelope(
        meta=ResponseMeta(
            source=model.source,
            freshness=model.freshness,
            updated_at=model.updated_at,
            coverage_note=model.coverage_note,
        ),
        data=data,
    )


def envelope_from_items(
    data: T,
    items: Sequence[TrustStampedModel],
    default_note: str,
    default_source: list[SourceRef] | None = None,
    default_freshness: Freshness = Freshness.STATIC,
) -> Envelope[T]:
    meta = merge_response_meta(
        list(items),
        default_note=default_note,
        default_source=default_source or [CATALOG_SOURCE],
        default_freshness=default_freshness,
    )
    return Envelope(meta=meta, data=data)


def error_envelope(
    code: str,
    message: str,
    coverage_note: str,
    *,
    hint: str | None = None,
    source: list[SourceRef] | None = None,
    freshness: Freshness = Freshness.STATIC,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        meta=ResponseMeta(
            source=source or [CATALOG_SOURCE],
            freshness=freshness,
            updated_at=datetime.now(UTC),
            coverage_note=coverage_note,
        ),
        data=ErrorData(code=code, message=message, hint=hint),
    )


def unsupported_domain_envelope(airport_code: str, domain: str) -> ErrorEnvelope:
    return error_envelope(
        code="unsupported_coverage",
        message=f"{airport_code.upper()} does not support {domain}.",
        coverage_note=unsupported_coverage_note(airport_code, domain),
        hint="Use /v1/coverage to inspect official airport/domain support.",
    )
