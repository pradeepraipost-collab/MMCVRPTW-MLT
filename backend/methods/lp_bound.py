"""Method 5 — LP Bound (Diagnostic relaxation, spec §11.5).

Build the strict per-order model from strict.py but with every variable
continuous. The result is a mathematical lower bound on what any integer
solution can achieve, useful for:

* Sanity-checking that the model is even feasible (catches the V3 critical
  bug from a different angle — if the LP is infeasible, the MILP certainly is).
* Validating other methods' gap claims (Quick's 1–3% gap is from the LP dual).

This method does NOT produce a usable plan — the LP solution is fractional and
order assignments don't correspond to a real shipment plan. The output Excel
fills sheets that require integer decisions with "Not applicable for LP Bound".
"""
from __future__ import annotations

import time

from ..problem import Problem
from .base import Method, MethodResult, LogCapture, CancellationToken
from .strict import _build_and_solve


class LPBoundMethod(Method):
    id = "lp_bound"
    name = "LP Bound — Relaxation"
    badge = "LP BOUND"

    def solve(
        self,
        problem: Problem,
        time_cap_sec: float = 60.0,
        gap_target: float = 0.0,  # ignored for LP
        threads: int = 8,
        log: LogCapture | None = None,
        cancel: CancellationToken | None = None,
    ) -> MethodResult:
        if log:
            log.append("LP Bound: solving the strict model with all binaries relaxed to [0,1].")
        result = _build_and_solve(
            problem=problem,
            method_id="lp_bound",
            relax_integrality=True,
            time_cap_sec=time_cap_sec,
            gap_target=0.0,
            threads=threads,
            log=log,
            cancel=cancel,
        )
        # LP relaxation: status is renamed to "lower_bound" to signal that the
        # objective is a bound, not a plan.
        if result.status in ("optimal", "time_limit"):
            result.status = "lower_bound"
            result.best_lower_bound = result.best_objective  # the LP optimum IS the bound
        return result
