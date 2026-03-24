from __future__ import annotations

from departure_ready.services.guide import build_coverage_envelope, build_guide_envelope


def main() -> None:
    print("coverage keys:", [a.airport_code for a in build_coverage_envelope().data.airports])
    print("guide promises:", build_guide_envelope().data.promises)
