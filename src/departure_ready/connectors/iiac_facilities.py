from __future__ import annotations

from datetime import datetime

from departure_ready.connectors.base import ConnectorContext, OfficialConnector, extract_items
from departure_ready.connectors.iiac_parking import infer_iiac_terminal
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import FacilityMatch, ShopMatch

IIAC_FACILITIES_DOC_URL = "https://www.data.go.kr/data/15095064/openapi.do"
IIAC_FACILITIES_API_URL = "http://apis.data.go.kr/B551177/FacilitiesInformation/getFacilitesInfo"
IIAC_SHOPS_DOC_URL = "https://www.data.go.kr/data/15095043/openapi.do"
IIAC_SHOPS_API_URL = "http://apis.data.go.kr/B551177/StatusOfFacility/getFacilityKR"


class IiacFacilityConnector(OfficialConnector):
    source_name = "iiac_facilities"
    source_url = IIAC_FACILITIES_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None) -> None:
        super().__init__(context, service_key=service_key)

    async def find_facilities(
        self,
        query: str | None,
        category: str | None = None,
    ) -> list[FacilityMatch]:
        service_key = self.require_service_key()
        params = {
            "serviceKey": service_key,
            "pageNo": 1,
            "numOfRows": 50,
            "lang": "K",
            "type": "json",
        }
        if query:
            params["facilitynm"] = query
        payload = await self.get_payload(IIAC_FACILITIES_API_URL, params=params)
        facilities = self.parse_facilities_payload(payload)
        if category:
            facilities = [item for item in facilities if category.lower() in item.category.lower()]
        return facilities

    async def find_shops(
        self,
        query: str | None,
        category: str | None = None,
    ) -> list[ShopMatch]:
        service_key = self.require_service_key()
        params = {
            "serviceKey": service_key,
            "pageNo": 1,
            "numOfRows": 50,
            "type": "json",
        }
        if query:
            params["facility_nm"] = query
        payload = await self.get_payload(IIAC_SHOPS_API_URL, params=params)
        shops = self.parse_shops_payload(payload)
        if category:
            shops = [item for item in shops if category.lower() in item.category.lower()]
        return shops

    def parse_facilities_payload(self, payload: dict) -> list[FacilityMatch]:
        rows = extract_items(payload)
        facilities: list[FacilityMatch] = []
        for row in rows:
            location = row.get("lcnm") or ""
            facilities.append(
                FacilityMatch(
                    airport_code="ICN",
                    terminal=infer_iiac_terminal(row.get("terminalid") or location),
                    name=row.get("facilitynm") or "Facility",
                    category=row.get("scategorynm")
                    or row.get("mcategorynm")
                    or row.get("lcategorynm")
                    or "facility",
                    location_text=location,
                    inout=_map_inout(row.get("arrordep")),
                    floor=row.get("floorinfo"),
                    operating_hours=row.get("servicetime"),
                    phone=row.get("tel"),
                    freshness=Freshness.DAILY,
                    updated_at=datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name=self.source_name,
                            kind=SourceKind.OFFICIAL_API,
                            url=self.source_url,
                        )
                    ],
                    coverage_note="IIAC terminal facility information",
                )
            )
        return facilities

    def parse_shops_payload(self, payload: dict) -> list[ShopMatch]:
        rows = extract_items(payload)
        shops: list[ShopMatch] = []
        for row in rows:
            location = row.get("lckoreannm") or ""
            shops.append(
                ShopMatch(
                    airport_code="ICN",
                    terminal=infer_iiac_terminal(location),
                    name=row.get("entrpskoreannm") or "Shop",
                    brand=row.get("entrpskoreannm"),
                    category="shop",
                    location_text=location,
                    inout=_map_inout(row.get("arrordep")),
                    operating_hours=row.get("servicetime"),
                    phone=row.get("tel"),
                    freshness=Freshness.DAILY,
                    updated_at=datetime.now().astimezone(),
                    source=[
                        SourceRef(
                            name="iiac_shops",
                            kind=SourceKind.OFFICIAL_API,
                            url=IIAC_SHOPS_DOC_URL,
                        )
                    ],
                    coverage_note="IIAC commercial facility information",
                )
            )
        return shops


def _map_inout(value: str | None) -> str | None:
    if value == "D":
        return "departure"
    if value == "A":
        return "arrival"
    return None
