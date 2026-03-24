from datetime import UTC, datetime

from departure_ready.contracts import (
    Envelope,
    ErrorData,
    ErrorEnvelope,
    Freshness,
    ResponseMeta,
    SourceKind,
    SourceRef,
    merge_response_meta,
)
from departure_ready.domain.models import BaggageDecision


def test_envelope_serializes():
    envelope = Envelope(
        meta=ResponseMeta(
            source=[SourceRef(name="x", kind=SourceKind.INTERNAL, url="https://example.invalid")],
            freshness=Freshness.STATIC,
            updated_at=datetime.now(UTC),
            coverage_note="test",
        ),
        data={"hello": "world"},
    )
    payload = envelope.model_dump(mode="json")
    assert payload["ok"] is True
    assert payload["meta"]["freshness"] == "static"
    assert payload["data"]["hello"] == "world"


def test_error_envelope_serializes():
    envelope = ErrorEnvelope(
        meta=ResponseMeta(
            source=[SourceRef(name="x", kind=SourceKind.INTERNAL, url="https://example.invalid")],
            freshness=Freshness.STATIC,
            updated_at=datetime.now(UTC),
            coverage_note="test",
        ),
        data=ErrorData(code="unsupported", message="unsupported", hint="use ICN"),
    )

    payload = envelope.model_dump(mode="json")

    assert payload["ok"] is False
    assert payload["data"]["code"] == "unsupported"
    assert payload["data"]["hint"] == "use ICN"


def test_merge_response_meta_uses_latest_update_and_keeps_source_order():
    earlier = datetime(2026, 3, 24, 9, 0, tzinfo=UTC)
    later = datetime(2026, 3, 24, 10, 0, tzinfo=UTC)

    first = BaggageDecision(
        item_query="lotion",
        trip_type="international",
        category="manual_confirmation",
        explanation="Confirm liquid volume.",
        source=[
            SourceRef(name="iiac_baggage_policy", kind=SourceKind.OFFICIAL_WEB, url="https://a")
        ],
        freshness=Freshness.POLICY,
        updated_at=earlier,
        coverage_note="Policy guidance",
    )
    second = BaggageDecision(
        item_query="perfume",
        trip_type="international",
        category="allowed_with_limit",
        explanation="Allowed within duty-free limit.",
        source=[
            SourceRef(name="customs_traveler_rules", kind=SourceKind.OFFICIAL_WEB, url="https://b")
        ],
        freshness=Freshness.POLICY,
        updated_at=later,
        coverage_note="Customs guidance",
    )

    meta = merge_response_meta(
        [first, second],
        default_note="default",
    )

    assert meta.updated_at == later
    assert [item.name for item in meta.source] == [
        "iiac_baggage_policy",
        "customs_traveler_rules",
    ]
    assert meta.coverage_note == "Policy guidance | Customs guidance"
