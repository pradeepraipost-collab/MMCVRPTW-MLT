"""S1 — Strict feasibility on the supplied 10k-order sample (spec §15).

The V3 critical bug: a hard-coded carrier-limit constant combined with
concentration caps left no feasible interior. User clicked Run, got
``Infeasible`` in under a second, no diagnostic.

This test asserts the Strict method on the SUPPLIED data returns a non-error
status — optimal, gap_reached, or time_limit. ``time_limit`` is acceptable
because a real 10k-order MILP routinely hits time caps; what is NOT acceptable
is ``infeasible``.
"""
from __future__ import annotations

import pytest

from backend.methods.strict import StrictMethod


@pytest.mark.timeout(180)
def test_strict_solves_supplied_data(problem):
    """Strict on the supplied 10k-order data must NOT be infeasible.

    V3 critical bug — check carrier-concentration interactions and lane creation
    if this ever fails again.
    """
    result = StrictMethod().solve(problem, time_cap_sec=90.0, gap_target=0.01, threads=8)

    assert result.status in ("optimal", "gap_reached", "time_limit"), (
        f"Strict failed feasibility on supplied data: status={result.status}, "
        f"error={result.error_message}. "
        "V3 critical bug — check carrier-concentration interactions and lane creation."
    )
    # Must have at least one feasible incumbent
    assert result.best_objective is not None and result.best_objective > 0, (
        f"Strict returned no feasible incumbent (obj={result.best_objective}). "
        "Even at time_limit there should be at least one usable solution."
    )
