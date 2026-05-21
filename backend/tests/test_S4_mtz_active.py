"""S4 — MTZ subtour elimination is active in Strict (spec §15, §16 rule #3).

V3 silently dropped MTZ for solve-time reasons and documented it as a deviation
in the README. The spec is explicit: Strict is spec-literal and MUST include
MTZ on multi-stop-eligible trips. Tractability concerns are addressed by
Method 1 (Quick) and Method 2 (Balanced), not by removing MTZ from Strict.

We inspect ``result.row_names`` for rows whose name starts with ``mtz_``.
Strict's _build_and_solve adds rows named ``mtz_subtour_{trip}_{n1}_{n2}`` for
every multi-stop-eligible trip × node pair, so a non-empty count proves MTZ is
present.
"""
from __future__ import annotations

import pytest

from backend.methods.strict import StrictMethod
from backend.problem import stratified_sample


@pytest.mark.timeout(120)
def test_mtz_present_in_strict(problem):
    # Use a small subset so build completes quickly even on slow CI; MTZ rows
    # are wired regardless of the order count.
    sub = stratified_sample(problem, n=200, seed=42)

    # Sanity precondition: the test data MUST have multi-stop-eligible carriers
    multi_stop_carriers = sum(1 for c in sub.carriers if c.multi_stop_eligible)
    assert multi_stop_carriers > 0, (
        "Test precondition failed: no multi-stop-eligible carriers in supplied data. "
        "S4 cannot verify MTZ presence without them."
    )

    result = StrictMethod().solve(sub, time_cap_sec=60.0, gap_target=0.05, threads=4)
    mtz_rows = [r for r in result.row_names if r.startswith("mtz_")]
    assert len(mtz_rows) > 0, (
        f"Strict model has NO mtz_* rows despite {multi_stop_carriers} multi-stop-eligible "
        "carrier rows. V3 silently dropped MTZ; never again. "
        "Check strict.py constraint 11 — MTZ subtour elimination must be added "
        "for every multi-stop-eligible trip in (SC→DS, FC→DS) lanes."
    )
