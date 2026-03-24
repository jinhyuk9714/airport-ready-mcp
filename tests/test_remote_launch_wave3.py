from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from departure_ready import smoke
from departure_ready.api.app import create_app
from departure_ready.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def test_settings_resolve_public_mcp_url_from_http_url():
    derived = Settings(public_http_url="https://departure-ready.onrender.com")
    explicit = Settings(
        public_http_url="https://departure-ready.onrender.com",
        public_mcp_url="https://mcp.example.com/runtime",
    )

    assert derived.resolved_public_mcp_url == "https://departure-ready.onrender.com/mcp"
    assert explicit.resolved_public_mcp_url == "https://mcp.example.com/runtime"


def test_fastapi_app_exposes_docs_and_remote_mcp_mount():
    with TestClient(create_app(), base_url="http://127.0.0.1:8000") as client:
        docs_response = client.get("/docs")
        mcp_response = client.get(
            "/mcp/",
            headers={"accept": "application/json, text/event-stream"},
        )

    assert docs_response.status_code == 200
    assert mcp_response.status_code in {400, 406}


def test_hosted_canary_report_skips_without_public_urls():
    report = smoke.build_hosted_canary_report(Settings())

    assert report["ok"] is True
    assert any(
        check["name"] == "hosted_http_canary" and check["status"] == "skipped"
        for check in report["checks"]
    )
    assert any(
        check["name"] == "hosted_mcp_canary" and check["status"] == "skipped"
        for check in report["checks"]
    )


def test_render_blueprint_and_canary_workflow_exist():
    render_blueprint = ROOT / "render.yaml"
    canary_workflow = ROOT / ".github" / "workflows" / "canary.yml"

    assert render_blueprint.exists()
    assert "healthCheckPath: /healthz" in render_blueprint.read_text()

    workflow_text = canary_workflow.read_text()
    assert "schedule:" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "DEPARTURE_READY_PUBLIC_HTTP_URL" in workflow_text
    assert "DEPARTURE_READY_PUBLIC_MCP_URL" in workflow_text
    assert "upload-artifact" in workflow_text
