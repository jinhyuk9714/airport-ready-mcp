from __future__ import annotations

from datetime import UTC, datetime

from departure_ready.connectors.policy import CUSTOMS_TRAVELER_RULES
from departure_ready.contracts import Envelope, Freshness
from departure_ready.domain.models import CustomsGuidance
from departure_ready.services.common import envelope_from_model

GENERAL_DUTY_FREE_THRESHOLD_USD = 800.0
ALCOHOL_MAX_LITERS = 2.0
ALCOHOL_MAX_VALUE_USD = 400.0
PERFUME_MAX_ML = 100.0
CIGARETTE_MAX_COUNT = 200


def build_customs_guidance(
    item_query: str | None = None,
    purchase_value_usd: float | None = None,
    alcohol_liters: float | None = None,
    perfume_ml: float | None = None,
    cigarette_count: int | None = None,
) -> CustomsGuidance:
    now = datetime.now(UTC)
    warnings: list[str] = []
    allowances = [
        "General traveler duty-free allowance: US$800",
        "Alcohol: up to 2 L total and up to US$400 total value",
        "Perfume: up to 100 ml",
        "Cigarettes: up to 200 sticks",
    ]

    declaration_required: bool | None
    summary_parts = []

    if purchase_value_usd is None:
        declaration_required = None
        summary_parts.append(
            "Confirm the total taxable value against the traveler duty-free allowance."
        )
        warnings.append("Total purchase value is missing, so the answer stays bounded.")
    elif purchase_value_usd > GENERAL_DUTY_FREE_THRESHOLD_USD:
        declaration_required = True
        summary_parts.append(
            f"The declared value exceeds the US${GENERAL_DUTY_FREE_THRESHOLD_USD:.0f} "
            "traveler allowance."
        )
    else:
        declaration_required = False
        summary_parts.append(
            f"The declared value is within the US${GENERAL_DUTY_FREE_THRESHOLD_USD:.0f} "
            "traveler allowance."
        )

    if alcohol_liters is not None:
        if alcohol_liters > ALCOHOL_MAX_LITERS:
            declaration_required = True
            warnings.append("Alcohol volume exceeds the 2 L allowance.")
        elif purchase_value_usd is None or purchase_value_usd > ALCOHOL_MAX_VALUE_USD:
            warnings.append(
                "Alcohol is still subject to the separate total-value allowance "
                "and age restrictions."
            )

    if perfume_ml is not None:
        if perfume_ml > PERFUME_MAX_ML:
            declaration_required = True
            warnings.append("Perfume exceeds the 100 ml allowance.")

    if cigarette_count is not None:
        if cigarette_count > CIGARETTE_MAX_COUNT:
            declaration_required = True
            warnings.append("Cigarette count exceeds the 200-stick allowance.")

    if item_query:
        query = item_query.lower()
        if "alcohol" in query and "alcohol" not in " ".join(warnings).lower():
            warnings.append("Alcohol has separate volume and value allowances.")
        if "perfume" in query and "perfume" not in " ".join(warnings).lower():
            warnings.append("Perfume has a separate 100 ml allowance.")
        if "cigarette" in query and "cigarette" not in " ".join(warnings).lower():
            warnings.append("Cigarettes have a separate 200-stick allowance.")

    summary = (
        " ".join(summary_parts)
        if summary_parts
        else "Confirm traveler customs allowances against official rules."
    )
    if declaration_required is None:
        summary = f"{summary} Manual confirmation is still needed for a final customs answer."

    return CustomsGuidance(
        item_query=item_query,
        summary=summary,
        declaration_required=declaration_required,
        purchase_value_usd=purchase_value_usd,
        duty_free_threshold_usd=GENERAL_DUTY_FREE_THRESHOLD_USD,
        allowances=allowances,
        warnings=warnings,
        source=CUSTOMS_TRAVELER_RULES.source(),
        freshness=Freshness.POLICY,
        updated_at=now,
        coverage_note=(
            "Official Korea Customs traveler rules; baggage restrictions and airline "
            "rules are separate."
        ),
    )


def build_customs_envelope(
    item_query: str | None = None,
    purchase_value_usd: float | None = None,
    alcohol_liters: float | None = None,
    perfume_ml: float | None = None,
    cigarette_count: int | None = None,
) -> Envelope[CustomsGuidance]:
    guidance = build_customs_guidance(
        item_query=item_query,
        purchase_value_usd=purchase_value_usd,
        alcohol_liters=alcohol_liters,
        perfume_ml=perfume_ml,
        cigarette_count=cigarette_count,
    )
    return envelope_from_model(guidance, guidance)
