from __future__ import annotations

from datetime import datetime

from departure_ready.catalog import normalize_airport_code
from departure_ready.connectors.base import ConnectorContext, OfficialConnector, extract_items
from departure_ready.contracts import Freshness, SourceKind, SourceRef
from departure_ready.domain.models import OperationalSignal

KAC_PROCESSING_DOC_URL = "https://www.data.go.kr/data/15095478/openapi.do"
KAC_PROCESSING_API_URL = "https://api.odcloud.kr/api/getAPRTWaitTime/v1/aprtWaitTime"
KAC_CROWD_DOC_URL = "https://www.data.go.kr/data/15110019/openapi.do"
KAC_CROWD_API_URL = "https://api.odcloud.kr/api/getAPRTPsgrCongestion_v2/v1/aprtPsgrCongestionV2"


class KacProcessingConnector(OfficialConnector):
    source_name = "kac_processing_time"
    source_url = KAC_PROCESSING_DOC_URL

    def __init__(self, context: ConnectorContext, service_key: str | None) -> None:
        super().__init__(context, service_key=service_key)

    async def get_processing_signal(self, airport_code: str) -> OperationalSignal | None:
        service_key = self.require_service_key()
        normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
        payload = await self.get_payload(
            KAC_PROCESSING_API_URL,
            params={
                "serviceKey": service_key,
                "page": 1,
                "perPage": 1,
                "returnType": "JSON",
                "cond[IATA_APCD::EQ]": normalized_airport,
            },
        )
        return self.parse_processing_payload(payload, normalized_airport)

    async def get_crowd_signal(self, airport_code: str) -> OperationalSignal | None:
        service_key = self.require_service_key()
        normalized_airport = normalize_airport_code(airport_code) or airport_code.upper()
        payload = await self.get_payload(
            KAC_CROWD_API_URL,
            params={
                "serviceKey": service_key,
                "page": 1,
                "perPage": 1,
                "returnType": "JSON",
                "cond[IATA_APCD::EQ]": normalized_airport,
            },
        )
        return self.parse_crowd_payload(payload, normalized_airport)

    def parse_processing_payload(
        self,
        payload: dict,
        airport_code: str,
    ) -> OperationalSignal | None:
        rows = extract_items(payload)
        if not rows:
            return None
        row = rows[0]
        total = row.get("STY_TCT_AVG_ALL") or "unknown"
        detail = (
            f"check-in {row.get('STY_TCT_AVG_A', '?')}m, "
            f"id/security {row.get('STY_TCT_AVG_B', '?')}m, "
            f"boarding {row.get('STY_TCT_AVG_C', '?')}m, "
            f"departure {row.get('STY_TCT_AVG_D', '?')}m; total {total}m."
        )
        return OperationalSignal(
            airport_code=airport_code.upper(),
            signal_type="processing_time",
            headline=f"Estimated processing time {total} minutes",
            detail=detail,
            freshness=Freshness.LIVE,
            updated_at=datetime.now().astimezone(),
            source=[
                SourceRef(
                    name=self.source_name,
                    kind=SourceKind.OFFICIAL_API,
                    url=self.source_url,
                )
            ],
            coverage_note=f"KAC processing-time signal for {airport_code.upper()}",
        )

    def parse_crowd_payload(
        self,
        payload: dict,
        airport_code: str,
    ) -> OperationalSignal | None:
        rows = extract_items(payload)
        if not rows:
            return None
        row = rows[0]
        detail = (
            f"A {row.get('CGDR_A_LVL', '?')}, "
            f"B {row.get('CGDR_B_LVL', '?')}, "
            f"C {row.get('CGDR_C_LVL', '?')}, "
            f"overall {row.get('CGDR_ALL_LVL', '?')}."
        )
        return OperationalSignal(
            airport_code=airport_code.upper(),
            signal_type="crowd_info",
            headline=f"Crowd level {row.get('CGDR_ALL_LVL', 'unknown')}",
            detail=detail,
            freshness=Freshness.LIVE,
            updated_at=datetime.now().astimezone(),
            source=[
                SourceRef(
                    name="kac_crowd_info",
                    kind=SourceKind.OFFICIAL_API,
                    url=KAC_CROWD_DOC_URL,
                )
            ],
            coverage_note=f"KAC crowd signal for {airport_code.upper()}",
        )
