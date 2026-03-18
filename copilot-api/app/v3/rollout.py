from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RolloutGateResult:
    ok: bool
    warnings: list[str]


def evaluate_rollout_gates(*, confidence: float, rows_returned: int) -> RolloutGateResult:
    min_conf = float(os.getenv("V3_MIN_CONFIDENCE", "0.55"))
    warnings: list[str] = []
    if confidence < min_conf:
        warnings.append(f"planner_confidence_below_threshold:{confidence:.2f}<{min_conf:.2f}")
    if rows_returned == 0:
        warnings.append("zero_rows_returned")
    block_on_low_conf = os.getenv("V3_BLOCK_LOW_CONFIDENCE", "0").strip() in {"1", "true", "TRUE", "yes", "YES"}
    if block_on_low_conf and confidence < min_conf:
        return RolloutGateResult(ok=False, warnings=warnings)
    return RolloutGateResult(ok=True, warnings=warnings)
