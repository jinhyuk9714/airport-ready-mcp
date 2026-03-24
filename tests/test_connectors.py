from __future__ import annotations

import asyncio

import httpx

from departure_ready.connectors.base import ConnectorContext, OfficialConnector
from departure_ready.connectors.iiac_facilities import IiacFacilityConnector
from departure_ready.connectors.iiac_flight import IiacFlightConnector
from departure_ready.connectors.iiac_parking import IiacParkingConnector
from departure_ready.connectors.kac_flight import KacFlightConnector
from departure_ready.connectors.kac_parking import KacParkingConnector
from departure_ready.connectors.kac_processing import KacProcessingConnector


class _RetryConnector(OfficialConnector):
    source_name = "retry_test"
    source_url = "https://example.invalid/retry"


def test_base_connector_retries_once_before_success():
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("slow")
        return httpx.Response(200, json={"response": {"body": {"items": {"item": []}}}})

    connector = _RetryConnector(
        ConnectorContext(
            timeout_sec=0.1,
            default_headers={},
            max_retries=2,
            transport=httpx.MockTransport(handler),
        )
    )

    payload = asyncio.run(connector.get_payload("https://example.invalid/retry"))

    assert payload["response"]["body"]["items"]["item"] == []
    assert calls["count"] == 2


def test_kac_parking_parser_maps_status_and_congestion():
    connector = KacParkingConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")

    status_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "aprKor": "김포국제공항",
                            "parkingAirportCodeName": "국내선 주차장",
                            "parkingFullSpace": "1000",
                            "parkingIstay": "450",
                            "parkingGetdate": "20260324",
                            "parkingGettime": "101500",
                        }
                    ]
                }
            }
        }
    }
    congestion_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "parkingAirportCodeName": "국내선 주차장",
                            "parkingCongestion": "원활",
                            "parkingCongestionDegree": "1",
                            "parkingOccupiedSpace": "450",
                            "parkingTotalSpace": "1000",
                            "sysGetdate": "20260324",
                            "sysGettime": "101500",
                        }
                    ]
                }
            }
        }
    }

    lots = connector.parse_status_payload(status_payload, "GMP")
    merged = connector.apply_congestion_payload(lots, congestion_payload)

    assert merged[0].airport_code == "GMP"
    assert merged[0].lot_name == "국내선 주차장"
    assert merged[0].available_spaces == 550
    assert merged[0].congestion_label == "원활"


def test_kac_flight_parser_maps_flight_rows():
    connector = KacFlightConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    payload = {
        "data": [
            {
                "AIR_FLN": "KE123",
                "AIRLINE_KOREAN": "대한항공",
                "STD": "2026-03-24 10:00",
                "ETD": "2026-03-24 10:30",
                "GATE": "12",
                "RMK_KOR": "지연",
            }
        ]
    }

    flights = connector.parse_flight_payload(payload, "GMP")

    assert flights[0].flight_no == "KE123"
    assert flights[0].airline == "대한항공"
    assert flights[0].gate == "12"
    assert flights[0].status_label == "지연"


def test_kac_processing_parser_maps_total_wait_signal():
    connector = KacProcessingConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    payload = {
        "data": [
            {
                "IATA_APCD": "GMP",
                "PRC_HR": "10",
                "STY_TCT_AVG_A": "5",
                "STY_TCT_AVG_B": "4",
                "STY_TCT_AVG_C": "6",
                "STY_TCT_AVG_D": "7",
                "STY_TCT_AVG_ALL": "22",
            }
        ]
    }

    signal = connector.parse_processing_payload(payload, "GMP")

    assert signal is not None
    assert signal.airport_code == "GMP"
    assert "22" in signal.detail


def test_iiac_parking_parser_maps_lot_rows():
    connector = IiacParkingConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "floor": "T1 장기 P1",
                            "parkingarea": "1000",
                            "parking": "650",
                            "datetm": "2026-03-24 10:15:00",
                        }
                    ]
                }
            }
        }
    }

    lots = connector.parse_status_payload(payload)

    assert lots[0].airport_code == "ICN"
    assert lots[0].available_spaces == 350
    assert lots[0].terminal == "T1"


def test_iiac_flight_parser_maps_same_day_rows():
    connector = IiacFlightConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "flightId": "OZ101",
                            "airline": "ASIANA AIRLINES",
                            "scheduleDateTime": "20260324110000",
                            "estimatedDateTime": "20260324112000",
                            "gatenumber": "248",
                            "remark": "BOARDING",
                            "terminalId": "P03",
                        }
                    ]
                }
            }
        }
    }

    flights = connector.parse_today_payload(payload)

    assert flights[0].flight_no == "OZ101"
    assert flights[0].gate == "248"
    assert flights[0].terminal == "T1"


def test_iiac_facility_and_shop_parsers_map_core_fields():
    connector = IiacFacilityConnector(ConnectorContext(timeout_sec=1, default_headers={}), "key")
    facility_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "facilitynm": "약국",
                            "lcategorynm": "의료/약국",
                            "lcnm": "제1여객터미널 3층 10번 게이트 부근",
                            "servicetime": "06:00 ~ 22:00",
                            "arrordep": "D",
                            "floorinfo": "3F",
                            "terminalid": "P03",
                            "tel": "032-000-0000",
                        }
                    ]
                }
            }
        }
    }
    shop_payload = {
        "response": {
            "body": {
                "items": {
                    "item": [
                        {
                            "entrpskoreannm": "편의점",
                            "trtmntprdlstkoreannm": "음료, 간식",
                            "lckoreannm": "제2여객터미널 3층 일반지역",
                            "servicetime": "24시간",
                            "arrordep": "D",
                            "tel": "032-111-1111",
                        }
                    ]
                }
            }
        }
    }

    facilities = connector.parse_facilities_payload(facility_payload)
    shops = connector.parse_shops_payload(shop_payload)

    assert facilities[0].name == "약국"
    assert facilities[0].terminal == "T1"
    assert shops[0].name == "편의점"
    assert shops[0].category == "shop"
