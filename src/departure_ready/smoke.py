from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from departure_ready.api.app import create_app
from departure_ready.services.guide import build_coverage_envelope, build_guide_envelope
from departure_ready.services.parking import build_parking_envelope
from departure_ready.services.readiness import build_readiness_envelope
from departure_ready.settings import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"


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
    ]
    return _report_from_checks(checks)


def build_hosted_canary_report(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or Settings()
    http_url = settings.resolved_public_http_url
    mcp_url = settings.resolved_public_mcp_url
    checks: list[dict[str, object]] = []
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
        checks.append(_hosted_http_canary(http_url))
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
        checks.append(_hosted_mcp_canary(mcp_url))
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
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as client:
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["smoke", "launch", "hosted"], default="launch")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    settings = Settings()
    if args.mode == "smoke":
        report = build_smoke_report(settings)
    elif args.mode == "hosted":
        report = build_hosted_canary_report(settings)
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
    if settings.iiac_service_key:
        envelope = build_parking_envelope("ICN", settings=settings)
        checks.append(
            _check(
                name="iiac_canary",
                ok=envelope.ok,
                detail="IIAC canary executed." if envelope.ok else envelope.data.message,
                status="ok" if envelope.ok else "fail",
                airport_code="ICN",
                coverage_note=envelope.meta.coverage_note,
            )
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
        envelope = build_parking_envelope("GMP", settings=settings)
        checks.append(
            _check(
                name="kac_canary",
                ok=envelope.ok,
                detail="KAC canary executed." if envelope.ok else envelope.data.message,
                status="ok" if envelope.ok else "fail",
                airport_code="GMP",
                coverage_note=envelope.meta.coverage_note,
            )
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


def _hosted_http_canary(base_url: str) -> dict[str, object]:
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            health = client.get(f"{base_url}/healthz")
            coverage = client.get(f"{base_url}/v1/coverage")
            future_flight = client.get(
                f"{base_url}/v1/flight-status",
                params={"airport_code": "ICN", "travel_date": tomorrow},
            )
        ok = (
            health.status_code == 200
            and coverage.status_code == 200
            and future_flight.status_code == 200
        )
        detail = "Hosted HTTP canary completed."
        if ok:
            payload = future_flight.json()
            detail = payload.get("meta", {}).get("coverage_note", detail)
        return _check(
            name="hosted_http_canary",
            ok=ok,
            detail=detail,
            base_url=base_url,
            travel_date=tomorrow,
            health_status=health.status_code,
            coverage_status=coverage.status_code,
            future_flight_status=future_flight.status_code,
        )
    except httpx.HTTPError as exc:
        return _check(
            name="hosted_http_canary",
            ok=False,
            detail=f"Hosted HTTP canary failed: {exc}",
            base_url=base_url,
        )


def _hosted_mcp_canary(mcp_url: str) -> dict[str, object]:
    headers = {"accept": "application/json, text/event-stream"}
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(mcp_url, headers=headers)
        ok = response.status_code in {400, 406}
        return _check(
            name="hosted_mcp_canary",
            ok=ok,
            detail="Hosted remote MCP endpoint responded.",
            mcp_url=mcp_url,
            status_code=response.status_code,
        )
    except httpx.HTTPError as exc:
        return _check(
            name="hosted_mcp_canary",
            ok=False,
            detail=f"Hosted MCP canary failed: {exc}",
            mcp_url=mcp_url,
        )


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


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{SRC_ROOT}{os.pathsep}{existing}" if existing else str(SRC_ROOT)
    return env


if __name__ == "__main__":
    main()
