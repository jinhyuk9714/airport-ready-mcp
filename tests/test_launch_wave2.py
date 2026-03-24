from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from departure_ready import smoke

ROOT = Path(__file__).resolve().parents[1]


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}" if existing else src_path
    return env


def test_smoke_runner_skips_keyed_canaries_without_env(monkeypatch):
    monkeypatch.delenv("DEPARTURE_READY_KAC_SERVICE_KEY", raising=False)
    monkeypatch.delenv("DEPARTURE_READY_IIAC_SERVICE_KEY", raising=False)

    report = smoke.build_smoke_report()

    assert report["ok"] is True
    assert any(
        check["name"] == "readiness_icn_no_keys" and check["status"] == "ok"
        for check in report["checks"]
    )
    assert any(
        check["name"] == "readiness_gmp_no_keys" and check["status"] == "ok"
        for check in report["checks"]
    )
    assert any(
        check["name"] == "parking_gmp_no_keys" and check["status"] == "ok"
        for check in report["checks"]
    )
    assert any(
        check["name"] == "iiac_canary" and check["status"] == "skipped"
        for check in report["checks"]
    )
    assert any(
        check["name"] == "kac_canary" and check["status"] == "skipped"
        for check in report["checks"]
    )


def test_api_app_boot_smoke_via_subprocess():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from departure_ready.api.app import create_app; "
                "app = create_app(); "
                "assert '/healthz' in {route.path for route in app.routes}; "
                "print('api-ready')"
            ),
        ],
        cwd=ROOT,
        env=_python_env(),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "api-ready" in result.stdout
    assert result.stderr == ""


def test_mcp_stdio_boot_smoke_has_no_stdout_pollution():
    report = smoke.check_mcp_stdio_boot(timeout_sec=0.5)

    assert report["started"] is True
    assert report["stdout"] == ""
    assert report["timed_out"] is True
