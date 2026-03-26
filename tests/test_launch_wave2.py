from __future__ import annotations

import subprocess

from departure_ready import smoke


def test_smoke_runner_skips_keyed_canaries_without_env(monkeypatch):
    monkeypatch.delenv("DEPARTURE_READY_KAC_SERVICE_KEY", raising=False)
    monkeypatch.delenv("DEPARTURE_READY_IIAC_SERVICE_KEY", raising=False)
    monkeypatch.delenv("DEPARTURE_READY_PUBLIC_HTTP_URL", raising=False)
    monkeypatch.delenv("DEPARTURE_READY_PUBLIC_MCP_URL", raising=False)

    report = smoke.build_smoke_report(
        smoke.Settings(
            env="test",
            kac_service_key=None,
            iiac_service_key=None,
            public_http_url=None,
            public_mcp_url=None,
        )
    )

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
    report = smoke.check_api_boot()

    assert report["ok"] is True
    assert "/healthz" in report["routes"]
    assert "/mcp" in report["routes"]


def test_mcp_stdio_boot_smoke_has_no_stdout_pollution(monkeypatch):
    class FakeProcess:
        returncode = -15

        def wait(self, timeout):
            raise subprocess.TimeoutExpired(cmd=["departure-ready-mcp"], timeout=timeout)

        def terminate(self):
            self.returncode = -15

        def communicate(self, timeout=None):
            _ = timeout
            return "", ""

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(smoke.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    report = smoke.check_mcp_stdio_boot(timeout_sec=0.5)

    assert report["started"] is True
    assert report["stdout"] == ""
    assert report["timed_out"] is True
