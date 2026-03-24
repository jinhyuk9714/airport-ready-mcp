from __future__ import annotations

from departure_ready.catalog import SUPPORT_MATRIX, internal_meta
from departure_ready.contracts import Envelope
from departure_ready.domain.models import AirportSupport, CoveragePayload, GuidePayload


def build_coverage_envelope() -> Envelope[CoveragePayload]:
    airports = [
        AirportSupport(airport_code=code, **payload) for code, payload in SUPPORT_MATRIX.items()
    ]
    payload = CoveragePayload(
        airports=airports,
        contract_summary=[
            "official source first",
            "freshness visible in every response",
            "unsupported coverage is explicit",
            "live fetch failures never become guessed values",
        ],
    )
    return Envelope(
        meta=internal_meta("Repository support matrix and trust contract."),
        data=payload,
    )


def build_guide_envelope() -> Envelope[GuidePayload]:
    payload = GuidePayload(
        promises=[
            "tell the user whether they should leave now based on official "
            "operational data when available",
            "keep parking, baggage, customs, and service eligibility separate",
            "label live vs forecast vs policy data explicitly",
        ],
        out_of_scope=[
            "generic map routing",
            "travel visa advice",
            "non-official airport crowd guesses",
        ],
    )
    return Envelope(
        meta=internal_meta("Product guide for the current repository scaffold."),
        data=payload,
    )
