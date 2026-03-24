from __future__ import annotations

from datetime import UTC, datetime

from departure_ready.contracts import Envelope, Freshness, ResponseMeta, SourceKind, SourceRef
from departure_ready.domain.models import FlightSnapshot, OperationalSignal
from departure_ready.services import readiness as readiness_module
from departure_ready.services.flight import FlightPayload
from departure_ready.services.readiness import build_readiness_envelope
from departure_ready.settings import Settings


def _flight_envelope(airport_code: str) -> Envelope[FlightPayload]:
    flight = FlightSnapshot(
        airport_code=airport_code,
        flight_no="KE123",
        airline="Korean Air",
        terminal="T1",
        gate="12",
        checkin_counter="A1",
        scheduled_at=datetime(2026, 3, 24, 11, 0, tzinfo=UTC),
        changed_at=datetime(2026, 3, 24, 11, 30, tzinfo=UTC),
        status_label="ON TIME",
        signal_kind="live",
        freshness=Freshness.LIVE,
        updated_at=datetime(2026, 3, 24, 10, 5, tzinfo=UTC),
        source=[
            SourceRef(
                name="fake_flight",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} flight",
    )
    payload = FlightPayload(
        airport_code=airport_code,
        status="live",
        summary=f"{airport_code} live flight status is available from the official source.",
        live_flights=[flight],
        forecast_signals=[],
        selected_flight=flight,
        missing_inputs=[],
    )
    return Envelope(
        meta=ResponseMeta(
            source=flight.source,
            freshness=Freshness.LIVE,
            updated_at=flight.updated_at,
            coverage_note=flight.coverage_note,
        ),
        data=payload,
    )


def _operational_signal(
    airport_code: str,
    signal_type: str,
    headline: str,
    detail: str,
) -> OperationalSignal:
    return OperationalSignal(
        airport_code=airport_code,
        signal_type=signal_type,
        headline=headline,
        detail=detail,
        freshness=Freshness.LIVE,
        updated_at=datetime(2026, 3, 24, 10, 15, tzinfo=UTC),
        source=[
            SourceRef(
                name=f"fake_{signal_type}",
                kind=SourceKind.INTERNAL,
                url="https://example.invalid",
            )
        ],
        coverage_note=f"{airport_code} {signal_type}",
    )


def _load_gmp_processing_signals(*args, **kwargs):
    return (
        [
            _operational_signal(
                "GMP",
                "processing_time",
                "Estimated processing time 22 minutes",
                "check-in 5m, id/security 9m, boarding 8m, departure 22m; total 22m.",
            )
        ],
        [],
    )


def _load_pus_crowd_signals(*args, **kwargs):
    return (
        [
            _operational_signal(
                "PUS",
                "crowd_info",
                "Crowd level B",
                "A B, B C, C D, overall B.",
            )
        ],
        [],
    )


def _load_cju_unavailable_signals(*args, **kwargs):
    return ([], ["Official KAC processing signal unavailable for CJU."])


def test_readiness_includes_processing_signal_for_gmp(monkeypatch):
    monkeypatch.setattr(
        readiness_module,
        "build_flight_envelope",
        lambda *args, **kwargs: _flight_envelope("GMP"),
    )
    monkeypatch.setattr(
        readiness_module,
        "_load_kac_operational_signals",
        _load_gmp_processing_signals,
    )

    envelope = build_readiness_envelope(
        "GMP",
        settings=Settings(kac_service_key="fake"),
    )

    card = envelope.data
    assert envelope.ok is True
    assert len(card.operational_signals) == 1
    assert card.operational_signals[0].signal_type == "processing_time"
    assert "processing" in card.summary.lower()
    assert any("processing" in action.lower() for action in card.next_actions)
    assert "operational_signals" in envelope.model_dump(mode="json")["data"]


def test_readiness_includes_crowd_signal_for_pus(monkeypatch):
    monkeypatch.setattr(
        readiness_module,
        "build_flight_envelope",
        lambda *args, **kwargs: _flight_envelope("PUS"),
    )
    monkeypatch.setattr(
        readiness_module,
        "_load_kac_operational_signals",
        _load_pus_crowd_signals,
    )

    envelope = build_readiness_envelope(
        "PUS",
        settings=Settings(kac_service_key="fake"),
    )

    card = envelope.data
    assert envelope.ok is True
    assert len(card.operational_signals) == 1
    assert card.operational_signals[0].signal_type == "crowd_info"
    assert "crowd" in card.summary.lower()
    assert any("crowd" in action.lower() for action in card.next_actions)


def test_readiness_marks_kac_signal_unavailable_without_guessing(monkeypatch):
    monkeypatch.setattr(
        readiness_module,
        "build_flight_envelope",
        lambda *args, **kwargs: _flight_envelope("CJU"),
    )
    monkeypatch.setattr(
        readiness_module,
        "_load_kac_operational_signals",
        _load_cju_unavailable_signals,
    )

    envelope = build_readiness_envelope(
        "CJU",
        settings=Settings(kac_service_key="fake"),
    )

    card = envelope.data
    assert envelope.ok is True
    assert card.operational_signals == []
    assert card.next_actions[-1] == "Official KAC processing signal unavailable for CJU."
    assert "unavailable" in envelope.meta.coverage_note.lower()
