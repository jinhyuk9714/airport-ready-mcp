from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from departure_ready.contracts import Freshness, SourceKind, SourceRef


@dataclass(slots=True)
class PolicyStamp:
    name: str
    url: str

    def source(self) -> list[SourceRef]:
        return [SourceRef(name=self.name, kind=SourceKind.OFFICIAL_WEB, url=self.url)]

    def now(self) -> datetime:
        return datetime.now(UTC)

    @property
    def freshness(self) -> Freshness:
        return Freshness.POLICY


IIAC_BAGGAGE_POLICY = PolicyStamp(
    name="iiac_baggage_policy",
    url="https://www.airport.kr/ap_ko/905/subview.do",
)
CUSTOMS_TRAVELER_RULES = PolicyStamp(
    name="customs_traveler_rules",
    url="https://www.customs.go.kr/kcs/cm/cntnts/cntntsView.do?cntntsId=829&mi=2837",
)
IIAC_SMARTPASS = PolicyStamp(
    name="iiac_smartpass",
    url="https://www.airport.kr/ap_ko/889/subview.do",
)
IIAC_SELF_CHECKIN = PolicyStamp(
    name="iiac_self_checkin_bagdrop",
    url="https://www.airport.kr/ap_ko/891/subview.do",
)
IIAC_EASY_DROP = PolicyStamp(
    name="iiac_easy_drop",
    url="https://www.airport.kr/ap_ko/890/subview.do",
)
IIAC_PRIORITY_LANE = PolicyStamp(
    name="iiac_priority_lane",
    url="https://www.airport.kr/ap_ko/908/subview.do",
)
KAC_PARKING_DISCOUNT = PolicyStamp(
    name="kac_parking_discount",
    url="https://park.airport.co.kr/humandiscount/intro.do",
)
KAC_PARKING_RESERVATION = PolicyStamp(
    name="kac_parking_reservation",
    url="https://park.airport.co.kr/notice/notice.do",
)
