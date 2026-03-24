from fastapi.testclient import TestClient

from departure_ready.api.app import create_app


def test_healthz():
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_coverage():
    client = TestClient(create_app())
    response = client.get("/v1/coverage")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert any(item["airport_code"] == "ICN" for item in data["data"]["airports"])


def test_baggage_check_returns_policy_guidance():
    client = TestClient(create_app())
    response = client.get(
        "/v1/baggage-check",
        params={"trip_type": "international", "item_query": "lotion", "liquid_ml": 120},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["carry_on_allowed"] is False
    assert payload["meta"]["freshness"] == "policy"


def test_customs_rules_flags_declaration_threshold():
    client = TestClient(create_app())
    response = client.get("/v1/customs-rules", params={"purchase_value_usd": 900})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["declaration_required"] is True
    assert payload["data"]["duty_free_threshold_usd"] == 800.0


def test_parking_returns_bounded_unavailable_state_without_keys():
    client = TestClient(create_app())
    response = client.get("/v1/parking", params={"airport_code": "ICN"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["airport_code"] == "ICN"
    assert payload["data"]["recommendation"]
    assert payload["meta"]["coverage_note"]


def test_priority_lane_eligibility_uses_policy_rules():
    client = TestClient(create_app())
    response = client.get(
        "/v1/priority-lane-eligibility",
        params={"airport_code": "ICN", "user_profile": "pregnant traveler"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["eligible"] is True


def test_readiness_envelope_exposes_trust_boundary():
    client = TestClient(create_app())
    response = client.get("/v1/readiness", params={"airport_code": "GMP"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["meta"]["source"]
    assert payload["meta"]["coverage_note"]


def test_readiness_returns_envelope():
    client = TestClient(create_app())
    response = client.get("/v1/readiness", params={"airport_code": "ICN"})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["meta"]["coverage_note"]
    assert data["data"]["airport_code"] == "ICN"
