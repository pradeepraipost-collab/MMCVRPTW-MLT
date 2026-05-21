"""S3 — Breach binary is wired (spec §15, §16 rule #2).

V3 declared ``breach[i]`` in the objective with no corresponding constraint.
The variable always took value 0; SLA penalty was decorative.

This test builds a synthetic problem with one order whose Ops_SLA_Deadline
cannot be met by any feasible route. After solving, the SLA penalty must be
non-zero AND that specific order's ``breach`` binary must be 1.0.

Catches: missing breach_link row, wrong row sense, dangling breach in objective.
"""
from __future__ import annotations

import pytest

from backend.methods.strict import StrictMethod
from backend.tests.conftest import build_synthetic_impossible_problem


@pytest.mark.timeout(120)
def test_breach_is_enforced(problem):
    sub, impossible_id = build_synthetic_impossible_problem(problem)
    result = StrictMethod().solve(sub, time_cap_sec=60.0, gap_target=0.05, threads=4)

    assert result.status in ("optimal", "gap_reached", "time_limit"), (
        f"Synthetic problem should solve, got status={result.status}, err={result.error_message}"
    )

    # The row name must exist: breach_link_{order_id}. This catches V3's "declared
    # but not constrained" defect by structure, not just by behaviour.
    breach_rows = [r for r in result.row_names if r.startswith("breach_link_")]
    assert len(breach_rows) >= len(sub.orders), (
        f"Only {len(breach_rows)} breach_link rows for {len(sub.orders)} orders. "
        "V3 had this exact bug: breach[i] declared in objective with NO constraint."
    )

    # The total SLA penalty must be > 0 (the impossible order MUST breach)
    assert result.sla_penalty_inr > 0, (
        f"SLA penalty is ₹{result.sla_penalty_inr:,.0f} on a synthetically impossible deadline. "
        "breach[i] is not constrained by arrival_time − ops_sla_deadline ≤ M·breach. "
        "V3 had this exact bug — see spec §16 rule #2 and §7.13."
    )

    # The specific impossible order's breach var must be ≈ 1.0
    breach_value = result.variable_values.get(("breach", impossible_id))
    assert breach_value is not None, (
        f"breach variable for impossible order {impossible_id} not extracted from solution."
    )
    assert breach_value > 0.99, (
        f"breach[{impossible_id}] = {breach_value:.3f}, expected ≈1.0. "
        "Constraint is not tight at the impossible deadline."
    )
