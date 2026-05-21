#!/usr/bin/env python3
"""Direct diagnostic for S1 model size — bypasses pytest so prints reach stdout.

Run with:
    source .venv/bin/activate && python3 diag_s1_size.py 2>&1 | tail -50

Identifies which constraint family is generating the bulk of S1's 1.56M rows.
Status will likely be 'infeasible' or 'time_limit' on a 10-second cap; that's
fine — we only need the row-name list, which is populated as the model is
built regardless of solve outcome.
"""
from __future__ import annotations

import re
import sys
from collections import Counter

sys.path.insert(0, ".")

from backend.ingest import read_master_workbook
from backend.problem import build_problem
from backend.methods.strict import StrictMethod


def main() -> int:
    print("Loading master + building base 10k problem…")
    ingest = read_master_workbook("MMCVRPTW_MLT_MasterData_V4.xlsx")
    assert ingest.ok, f"ingest failed: {[e.to_dict() for e in ingest.errors]}"
    problem = build_problem(ingest.frames)
    print(f"  {len(problem.orders):,} orders")

    print("Solving with a 10s cap (we just want the model size)…")
    result = StrictMethod().solve(
        problem, time_cap_sec=10.0, gap_target=0.01, threads=8,
    )

    print(f"\nStatus:               {result.status}")
    print(f"Wall time:            {result.wall_time_sec:.2f}s")
    print(f"Total rows:           {len(result.row_names):>14,}")
    n_vars = len(result.variable_values) if result.variable_values else "(extraction skipped)"
    print(f"Total vars extracted: {n_vars}")

    # Family prefix = leading lowercase+underscore sequence, stopping before
    # the identifier-specific suffix (a digit, an uppercase letter, or a hyphen).
    prefix_re = re.compile(r'^([a-z]+(?:_[a-z]+)*)(?:_[A-Z0-9]|$|-)')

    def row_prefix(name: str) -> str:
        m = prefix_re.match(name)
        return m.group(1) if m else name

    prefixes = Counter(row_prefix(n) for n in result.row_names)
    total = sum(prefixes.values())

    print(f"\nTop 20 row prefixes (out of {len(prefixes)} unique):")
    print(f"{'Prefix':<32} {'Count':>14} {'%':>7}   {'Cum':>14}")
    print("-" * 74)
    covered = 0
    for p, c in prefixes.most_common(20):
        pct = 100.0 * c / max(1, total)
        covered += c
        print(f"{p:<32} {c:>14,} {pct:>6.1f}%   {covered:>14,}")
    print("-" * 74)
    print(f"{'TOP 20 COVERAGE':<32} "
          f"{covered:>14,} {100.0*covered/max(1, total):>6.1f}%")
    print(f"{'TOTAL':<32} {total:>14,}")

    if result.error_message:
        print(f"\nSolver error message: {result.error_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
