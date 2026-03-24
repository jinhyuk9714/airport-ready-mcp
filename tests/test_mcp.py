from departure_ready.mcp.server import (
    mcp,
    tool_check_baggage_rules,
    tool_get_customs_rules,
    tool_get_parking_status,
)


def test_mcp_registers_core_domain_tools():
    tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}

    assert "tool_get_departure_readiness" in tool_names
    assert "tool_get_parking_status" in tool_names
    assert "tool_check_baggage_rules" in tool_names
    assert "tool_get_customs_rules" in tool_names


def test_mcp_baggage_tool_returns_structured_policy_output():
    payload = tool_check_baggage_rules(
        item_query="lotion",
        trip_type="international",
        liquid_ml=120,
    )

    assert payload["ok"] is True
    assert payload["data"]["carry_on_allowed"] is False


def test_mcp_customs_tool_returns_threshold_guidance():
    payload = tool_get_customs_rules(purchase_value_usd=900)

    assert payload["ok"] is True
    assert payload["data"]["declaration_required"] is True


def test_mcp_parking_tool_returns_bounded_unavailable_state_without_keys():
    payload = tool_get_parking_status(airport_code="ICN")

    assert payload["ok"] is True
    assert payload["data"]["airport_code"] == "ICN"
