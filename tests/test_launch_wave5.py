from __future__ import annotations

from types import SimpleNamespace

from departure_ready import smoke
from departure_ready.contracts import Freshness
from departure_ready.settings import Settings


def _meta(*, coverage_note: str, freshness: Freshness) -> SimpleNamespace:
    return SimpleNamespace(
        source=[{"name": "fake_source", "kind": "internal", "url": "https://example.invalid"}],
        freshness=freshness,
        updated_at="2026-03-24T20:00:00+09:00",
        coverage_note=coverage_note,
    )


def _parking_envelope(airport_code: str) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        meta=_meta(coverage_note=f"{airport_code} parking ok", freshness=Freshness.LIVE),
        data=SimpleNamespace(
            airport_code=airport_code,
            recommendation=f"{airport_code} parking recommendation",
            lots=[SimpleNamespace(lot_name="A")],
        ),
    )


def _flight_envelope(airport_code: str) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        meta=_meta(coverage_note=f"{airport_code} flight ok", freshness=Freshness.DAILY),
        data=SimpleNamespace(
            airport_code=airport_code,
            status="daily",
            summary=f"{airport_code} flight summary",
            selected_flight=SimpleNamespace(flight_no="KE123"),
        ),
    )


def _readiness_envelope(airport_code: str) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        meta=_meta(coverage_note=f"{airport_code} readiness ok", freshness=Freshness.LIVE),
        data=SimpleNamespace(
            airport_code=airport_code,
            summary=f"{airport_code} readiness summary",
            operational_signals=[SimpleNamespace(signal_type="processing_time")],
        ),
    )


def _facility_envelope(airport_code: str) -> SimpleNamespace:
    return SimpleNamespace(
        ok=True,
        meta=_meta(coverage_note=f"{airport_code} facilities ok", freshness=Freshness.STATIC),
        data=SimpleNamespace(
            airport_code=airport_code,
            matches=[SimpleNamespace(name="Barrier-free elevator", category="accessibility")],
        ),
    )


async def _async_facility_envelope(settings, airport_code: str, **kwargs) -> SimpleNamespace:
    _ = settings, kwargs
    return _facility_envelope(airport_code)


def test_hosted_canary_strict_fails_without_required_ops_config():
    report = smoke.build_hosted_canary_report(Settings(env="test"), strict=True)

    assert report["ok"] is False
    config = report["checks"][0]
    assert config["name"] == "hosted_ops_config"
    assert config["status"] == "fail"
    assert "DEPARTURE_READY_PUBLIC_HTTP_URL" in config["missing"]
    assert "DEPARTURE_READY_KAC_SERVICE_KEY" in config["missing"]
    assert "DEPARTURE_READY_IIAC_SERVICE_KEY" in config["missing"]


def test_hosted_canary_uses_http_url_fallback_for_mcp(monkeypatch):
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(
        smoke,
        "_hosted_http_canary_checks",
        lambda url: [smoke._check(name="hosted_http_stub", ok=True, detail=url)],
    )

    async def fake_mcp_checks(mcp_url: str, *, http_url: str | None = None):
        calls.append((mcp_url, http_url))
        return [smoke._check(name="hosted_mcp_stub", ok=True, detail=mcp_url)]

    monkeypatch.setattr(smoke, "_hosted_mcp_canary_checks", fake_mcp_checks)

    report = smoke.build_hosted_canary_report(
        Settings(
            env="test",
            public_http_url="https://departure-ready.example.com/",
            kac_service_key="kac-key",
            iiac_service_key="iiac-key",
        ),
        strict=True,
    )

    assert report["ok"] is True
    assert calls == [
        (
            "https://departure-ready.example.com/mcp",
            "https://departure-ready.example.com",
        )
    ]


def test_smoke_report_expands_keyed_canary_breadth(monkeypatch):
    monkeypatch.setattr(
        smoke,
        "build_parking_envelope",
        lambda *args, **kwargs: _parking_envelope(args[0]),
    )
    monkeypatch.setattr(
        smoke,
        "build_flight_envelope",
        lambda *args, **kwargs: _flight_envelope(args[0]),
    )
    monkeypatch.setattr(
        smoke,
        "build_readiness_envelope",
        lambda *args, **kwargs: _readiness_envelope(args[0]),
    )
    monkeypatch.setattr(smoke, "build_facilities_envelope", _async_facility_envelope)
    monkeypatch.setattr(smoke, "build_shops_envelope", _async_facility_envelope)

    report = smoke.build_smoke_report(
        Settings(env="test", kac_service_key="kac-key", iiac_service_key="iiac-key")
    )
    names = {check["name"] for check in report["checks"]}

    assert {
        "iiac_parking_canary",
        "iiac_future_flight_canary",
        "iiac_facilities_canary",
        "iiac_shops_canary",
        "kac_parking_canary",
        "kac_readiness_canary",
        "kac_facilities_canary",
    }.issubset(names)
