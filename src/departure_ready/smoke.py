from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from departure_ready.api.app import create_app
from departure_ready.services.facilities import (
    build_facilities_envelope,
    build_shops_envelope,
)
from departure_ready.services.flight import build_flight_envelope
from departure_ready.services.guide import build_coverage_envelope, build_guide_envelope
from departure_ready.services.parking import build_parking_envelope
from departure_ready.services.readiness import build_readiness_envelope
from departure_ready.settings import Settings, get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
LOCAL_BASE_URL = "http://testserver"
REQUIRED_HOSTED_ENV = (
    "DEPARTURE_READY_PUBLIC_HTTP_URL",
    "DEPARTURE_READY_KAC_SERVICE_KEY",
    "DEPARTURE_READY_IIAC_SERVICE_KEY",
)


def build_smoke_report(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or Settings()
    return _report_from_checks(_smoke_checks(settings))


def build_launch_report(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or Settings()
    checks = [
        *_smoke_checks(settings),
        check_api_boot(),
        check_mcp_stdio_boot(),
        check_remote_mcp_mount(),
        check_remote_mcp_coverage_tool(),
        check_remote_mcp_readiness_parity(settings),
    ]
    return _report_from_checks(checks)


def build_hosted_canary_report(
    settings: Settings | None = None,
    *,
    strict: bool = False,
) -> dict[str, object]:
    settings = settings or Settings()
    checks: list[dict[str, object]] = []

    if strict:
        config_check = _hosted_ops_config_check(settings)
        checks.append(config_check)
        if not config_check["ok"]:
            return _report_from_checks(checks)

    http_url = settings.resolved_public_http_url
    mcp_url = settings.resolved_public_mcp_url

    if not http_url:
        checks.append(
            _check(
                name="hosted_http_canary",
                ok=True,
                status="skipped",
                detail="DEPARTURE_READY_PUBLIC_HTTP_URL is not set.",
            )
        )
    else:
        checks.extend(_hosted_http_canary_checks(http_url))

    if not mcp_url:
        checks.append(
            _check(
                name="hosted_mcp_canary",
                ok=True,
                status="skipped",
                detail=(
                    "DEPARTURE_READY_PUBLIC_MCP_URL is not set and no public HTTP "
                    "URL fallback is available."
                ),
            )
        )
    else:
        checks.extend(asyncio.run(_hosted_mcp_canary_checks(mcp_url, http_url=http_url)))

    return _report_from_checks(checks)


def check_api_boot() -> dict[str, object]:
    app = create_app()
    routes = sorted(route.path for route in app.routes)
    ok = "/healthz" in routes and "/v1/readiness" in routes and "/mcp" in routes
    return _check(
        name="api_boot",
        ok=ok,
        detail="FastAPI app factory constructed successfully.",
        routes=routes,
    )


def check_mcp_stdio_boot(timeout_sec: float = 0.5) -> dict[str, object]:
    command = [
        sys.executable,
        "-c",
        "from departure_ready.mcp.server import main; main()",
    ]
    proc = subprocess.Popen(  # noqa: S603
        command,
        cwd=PROJECT_ROOT,
        env=_python_env(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    timed_out = False
    try:
        proc.wait(timeout=timeout_sec)
        stdout, stderr = proc.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.terminate()
        try:
            stdout, stderr = proc.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
    ok = timed_out and stdout == ""
    return _check(
        name="mcp_stdio_boot",
        ok=ok,
        detail="FastMCP stdio server launched without stdout pollution.",
        started=True,
        timed_out=timed_out,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def check_remote_mcp_mount() -> dict[str, object]:
    with _local_public_http_url():
        with TestClient(create_app(), base_url=LOCAL_BASE_URL) as client:
            response = client.get(
                "/mcp/",
                headers={"accept": "application/json, text/event-stream"},
            )
    ok = response.status_code in {400, 406}
    return _check(
        name="mcp_remote_mount",
        ok=ok,
        detail="Remote MCP mount responded on /mcp.",
        status_code=response.status_code,
    )


def check_remote_mcp_coverage_tool() -> dict[str, object]:
    return asyncio.run(_check_remote_mcp_coverage_tool_async())


def check_remote_mcp_readiness_parity(settings: Settings | None = None) -> dict[str, object]:
    runtime_settings = settings or Settings()
    return asyncio.run(_check_remote_mcp_readiness_parity_async(runtime_settings))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smoke", "launch", "hosted"], default="launch")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--strict-hosted", action="store_true")
    args = parser.parse_args()

    settings = Settings()
    if args.mode == "smoke":
        report = build_smoke_report(settings)
    elif args.mode == "hosted":
        report = build_hosted_canary_report(settings, strict=args.strict_hosted)
    else:
        report = build_launch_report(settings)

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n")
    print(rendered)
    raise SystemExit(0 if report["ok"] else 1)


def _smoke_checks(settings: Settings) -> list[dict[str, object]]:
    return [
        _coverage_check(),
        _guide_check(),
        _readiness_check(
            name="readiness_icn_no_keys",
            airport_code="ICN",
            going_by_car=True,
            settings=settings,
        ),
        _readiness_check(
            name="readiness_gmp_no_keys",
            airport_code="GMP",
            settings=settings,
        ),
        _parking_check(
            name="parking_gmp_no_keys",
            airport_code="GMP",
            settings=settings,
        ),
        *_keyed_canary_checks(settings),
    ]


def _coverage_check() -> dict[str, object]:
    envelope = build_coverage_envelope()
    return _check(
        name="coverage",
        ok=envelope.ok,
        detail="Coverage envelope is available.",
        airports=[item.airport_code for item in envelope.data.airports],
    )


def _guide_check() -> dict[str, object]:
    envelope = build_guide_envelope()
    return _check(
        name="guide",
        ok=envelope.ok,
        detail="Guide envelope is available.",
        promises=envelope.data.promises,
    )


def _readiness_check(
    *,
    name: str,
    airport_code: str,
    settings: Settings,
    going_by_car: bool = False,
) -> dict[str, object]:
    envelope = build_readiness_envelope(
        airport_code,
        going_by_car=going_by_car,
        settings=settings,
    )
    detail = envelope.data.summary if envelope.ok else envelope.data.message
    return _check(
        name=name,
        ok=envelope.ok,
        detail=detail,
        airport_code=envelope.data.airport_code if envelope.ok else airport_code,
        coverage_note=envelope.meta.coverage_note,
    )


def _parking_check(
    *,
    name: str,
    airport_code: str,
    settings: Settings,
) -> dict[str, object]:
    envelope = build_parking_envelope(airport_code, settings=settings)
    detail = envelope.data.recommendation if envelope.ok else envelope.data.message
    return _check(
        name=name,
        ok=envelope.ok,
        detail=detail,
        airport_code=envelope.data.airport_code if envelope.ok else airport_code,
        coverage_note=envelope.meta.coverage_note,
    )


def _keyed_canary_checks(settings: Settings) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()

    if settings.iiac_service_key:
        checks.extend(
            [
                _safe_canary_check(
                    name="iiac_parking_canary",
                    envelope_factory=lambda: build_parking_envelope("ICN", settings=settings),
                    evaluator=lambda envelope: _parking_contract_check(
                        name="iiac_parking_canary",
                        envelope=envelope,
                        require_lots=True,
                    ),
                ),
                _safe_canary_check(
                    name="iiac_future_flight_canary",
                    envelope_factory=lambda: build_flight_envelope(
                        "ICN", travel_date=tomorrow, settings=settings
                    ),
                    evaluator=lambda envelope: _flight_contract_check(
                        name="iiac_future_flight_canary",
                        envelope=envelope,
                        disallow_unavailable=True,
                    ),
                ),
                _safe_canary_check(
                    name="iiac_facilities_canary",
                    envelope_factory=lambda: asyncio.run(
                        build_facilities_envelope(settings, "ICN")
                    ),
                    evaluator=lambda envelope: _facility_contract_check(
                        name="iiac_facilities_canary",
                        envelope=envelope,
                        require_matches=True,
                    ),
                ),
                _safe_canary_check(
                    name="iiac_shops_canary",
                    envelope_factory=lambda: asyncio.run(build_shops_envelope(settings, "ICN")),
                    evaluator=lambda envelope: _facility_contract_check(
                        name="iiac_shops_canary",
                        envelope=envelope,
                        require_matches=True,
                    ),
                ),
            ]
        )
    else:
        checks.append(
            _check(
                name="iiac_canary",
                ok=True,
                status="skipped",
                detail="DEPARTURE_READY_IIAC_SERVICE_KEY is not set.",
            )
        )

    if settings.kac_service_key:
        checks.extend(
            [
                _safe_canary_check(
                    name="kac_parking_canary",
                    envelope_factory=lambda: build_parking_envelope("GMP", settings=settings),
                    evaluator=lambda envelope: _parking_contract_check(
                        name="kac_parking_canary",
                        envelope=envelope,
                        require_lots=True,
                    ),
                ),
                _safe_canary_check(
                    name="kac_readiness_canary",
                    envelope_factory=lambda: build_readiness_envelope("GMP", settings=settings),
                    evaluator=lambda envelope: _readiness_contract_check(
                        name="kac_readiness_canary",
                        envelope=envelope,
                        require_operational_signals=True,
                    ),
                ),
                _safe_canary_check(
                    name="kac_facilities_canary",
                    envelope_factory=lambda: asyncio.run(
                        build_facilities_envelope(
                            settings,
                            "PUS",
                            category="wheelchair",
                        )
                    ),
                    evaluator=lambda envelope: _facility_contract_check(
                        name="kac_facilities_canary",
                        envelope=envelope,
                        require_matches=True,
                    ),
                ),
            ]
        )
    else:
        checks.append(
            _check(
                name="kac_canary",
                ok=True,
                status="skipped",
                detail="DEPARTURE_READY_KAC_SERVICE_KEY is not set.",
            )
        )

    return checks


def _safe_canary_check(
    *,
    name: str,
    envelope_factory: Callable[[], Any],
    evaluator: Callable[[Any], dict[str, object]],
) -> dict[str, object]:
    try:
        envelope = envelope_factory()
    except Exception as exc:  # noqa: BLE001
        return _check(
            name=name,
            ok=False,
            detail=f"Official source check failed: {exc}",
        )
    return evaluator(envelope)


def _hosted_ops_config_check(settings: Settings) -> dict[str, object]:
    missing = [
        key
        for key, value in (
            ("DEPARTURE_READY_PUBLIC_HTTP_URL", settings.resolved_public_http_url),
            ("DEPARTURE_READY_KAC_SERVICE_KEY", settings.kac_service_key),
            ("DEPARTURE_READY_IIAC_SERVICE_KEY", settings.iiac_service_key),
        )
        if not value
    ]
    return _check(
        name="hosted_ops_config",
        ok=not missing,
        detail=(
            "Hosted canary has the required ops configuration."
            if not missing
            else f"Missing required hosted canary config: {', '.join(missing)}"
        ),
        required_env=list(REQUIRED_HOSTED_ENV),
        resolved_public_http_url=settings.resolved_public_http_url,
        resolved_public_mcp_url=settings.resolved_public_mcp_url,
        missing=missing,
    )


def _hosted_http_canary_checks(base_url: str) -> list[dict[str, object]]:
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    return [
        _hosted_health_check(base_url),
        _hosted_json_envelope_check(
            name="hosted_coverage_canary",
            base_url=base_url,
            path="/v1/coverage",
        ),
        _hosted_json_envelope_check(
            name="hosted_guide_canary",
            base_url=base_url,
            path="/v1/guide",
        ),
        _hosted_json_envelope_check(
            name="hosted_icn_parking_canary",
            base_url=base_url,
            path="/v1/parking",
            params={"airport_code": "ICN"},
            disallow_unavailable=True,
            require_count_field=("data.lots", 1),
        ),
        _hosted_json_envelope_check(
            name="hosted_icn_future_flight_canary",
            base_url=base_url,
            path="/v1/flight-status",
            params={"airport_code": "ICN", "travel_date": tomorrow},
            disallow_unavailable=True,
            expected_freshness="daily",
            require_truthy_fields=["data.selected_flight"],
        ),
        _hosted_json_envelope_check(
            name="hosted_gmp_readiness_canary",
            base_url=base_url,
            path="/v1/readiness",
            params={"airport_code": "GMP"},
            disallow_unavailable=True,
            require_count_field=("data.operational_signals", 1),
        ),
        _hosted_json_envelope_check(
            name="hosted_pus_facilities_canary",
            base_url=base_url,
            path="/v1/facilities",
            params={"airport_code": "PUS", "category": "wheelchair"},
            disallow_unavailable=True,
            require_count_field=("data.matches", 1),
        ),
        _hosted_json_envelope_check(
            name="hosted_icn_shops_canary",
            base_url=base_url,
            path="/v1/shops",
            params={"airport_code": "ICN"},
            disallow_unavailable=True,
            require_count_field=("data.matches", 1),
        ),
        _hosted_json_envelope_check(
            name="hosted_baggage_canary",
            base_url=base_url,
            path="/v1/baggage-check",
            params={
                "trip_type": "international",
                "item_query": "lotion",
                "liquid_ml": 120,
            },
            validator=lambda payload: payload["data"]["carry_on_allowed"] is False,
        ),
        _hosted_json_envelope_check(
            name="hosted_customs_canary",
            base_url=base_url,
            path="/v1/customs-rules",
            params={"purchase_value_usd": 900},
            validator=lambda payload: payload["data"]["declaration_required"] is True,
        ),
        _hosted_json_envelope_check(
            name="hosted_self_service_canary",
            base_url=base_url,
            path="/v1/self-service-options",
            params={"airport_code": "ICN"},
            validator=lambda payload: "ICN" == payload["data"]["airport_code"],
        ),
        _hosted_json_envelope_check(
            name="hosted_priority_lane_canary",
            base_url=base_url,
            path="/v1/priority-lane-eligibility",
            params={"airport_code": "ICN", "user_profile": "pregnant traveler"},
            validator=lambda payload: payload["data"]["eligible"] is True,
        ),
    ]


async def _hosted_mcp_canary_checks(
    mcp_url: str,
    *,
    http_url: str | None = None,
) -> list[dict[str, object]]:
    checks = [_hosted_mcp_mount_canary(mcp_url)]

    try:
        coverage = await _call_remote_tool(mcp_url, "tool_get_coverage", {})
        checks.append(
            _check(
                name="hosted_mcp_coverage_tool",
                ok=_meta_contract_present(coverage),
                detail=_detail_from_payload(coverage),
                mcp_url=mcp_url,
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            _check(
                name="hosted_mcp_coverage_tool",
                ok=False,
                detail=f"Hosted remote MCP coverage tool failed: {exc}",
                mcp_url=mcp_url,
            )
        )

    if not http_url:
        return checks

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            remote_readiness = await _call_remote_tool(
                mcp_url,
                "tool_get_departure_readiness",
                {"airport_code": "GMP"},
            )
            http_readiness = (
                await client.get(
                    f"{http_url}/v1/readiness",
                    params={"airport_code": "GMP"},
                )
            ).json()
            ok, detail = _readiness_parity(remote_readiness, http_readiness)
            if _payload_mentions_unavailable(remote_readiness):
                ok = False
            checks.append(
                _check(
                    name="hosted_mcp_readiness_parity",
                    ok=ok,
                    detail=detail,
                    mcp_url=mcp_url,
                    http_url=http_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                _check(
                    name="hosted_mcp_readiness_parity",
                    ok=False,
                    detail=f"Hosted remote MCP readiness parity failed: {exc}",
                    mcp_url=mcp_url,
                    http_url=http_url,
                )
            )

        try:
            remote_facilities = await _call_remote_tool(
                mcp_url,
                "tool_find_facilities",
                {"airport_code": "PUS", "category": "wheelchair"},
            )
            http_facilities = (
                await client.get(
                    f"{http_url}/v1/facilities",
                    params={"airport_code": "PUS", "category": "wheelchair"},
                )
            ).json()
            ok, detail = _facilities_parity(remote_facilities, http_facilities)
            if _payload_mentions_unavailable(remote_facilities):
                ok = False
            if not remote_facilities["data"]["matches"]:
                ok = False
            checks.append(
                _check(
                    name="hosted_mcp_facilities_parity",
                    ok=ok,
                    detail=detail,
                    mcp_url=mcp_url,
                    http_url=http_url,
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                _check(
                    name="hosted_mcp_facilities_parity",
                    ok=False,
                    detail=f"Hosted remote MCP facilities parity failed: {exc}",
                    mcp_url=mcp_url,
                    http_url=http_url,
                )
            )

    return checks


def _hosted_health_check(base_url: str) -> dict[str, object]:
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(f"{base_url}/healthz")
        ok = response.status_code == 200
        detail = (
            "Hosted /healthz responded."
            if ok
            else f"Hosted /healthz failed: {response.status_code}"
        )
        return _check(
            name="hosted_healthz_canary",
            ok=ok,
            detail=detail,
            base_url=base_url,
            status_code=response.status_code,
        )
    except httpx.HTTPError as exc:
        return _check(
            name="hosted_healthz_canary",
            ok=False,
            detail=f"Hosted /healthz failed: {exc}",
            base_url=base_url,
        )


def _hosted_json_envelope_check(
    *,
    name: str,
    base_url: str,
    path: str,
    params: dict[str, Any] | None = None,
    disallow_unavailable: bool = False,
    expected_freshness: str | None = None,
    require_truthy_fields: list[str] | None = None,
    require_count_field: tuple[str, int] | None = None,
    validator: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, object]:
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(f"{base_url}{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return _check(
            name=name,
            ok=False,
            detail=f"{path} canary failed: {exc}",
            base_url=base_url,
            path=path,
            params=params or {},
        )

    ok = payload.get("ok") is True and _meta_contract_present(payload)
    if expected_freshness and payload["meta"]["freshness"] != expected_freshness:
        ok = False
    if disallow_unavailable and _payload_mentions_unavailable(payload):
        ok = False
    for field in require_truthy_fields or []:
        if not _dig(payload, field):
            ok = False
    if require_count_field is not None:
        field, minimum = require_count_field
        value = _dig(payload, field)
        if not isinstance(value, list) or len(value) < minimum:
            ok = False
    if validator and not validator(payload):
        ok = False

    return _check(
        name=name,
        ok=ok,
        detail=_detail_from_payload(payload),
        base_url=base_url,
        path=path,
        params=params or {},
        freshness=payload["meta"]["freshness"],
        coverage_note=payload["meta"]["coverage_note"],
    )


def _hosted_mcp_mount_canary(mcp_url: str) -> dict[str, object]:
    headers = {"accept": "application/json, text/event-stream"}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(mcp_url, headers=headers)
        ok = response.status_code in {400, 406}
        return _check(
            name="hosted_mcp_mount",
            ok=ok,
            detail="Hosted remote MCP endpoint responded.",
            mcp_url=mcp_url,
            status_code=response.status_code,
        )
    except httpx.HTTPError as exc:
        return _check(
            name="hosted_mcp_mount",
            ok=False,
            detail=f"Hosted MCP mount failed: {exc}",
            mcp_url=mcp_url,
        )


def _parking_contract_check(
    *,
    name: str,
    envelope,
    require_lots: bool = False,
) -> dict[str, object]:
    if not envelope.ok:
        return _check(
            name=name,
            ok=False,
            detail=_envelope_message(envelope),
            coverage_note=envelope.meta.coverage_note,
            freshness=_freshness_value(envelope.meta.freshness),
        )
    ok = envelope.ok and bool(envelope.meta.source)
    if _note_mentions_unavailable(envelope.meta.coverage_note):
        ok = False
    if require_lots and not envelope.data.lots:
        ok = False
    return _check(
        name=name,
        ok=ok,
        detail=envelope.data.recommendation if envelope.ok else envelope.data.message,
        airport_code=envelope.data.airport_code if envelope.ok else None,
        coverage_note=envelope.meta.coverage_note,
    )


def _flight_contract_check(
    *,
    name: str,
    envelope,
    disallow_unavailable: bool = False,
) -> dict[str, object]:
    if not envelope.ok:
        return _check(
            name=name,
            ok=False,
            detail=_envelope_message(envelope),
            coverage_note=envelope.meta.coverage_note,
            freshness=_freshness_value(envelope.meta.freshness),
        )
    ok = envelope.ok and bool(envelope.meta.source)
    if disallow_unavailable and envelope.data.status == "unavailable":
        ok = False
    if disallow_unavailable and _note_mentions_unavailable(envelope.meta.coverage_note):
        ok = False
    if disallow_unavailable and envelope.data.selected_flight is None:
        ok = False
    return _check(
        name=name,
        ok=ok,
        detail=envelope.data.summary if envelope.ok else envelope.data.message,
        airport_code=envelope.data.airport_code if envelope.ok else None,
        coverage_note=envelope.meta.coverage_note,
        freshness=envelope.meta.freshness.value,
    )


def _facility_contract_check(
    *,
    name: str,
    envelope,
    require_matches: bool = False,
) -> dict[str, object]:
    if not envelope.ok:
        return _check(
            name=name,
            ok=False,
            detail=_envelope_message(envelope),
            coverage_note=envelope.meta.coverage_note,
            freshness=_freshness_value(envelope.meta.freshness),
            matches=0,
        )
    ok = envelope.ok and bool(envelope.meta.source)
    if _note_mentions_unavailable(envelope.meta.coverage_note):
        ok = False
    if require_matches and not envelope.data.matches:
        ok = False
    return _check(
        name=name,
        ok=ok,
        detail=envelope.meta.coverage_note,
        airport_code=envelope.data.airport_code if envelope.ok else None,
        coverage_note=envelope.meta.coverage_note,
        matches=len(envelope.data.matches) if envelope.ok else 0,
    )


def _readiness_contract_check(
    *,
    name: str,
    envelope,
    require_operational_signals: bool = False,
) -> dict[str, object]:
    if not envelope.ok:
        return _check(
            name=name,
            ok=False,
            detail=_envelope_message(envelope),
            coverage_note=envelope.meta.coverage_note,
            freshness=_freshness_value(envelope.meta.freshness),
            operational_signals=0,
        )
    ok = envelope.ok and bool(envelope.meta.source)
    if require_operational_signals and not envelope.data.operational_signals:
        ok = False
    if require_operational_signals and _note_mentions_unavailable(envelope.meta.coverage_note):
        ok = False
    return _check(
        name=name,
        ok=ok,
        detail=envelope.data.summary if envelope.ok else envelope.data.message,
        airport_code=envelope.data.airport_code if envelope.ok else None,
        coverage_note=envelope.meta.coverage_note,
        operational_signals=len(envelope.data.operational_signals) if envelope.ok else 0,
    )


async def _check_remote_mcp_coverage_tool_async() -> dict[str, object]:
    with _local_public_http_url():
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=LOCAL_BASE_URL) as client:
                tool_names = await _list_remote_tools(f"{LOCAL_BASE_URL}/mcp/", http_client=client)
                remote = await _call_remote_tool(
                    f"{LOCAL_BASE_URL}/mcp/",
                    "tool_get_coverage",
                    {},
                    http_client=client,
                )
                http_payload = (await client.get("/v1/coverage")).json()

    ok = (
        "tool_get_coverage" in tool_names
        and remote["ok"] is True
        and _source_signature(remote) == _source_signature(http_payload)
        and remote["meta"]["freshness"] == http_payload["meta"]["freshness"]
        and remote["meta"]["coverage_note"] == http_payload["meta"]["coverage_note"]
        and bool(remote["meta"]["updated_at"])
        and bool(http_payload["meta"]["updated_at"])
        and remote["data"]["airports"] == http_payload["data"]["airports"]
    )
    return _check(
        name="mcp_remote_coverage_tool",
        ok=ok,
        detail=_detail_from_payload(remote),
        tool_count=len(tool_names),
    )


async def _check_remote_mcp_readiness_parity_async(settings: Settings) -> dict[str, object]:
    _ = settings
    with _local_public_http_url():
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url=LOCAL_BASE_URL) as client:
                remote = await _call_remote_tool(
                    f"{LOCAL_BASE_URL}/mcp/",
                    "tool_get_departure_readiness",
                    {"airport_code": "GMP"},
                    http_client=client,
                )
                response = await client.get(
                    "/v1/readiness",
                    params={"airport_code": "GMP"},
                )
                http_payload = response.json()

    ok, detail = _readiness_parity(remote, http_payload)
    return _check(
        name="mcp_remote_readiness_parity",
        ok=ok,
        detail=detail,
        airport_code=remote["data"]["airport_code"],
    )


async def _list_remote_tools(
    mcp_url: str,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> list[str]:
    async with streamable_http_client(mcp_url, http_client=http_client) as (
        read_stream,
        write_stream,
        _get_session_id,
    ):
        session = ClientSession(read_stream, write_stream)
        async with session:
            tools = await session.initialize()
            _ = tools
            result = await session.list_tools()
    return [tool.name for tool in result.tools]


async def _call_remote_tool(
    mcp_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    async with streamable_http_client(mcp_url, http_client=http_client) as (
        read_stream,
        write_stream,
        _get_session_id,
    ):
        session = ClientSession(read_stream, write_stream)
        async with session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
    return _tool_payload(result)


def _tool_payload(result) -> dict[str, object]:
    if result.isError:
        raise RuntimeError(f"Remote MCP tool returned an error: {result}")
    for item in result.content:
        text = getattr(item, "text", None)
        if text:
            return json.loads(text)
    raise ValueError("Remote MCP tool returned no text payload.")


def _readiness_parity(remote: dict[str, Any], http_payload: dict[str, Any]) -> tuple[bool, str]:
    ok = (
        remote.get("ok") == http_payload.get("ok")
        and _source_signature(remote) == _source_signature(http_payload)
        and remote["meta"]["freshness"] == http_payload["meta"]["freshness"]
        and remote["meta"]["coverage_note"] == http_payload["meta"]["coverage_note"]
        and bool(remote["meta"]["updated_at"])
        and bool(http_payload["meta"]["updated_at"])
        and remote["data"]["airport_code"] == http_payload["data"]["airport_code"]
        and remote["data"]["summary"] == http_payload["data"]["summary"]
        and remote["data"]["operational_signal"] == http_payload["data"]["operational_signal"]
        and isinstance(remote["data"]["next_actions"], list)
        and isinstance(http_payload["data"]["next_actions"], list)
    )
    return ok, _detail_from_payload(remote)


def _facilities_parity(remote: dict[str, Any], http_payload: dict[str, Any]) -> tuple[bool, str]:
    remote_matches = remote["data"]["matches"]
    http_matches = http_payload["data"]["matches"]
    ok = (
        remote.get("ok") == http_payload.get("ok")
        and _source_signature(remote) == _source_signature(http_payload)
        and remote["meta"]["freshness"] == http_payload["meta"]["freshness"]
        and remote["meta"]["coverage_note"] == http_payload["meta"]["coverage_note"]
        and bool(remote["meta"]["updated_at"])
        and bool(http_payload["meta"]["updated_at"])
        and remote["data"]["airport_code"] == http_payload["data"]["airport_code"]
        and isinstance(remote_matches, list)
        and isinstance(http_matches, list)
        and len(remote_matches) == len(http_matches)
    )
    if remote_matches and http_matches:
        ok = ok and remote_matches[0]["name"] == http_matches[0]["name"]
        ok = ok and remote_matches[0]["category"] == http_matches[0]["category"]
    return ok, _detail_from_payload(remote)


def _meta_contract_present(payload: dict[str, Any]) -> bool:
    meta = payload.get("meta", {})
    return bool(meta.get("source")) and bool(meta.get("freshness")) and bool(meta.get("updated_at"))


def _detail_from_payload(payload: dict[str, Any]) -> str:
    meta = payload.get("meta", {})
    data = payload.get("data", {})
    return (
        meta.get("coverage_note")
        or data.get("summary")
        or data.get("recommendation")
        or "MCP payload available."
    )


def _payload_mentions_unavailable(payload: dict[str, Any]) -> bool:
    return _note_mentions_unavailable(payload.get("meta", {}).get("coverage_note"))


def _note_mentions_unavailable(note: str | None) -> bool:
    return "unavailable" in (note or "").lower()


def _source_signature(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    return [
        (
            item.get("name", ""),
            item.get("kind", ""),
            item.get("url", ""),
        )
        for item in payload.get("meta", {}).get("source", [])
    ]


def _dig(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for chunk in path.split("."):
        if isinstance(current, dict):
            current = current.get(chunk)
        else:
            return None
    return current


def _envelope_message(envelope) -> str:
    return getattr(envelope.data, "message", envelope.meta.coverage_note)


def _freshness_value(freshness: Any) -> Any:
    return getattr(freshness, "value", freshness)


def _report_from_checks(checks: list[dict[str, object]]) -> dict[str, object]:
    return {
        "ok": all(check.get("ok", False) or check.get("status") == "skipped" for check in checks),
        "checks": checks,
    }


def _check(
    *,
    name: str,
    ok: bool,
    detail: str,
    status: str | None = None,
    **extra: Any,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "ok": ok,
        "status": status or ("ok" if ok else "fail"),
        "detail": detail,
    }
    payload.update(extra)
    return payload


@contextmanager
def _local_public_http_url(url: str = LOCAL_BASE_URL) -> Iterator[None]:
    previous_http = os.environ.get("DEPARTURE_READY_PUBLIC_HTTP_URL")
    previous_mcp = os.environ.get("DEPARTURE_READY_PUBLIC_MCP_URL")
    os.environ["DEPARTURE_READY_PUBLIC_HTTP_URL"] = url
    os.environ.pop("DEPARTURE_READY_PUBLIC_MCP_URL", None)
    get_settings.cache_clear()
    try:
        yield
    finally:
        if previous_http is None:
            os.environ.pop("DEPARTURE_READY_PUBLIC_HTTP_URL", None)
        else:
            os.environ["DEPARTURE_READY_PUBLIC_HTTP_URL"] = previous_http
        if previous_mcp is None:
            os.environ.pop("DEPARTURE_READY_PUBLIC_MCP_URL", None)
        else:
            os.environ["DEPARTURE_READY_PUBLIC_MCP_URL"] = previous_mcp
        get_settings.cache_clear()


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{SRC_ROOT}{os.pathsep}{existing}" if existing else str(SRC_ROOT)
    return env


if __name__ == "__main__":
    main()
