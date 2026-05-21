#!/usr/bin/env python3
"""Bisection diagnostic — disable one constraint family at a time and report
which absence flips status from 'infeasible' to feasible.

Usage:
    source .venv/bin/activate
    python3 bisect_infeasibility.py [size] [method]

Where:
    size   = "synthetic" (5 orders, default) | "1k" | "10k"
    method = "strict" (default) | "quick"

Examples:
    python3 bisect_infeasibility.py                # synthetic + strict
    python3 bisect_infeasibility.py 10k strict     # full S1 reproduction
    python3 bisect_infeasibility.py 1k quick       # S2/S6 reproduction

The first family whose absence yields 'optimal' / 'gap_reached' / 'time_limit'
is the culprit. If ALL disabled still infeasible, the bug is in variable
bounds, coverage logic, or trip enumeration (not a row family).
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from backend.ingest import read_master_workbook
from backend.problem import build_problem, stratified_sample
from backend.tests.conftest import build_synthetic_impossible_problem


# Constraint family names recognised by Strict and Quick. These match the
# `if "<name>" not in disabled:` guards in their respective files.
STRICT_FAMILIES = [
    "coverage", "flow_consistency", "trip_activation", "trip_capacity",
    "trip_load", "load_disjunction", "fc_throughput", "sc_throughput",
    "concentration", "mtz", "arrival_time", "breach_link",
]
QUICK_FAMILIES = [
    "coverage", "fc_throughput", "concentration",
    "arrival_time", "breach_link",
]


def main() -> int:
    size = sys.argv[1] if len(sys.argv) > 1 else "synthetic"
    method_name = sys.argv[2] if len(sys.argv) > 2 else "strict"

    print(f"Bisection: size={size}, method={method_name}")
    print("Loading master + building problem…")
    ingest = read_master_workbook("MMCVRPTW_MLT_MasterData_V4.xlsx")
    assert ingest.ok, f"ingest failed: {[e.to_dict() for e in ingest.errors]}"
    base = build_problem(ingest.frames)

    if size == "10k":
        problem = base
        time_cap = 30.0  # short per-bisection cap; we just want feasibility flip
    elif size == "1k":
        problem = stratified_sample(base, n=1000, seed=42)
        time_cap = 60.0
    elif size == "synthetic":
        problem, _ = build_synthetic_impossible_problem(base)
        time_cap = 30.0
    else:
        print(f"Unknown size {size!r}. Use synthetic|1k|10k.")
        return 2

    if method_name == "quick":
        from backend.methods.quick import QuickMethod
        Method = QuickMethod
        families = QUICK_FAMILIES
    elif method_name == "strict":
        from backend.methods.strict import StrictMethod
        Method = StrictMethod
        families = STRICT_FAMILIES
    else:
        print(f"Unknown method {method_name!r}. Use strict|quick.")
        return 2

    print(f"  {len(problem.orders):,} orders, time_cap={time_cap}s per probe")
    print()

    def _row(label: str, result) -> None:
        obj = ("-" if result.best_objective is None
               else f"{result.best_objective:>14,.0f}")
        print(f"{label:<22} {result.status:<28} {obj}  {result.wall_time_sec:>8.2f}")

    print(f"{'Family disabled':<22} {'Status':<28} {'Obj (INR)':>14}  {'Wall (s)':>8}")
    print("-" * 80)

    baseline = Method().solve(problem, time_cap_sec=time_cap)
    _row("(none — baseline)", baseline)

    for fam in families:
        try:
            r = Method().solve(
                problem,
                time_cap_sec=time_cap,
                disable_constraint_families={fam},
            )
            _row(fam, r)
        except Exception as e:  # noqa: BLE001
            print(f"{fam:<22} EXCEPTION: {type(e).__name__}: {e}")

    print()
    print("Now disabling ALL families simultaneously:")
    all_off = Method().solve(
        problem,
        time_cap_sec=time_cap,
        disable_constraint_families=set(families),
    )
    _row("ALL disabled", all_off)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
