from fastapi.testclient import TestClient

from departure_ready.api.app import create_app
from departure_ready.settings import get_settings


def test_qa_corpus_readiness_for_gmp_family_trip_stays_bounded():
    client = TestClient(create_app())

    response = client.get(
        "/v1/readiness",
        params=[
            ("airport_code", "GMP"),
            ("going_by_car", "true"),
            ("items", "kimchi"),
            ("traveler_flags", "pregnant"),
            ("traveler_flags", "child"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["airport_code"] == "GMP"
    assert payload["data"]["next_actions"]
    assert payload["meta"]["coverage_note"]


def test_qa_corpus_baggage_flags_kimchi_as_liquid_like_item():
    client = TestClient(create_app())

    response = client.get(
        "/v1/baggage-check",
        params={
            "trip_type": "international",
            "item_query": "kimchi",
            "liquid_ml": 120,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["carry_on_allowed"] is False
    assert "kimchi" in payload["data"]["explanation"].lower()


def test_qa_corpus_customs_flags_over_limit_tobacco_purchase():
    client = TestClient(create_app())

    response = client.get(
        "/v1/customs-rules",
        params={
            "purchase_value_usd": 900,
            "cigarette_count": 250,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["declaration_required"] is True
    assert any("200-stick" in warning for warning in payload["data"]["warnings"])


def test_qa_corpus_priority_lane_stays_icn_only():
    client = TestClient(create_app())

    response = client.get(
        "/v1/priority-lane-eligibility",
        params={"airport_code": "GMP", "user_profile": "pregnant traveler"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["eligible"] is False
    assert "ICN-only" in payload["meta"]["coverage_note"]


def test_qa_corpus_supported_airport_parking_avoids_fake_live_fallback(monkeypatch):
    monkeypatch.setenv("DEPARTURE_READY_KAC_SERVICE_KEY", "")
    monkeypatch.setenv("DEPARTURE_READY_IIAC_SERVICE_KEY", "")
    get_settings.cache_clear()
    client = TestClient(create_app())

    response = client.get("/v1/parking", params={"airport_code": "ICN"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["lots"] == []
    assert "currently unavailable" in payload["meta"]["coverage_note"]
    get_settings.cache_clear()
