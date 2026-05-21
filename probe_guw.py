#!/usr/bin/env python3
"""Probe: solve FC_GUW_01's S2-subset orders directly via Strict (no Balanced
wrapper, no parallel subs). Tells us whether the kError is data-specific to
GUW or a runtime-state issue with Balanced's per-FC iteration.

Usage:
    source .venv/bin/activate && python3 probe_guw.py
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from dataclasses import replace

from backend.ingest import read_master_workbook
from backend.problem import build_problem, stratified_sample, Problem
from backend.methods.strict import StrictMethod


def main() -> int:
    print("Loading master + S2's 1k stratified subset (seed=42)…")
    ingest = read_master_workbook("MMCVRPTW_MLT_MasterData_V4.xlsx")
    base = build_problem(ingest.frames)
    sub_1k = stratified_sample(base, n=1000, seed=42)

    fc_id = "FC_GUW_01"
    guw_orders = [o for o in sub_1k.orders if o.origin_fc == fc_id]
    print(f"  {fc_id} has {len(guw_orders)} orders in the 1k subset.")
    if not guw_orders:
        print("  (no orders → nothing to probe)")
        return 0

    # Build a sub-problem with only those orders + the same shared network
    # the Balanced sub-MILP would see.
    guw_problem = Problem(
        wave_date=sub_1k.wave_date,
        fcs=sub_1k.fcs, scs=sub_1k.scs, dses=sub_1k.dses,
        vehicles=sub_1k.vehicles, carriers=list(sub_1k.carriers),
        lanes=sub_1k.lanes,
        orders=guw_orders,
        order_wave=sub_1k.order_wave, dispatch_wave=sub_1k.dispatch_wave,
        node_schedule=sub_1k.node_schedule,
        ds_dispatch_waves=sub_1k.ds_dispatch_waves,
        sla_config=sub_1k.sla_config, penalty_config=sub_1k.penalty_config,
        pick_pack_config=sub_1k.pick_pack_config,
        lanes_by_od=sub_1k.lanes_by_od,
        multi_stop_eligible_carrier_count=sub_1k.multi_stop_eligible_carrier_count,
    )

    print(f"\nProbe A: Strict on {fc_id}, threads=4, cap=60s")
    r = StrictMethod().solve(guw_problem, time_cap_sec=60.0,
                             gap_target=0.05, threads=4)
    print(f"  status={r.status}")
    print(f"  obj={r.best_objective}")
    print(f"  wall={r.wall_time_sec:.2f}s")
    if r.error_message:
        print(f"  err={r.error_message}")

    print(f"\nProbe B: Strict on {fc_id}, threads=1, cap=120s (single-threaded retry)")
    r1 = StrictMethod().solve(guw_problem, time_cap_sec=120.0,
                              gap_target=0.05, threads=1)
    print(f"  status={r1.status}")
    print(f"  obj={r1.best_objective}")
    print(f"  wall={r1.wall_time_sec:.2f}s")
    if r1.error_message:
        print(f"  err={r1.error_message}")

    # Interpretation
    print()
    if r.status in ("optimal", "gap_reached", "time_limit") and r.best_objective:
        print("→ FC_GUW_01 solves fine in isolation. The failure in Balanced "
              "is a runtime-state issue (state accumulation across consecutive "
              "Highs() instances). The retry-with-threads=1 fix in balanced.py "
              "should catch it.")
    elif r1.status in ("optimal", "gap_reached", "time_limit") and r1.best_objective:
        print("→ FC_GUW_01 fails at threads=4 but succeeds at threads=1. The "
              "threading cap + retry fix in balanced.py should resolve S2.")
    else:
        print("→ FC_GUW_01 fails even in isolation single-threaded. The bug is "
              "data-specific to GUW's orders / lanes. Need to inspect the "
              "GUW-subset model directly (bisect_infeasibility.py on the GUW "
              "sub-problem).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
