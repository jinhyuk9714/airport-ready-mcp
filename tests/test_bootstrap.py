from departure_ready.api.app import create_app
from departure_ready.mcp.server import mcp


def test_app_factory_has_expected_routes():
    app = create_app()
    paths = {route.path for route in app.routes}

    assert "/healthz" in paths
    assert "/v1/coverage" in paths
    assert "/v1/guide" in paths
    assert "/v1/readiness" in paths


def test_mcp_server_has_guide_and_coverage_tools():
    tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}

    assert "tool_get_coverage" in tool_names
    assert "tool_get_guide" in tool_names
    assert "tool_get_departure_readiness" in tool_names
