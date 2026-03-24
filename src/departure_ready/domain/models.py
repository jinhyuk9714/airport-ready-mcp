from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from departure_ready.contracts import AirportCode, Freshness, SourceRef


class TrustStampedModel(BaseModel):
    source: list[SourceRef]
    freshness: Freshness
    updated_at: datetime
    coverage_note: str


class AirportSupport(BaseModel):
    airport_code: AirportCode | str
    name_ko: str
    coverage: Literal["strong", "selected", "static_only"]
    domains: list[str]


class CoveragePayload(BaseModel):
    airports: list[AirportSupport]
    contract_summary: list[str]


class GuidePayload(BaseModel):
    product_name: str = "Departure Ready MCP"
    primary_surface: str = "Remote MCP"
    companion_surface: str = "HTTP API"
    promises: list[str]
    out_of_scope: list[str]


class ParkingLotSnapshot(TrustStampedModel):
    airport_code: str
    lot_name: str
    lot_id: str | None = None
    terminal: str | None = None
    available_spaces: int | None = None
    occupancy_pct: float | None = None
    congestion_label: str | None = None
    status: Literal["available", "limited", "full", "unknown", "unavailable"] = "unknown"
    estimated_fee_krw: int | None = None
    fee_note: str | None = None


class ParkingPayload(BaseModel):
    airport_code: str
    terminal: str | None = None
    recommendation: str
    lots: list[ParkingLotSnapshot] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)


class FlightSnapshot(TrustStampedModel):
    airport_code: str
    flight_no: str | None = None
    airline: str | None = None
    terminal: str | None = None
    gate: str | None = None
    checkin_counter: str | None = None
    scheduled_at: datetime | None = None
    changed_at: datetime | None = None
    status_label: str | None = None
    signal_kind: Literal["live", "forecast", "daily", "unavailable"] = "unavailable"


class OperationalSignal(TrustStampedModel):
    airport_code: str
    signal_type: str
    headline: str
    detail: str


class ProcessingSignal(TrustStampedModel):
    airport_code: str
    label: str
    detail: str
    total_minutes: int | None = None


class BaggageDecision(TrustStampedModel):
    item_query: str
    trip_type: Literal["domestic", "international"]
    carry_on_allowed: bool | None = None
    checked_allowed: bool | None = None
    declaration_needed: bool | None = None
    category: str
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    manual_confirmation_required: bool = False


class CustomsGuidance(TrustStampedModel):
    item_query: str | None = None
    summary: str
    declaration_required: bool | None = None
    purchase_value_usd: float | None = None
    duty_free_threshold_usd: float = 800.0
    allowances: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ServiceEligibility(TrustStampedModel):
    airport_code: str
    service_name: str
    eligible: bool | None = None
    reason: str
    evidence: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)


class SelfServiceOptions(TrustStampedModel):
    airport_code: str
    airline: str | None = None
    smart_pass_supported: bool | None = None
    self_checkin_supported: bool | None = None
    self_bag_drop_supported: bool | None = None
    easy_drop_supported: bool | None = None
    notes: list[str] = Field(default_factory=list)


class PriorityLaneEligibility(TrustStampedModel):
    airport_code: str
    eligible: bool | None = None
    reason: str
    evidence: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)


class FacilityMatch(TrustStampedModel):
    airport_code: str
    terminal: str | None = None
    name: str
    category: str
    location_text: str
    inout: str | None = None
    floor: str | None = None
    operating_hours: str | None = None
    phone: str | None = None


class ShopMatch(FacilityMatch):
    brand: str | None = None


class FacilityPayload(BaseModel):
    airport_code: str
    terminal: str | None = None
    matches: list[FacilityMatch] = Field(default_factory=list)


class ReadinessCard(TrustStampedModel):
    airport_code: str
    summary: str
    operational_signal: str
    operational_signals: list[OperationalSignal] = Field(default_factory=list)
    next_actions: list[str]
    flight: FlightSnapshot | None = None
    parking: ParkingPayload | None = None
    baggage_warnings: list[BaggageDecision] = Field(default_factory=list)
    service_eligibility: list[ServiceEligibility] = Field(default_factory=list)
    facility_hints: list[FacilityMatch] = Field(default_factory=list)
