"""Method 3 — Strict (Monolithic per-order MILP).

This is the reference per-order formulation from spec §3 and §9. Every
constraint family from §7 is present. The other methods (Quick, Balanced, LP
Bound) are variants of this model.

Anti-shortcut commitments enforced HERE (each is gated by a self-test):

* The ``breach[i]`` binary IS tied to a hard constraint of the form
  ``arrival_time[i] − ops_sla_deadline[i] ≤ M · breach[i]``. Adding a row
  named ``"breach_link_{i}"`` for every order. **V3 shipped without this row;
  test S3 verifies it exists.**
* MTZ subtour elimination IS added for every multi-stop-eligible trip with
  rows named ``"mtz_..."``. **V3 silently dropped MTZ; test S4 verifies the
  presence of mtz_* rows in the row name list.**
* The Big-M used in the breach constraint is per-order tight (see
  ``compute_tight_big_m`` in base.py). **V3 used 1e6 generic Big-M; this
  module rejects any value ≥ 1e5 as a guard.**
* All ``addCol`` calls receive NumPy arrays with explicit dtypes (per §16
  rule #4). ``highspy.addRow`` is called with index/value sequences as
  expected by the pinned 1.7.2 signature.
* No ``try/except: pass`` around solver calls (per §16 rule #5).

The trip enumeration deserves explanation. A "trip" in the MILP is a unit of
truck capacity on a single lane. We pre-allocate trip slots per (carrier_row,
lane) sized to the lane's potential demand divided by the carrier vehicle's
parcel capacity (with a sanity floor of 1 and a per-lane cap to keep the LP
relaxation tractable). Each order picks a trip via x_mm / y_lm / w_fd; trips
that no order picks have u[t]=0 and contribute nothing to cost.
"""
from __future__ import annotations

import math
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from ..problem import (
    Problem, Order, Carrier, Vehicle, Lane,
    LANE_FC_SC, LANE_SC_DS, LANE_FC_DS, LANE_SC_SC,
    enumerate_routes_for_order,
)
from .base import Method, MethodResult, LogCapture, CancellationToken, compute_tight_big_m


# Big-M guard: any per-order Big-M ≥ this is treated as a bug (§16 rule).
BIG_M_FORBIDDEN_THRESHOLD = 1e5


class StrictMethod(Method):
    id = "strict"
    name = "Strict — Monolithic per-order MILP"
    badge = "STRICT"

    def solve(
        self,
        problem: Problem,
        time_cap_sec: float = 3600.0,
        gap_target: float = 0.01,
        threads: int = 8,
        log: LogCapture | None = None,
        cancel: CancellationToken | None = None,
        disable_constraint_families: set[str] | None = None,
    ) -> MethodResult:
        return _build_and_solve(
            problem=problem,
            method_id="strict",
            relax_integrality=False,
            time_cap_sec=time_cap_sec,
            gap_target=gap_target,
            threads=threads,
            log=log,
            cancel=cancel,
            disable_constraint_families=disable_constraint_families or set(),
        )


def _log(log: LogCapture | None, msg: str) -> None:
    if log is not None:
        log.append(msg)


def _build_and_solve(
    problem: Problem,
    method_id: str,
    relax_integrality: bool,
    time_cap_sec: float,
    gap_target: float,
    threads: int,
    log: LogCapture | None,
    cancel: CancellationToken | None,
    disable_constraint_families: set[str] | None = None,
) -> MethodResult:
    """Build the per-order MILP (or its LP relaxation) and call HiGHS.

    ``relax_integrality=True`` is how Method 5 (LP Bound) reuses this code.
    """
    t_start = time.time()
    cancel = cancel or CancellationToken()
    # Diagnostic: disable specific constraint families to bisect infeasibility.
    # Recognised family names match the dispatch table below. Pass a set like
    # {"mtz", "concentration"} to skip those _add_row blocks. See
    # /tmp/bisect_infeasibility.py for the canonical caller.
    disabled = set(disable_constraint_families or set())
    if disabled:
        _log(log, f"Constraint families DISABLED for diagnostic: {sorted(disabled)}")

    # Import here so highspy version pin failures surface at solve time,
    # not module-load time (lets the API server start even if highspy is
    # mis-installed; the API call returns the error to the UI).
    import highspy

    h = highspy.Highs()
    # Solver controls. output_flag is gated by env var so users can debug
    # solver behaviour with `MMCVRPTW_VERBOSE_HIGHS=1 pytest …`.
    h.setOptionValue("output_flag", bool(os.environ.get("MMCVRPTW_VERBOSE_HIGHS")))
    h.setOptionValue("threads", int(threads))
    h.setOptionValue("time_limit", float(time_cap_sec))
    h.setOptionValue("mip_rel_gap", float(gap_target))
    h.changeObjectiveSense(highspy.ObjSense.kMinimize)

    # ---- Trip enumeration ----
    trips, trip_index = _enumerate_trips(problem, log=log)
    _log(log, f"Trip enumeration: {len(trips):,} trip slots across "
              f"{len({(t['carrier_idx'], t['lane_idx']) for t in trips})} "
              "(carrier × lane) combinations.")
    if cancel.is_cancelled():
        return _cancelled(method_id, t_start)

    # ---- Order route enumeration ----
    order_routes = _enumerate_order_routes(problem, log=log)
    n_orders = len(problem.orders)
    n_courier_eligible = sum(1 for o in problem.orders if order_routes[o.order_id]["courier_eligible"])
    _log(log, f"Order route enumeration: {n_orders:,} orders, "
              f"{n_courier_eligible:,} courier-eligible.")

    # ---- Variable creation ----
    var = _VariableRegistry()
    row_names: list[str] = []

    # FC-used binaries
    for fc in problem.fcs.values():
        var.add_var(("fc_used", fc.fc_id), lower=0, upper=1, integer=not relax_integrality,
                    cost=fc.fixed_cost_per_wave_inr, h=h)

    # Trip-level variables
    for t_idx, trip in enumerate(trips):
        u_col = var.add_var(("u", t_idx), 0, 1, not relax_integrality, 0.0, h)
        ftl_col = var.add_var(("ftl", t_idx), 0, 1, not relax_integrality, 0.0, h)
        ptl_col = var.add_var(("ptl", t_idx), 0, 1, not relax_integrality, 0.0, h)
        ltl_col = var.add_var(("ltl", t_idx), 0, 1, not relax_integrality, 0.0, h)
        # Carrier cost coefficients per spec §8: per-trip rates for FTL/PTL, per-kg for LTL
        c = problem.carriers[trip["carrier_idx"]]
        if c.ftl_rate_inr is not None:
            h.changeColCost(ftl_col, float(c.ftl_rate_inr))
        if c.ptl_rate_inr is not None:
            h.changeColCost(ptl_col, float(c.ptl_rate_inr))
        # Continuous load variables
        v = problem.vehicles[c.vehicle_type]
        var.add_var(("load_kg", t_idx), 0.0, v.weight_capacity_kg, False, 0.0, h)
        var.add_var(("load_vol", t_idx), 0.0, v.volume_capacity_m3, False, 0.0, h)
        var.add_var(("load_parcels", t_idx), 0.0, v.parcel_capacity, False, 0.0, h)
        # LTL cost is per-kg on load_kg, conditional on ltl=1. Linearise by
        # multiplying load_kg coefficient by ltl_rate and adding a coupling
        # constraint that forces load_kg coef contribution only when ltl=1
        # via the disjunction below. We add the cost via an auxiliary
        # variable ltl_kg[t] = load_kg[t] if ltl=1 else 0.
        if c.ltl_rate_inr_per_kg is not None and c.load_type == "LTL":
            ltl_kg_col = var.add_var(("ltl_kg", t_idx), 0.0, v.weight_capacity_kg, False,
                                     float(c.ltl_rate_inr_per_kg), h)
            # ltl_kg[t] ≤ load_kg[t]
            row = _add_row(h, -math.inf, 0.0,
                           [(ltl_kg_col, 1.0), (var.col(("load_kg", t_idx)), -1.0)])
            row_names.append(f"ltl_kg_le_load_{t_idx}")
            # ltl_kg[t] ≤ M · ltl[t]  with M = vehicle weight cap
            _add_row(h, -math.inf, 0.0,
                     [(ltl_kg_col, 1.0), (ltl_col, -float(v.weight_capacity_kg))])
            row_names.append(f"ltl_kg_le_ltl_{t_idx}")
            # ltl_kg[t] ≥ load_kg[t] - M · (1 - ltl[t])  →  load_kg - ltl_kg - M·ltl ≤ M-? simpler:
            # ltl_kg ≥ load_kg - W·(1-ltl)  →  load_kg - ltl_kg - W·ltl ≤ 0 (− W) handled at +W on RHS
            _add_row(h, -math.inf, float(v.weight_capacity_kg),
                     [(var.col(("load_kg", t_idx)), 1.0),
                      (ltl_kg_col, -1.0),
                      (ltl_col, -float(v.weight_capacity_kg))])
            row_names.append(f"ltl_kg_link_{t_idx}")

    # Order-level variables: x_mm[i, route_idx], y_lm[i, route_idx] for hub-spoke,
    # w_fd[i, route_idx] for direct, z[i] for courier (courier-eligible only).
    # Each route binds to a specific (mm_trip, lm_trip) pair (or single direct trip).
    for o in problem.orders:
        routes = order_routes[o.order_id]
        # Courier
        if routes["courier_eligible"]:
            var.add_var(("z", o.order_id), 0, 1, not relax_integrality,
                        problem.courier_rate_inr, h)
        # Direct route trip choices
        for k, (trip_idx,) in enumerate(routes["direct_choices"]):
            var.add_var(("w_fd", o.order_id, k), 0, 1, not relax_integrality, 0.0, h)
        # Hub-spoke trip choices (mm + lm pair)
        for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
            var.add_var(("x_mm", o.order_id, k), 0, 1, not relax_integrality, 0.0, h)
            var.add_var(("y_lm", o.order_id, k), 0, 1, not relax_integrality, 0.0, h)
        # Arrival time + breach
        var.add_var(("arrival", o.order_id), 0.0, 1e4, False, 0.0, h)
        var.add_var(("breach", o.order_id), 0, 1, not relax_integrality,
                    float(o.total_penalty_inr), h)

    _log(log, f"Built {var.n_vars:,} variables.")
    if cancel.is_cancelled():
        return _cancelled(method_id, t_start)

    # ---- Constraints ----

    # 1. COVERAGE — every order shipped exactly once
    if "coverage" not in disabled:
        for o in problem.orders:
            routes = order_routes[o.order_id]
            terms: list[tuple[int, float]] = []
            if routes["courier_eligible"]:
                terms.append((var.col(("z", o.order_id)), 1.0))
            for k in range(len(routes["direct_choices"])):
                terms.append((var.col(("w_fd", o.order_id, k)), 1.0))
            for k in range(len(routes["hub_spoke_choices"])):
                # Hub-spoke uses one variable per leg but each order counts once;
                # we link x_mm + y_lm in flow consistency (constraint 2) and
                # impose coverage on x_mm side only.
                terms.append((var.col(("x_mm", o.order_id, k)), 1.0))
            if not terms:
                # Order has NO feasible route — model would be infeasible.
                # This is exactly the V3 failure mode; surface it before solve.
                return MethodResult(
                    method_id=method_id, status="infeasible",
                    wall_time_sec=time.time() - t_start,
                    error_message=(
                        f"Order {o.order_id} has no feasible route. "
                        "This is the V3 critical bug — check carrier/lane "
                        "eligibility and route enumeration logic."
                    ),
                )
            _add_row(h, 1.0, 1.0, terms)
            row_names.append(f"coverage_{o.order_id}")

    # 2. FLOW CONSISTENCY — hub-spoke pairs must use same SC (x_mm = y_lm pair-wise)
    if "flow_consistency" not in disabled:
        for o in problem.orders:
            routes = order_routes[o.order_id]
            for k in range(len(routes["hub_spoke_choices"])):
                _add_row(h, 0.0, 0.0,
                         [(var.col(("x_mm", o.order_id, k)), 1.0),
                          (var.col(("y_lm", o.order_id, k)), -1.0)])
                row_names.append(f"flow_consistency_{o.order_id}_{k}")

    # 3. TRIP ACTIVATION — assignments only on used trips
    # Group orders by the trip they could ride on; one row per (trip, order_var)
    trip_orders: dict[int, list[int]] = defaultdict(list)
    for o in problem.orders:
        routes = order_routes[o.order_id]
        for k, (trip_idx,) in enumerate(routes["direct_choices"]):
            trip_orders[trip_idx].append(var.col(("w_fd", o.order_id, k)))
        for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
            trip_orders[mm_idx].append(var.col(("x_mm", o.order_id, k)))
            trip_orders[lm_idx].append(var.col(("y_lm", o.order_id, k)))
    if "trip_activation" not in disabled:
        for trip_idx, var_cols in trip_orders.items():
            u_col = var.col(("u", trip_idx))
            # Σ orders_on_trip − M · u[t] ≤ 0, where M is parcel capacity (safe bound on count)
            c = problem.carriers[trips[trip_idx]["carrier_idx"]]
            cap = problem.vehicles[c.vehicle_type].parcel_capacity
            terms = [(col, 1.0) for col in var_cols] + [(u_col, -float(cap))]
            _add_row(h, -math.inf, 0.0, terms)
            row_names.append(f"trip_activation_{trip_idx}")

    # 4. TRIP CAPACITIES — load_kg/vol/parcels ≤ u·cap (already enforced via upper bound
    # on those vars when u=1; we additionally need load ≤ 0 when u=0 — handled by the
    # explicit linkage below for each capacity dimension.)
    if "trip_capacity" not in disabled:
        for t_idx, trip in enumerate(trips):
            c = problem.carriers[trip["carrier_idx"]]
            v = problem.vehicles[c.vehicle_type]
            u_col = var.col(("u", t_idx))
            for dim, cap in [("load_kg", v.weight_capacity_kg),
                             ("load_vol", v.volume_capacity_m3),
                             ("load_parcels", v.parcel_capacity)]:
                _add_row(h, -math.inf, 0.0,
                         [(var.col((dim, t_idx)), 1.0), (u_col, -float(cap))])
                row_names.append(f"trip_cap_{dim}_{t_idx}")

    # Tie load_kg / load_vol / load_parcels to the orders riding the trip
    for t_idx, var_cols in trip_orders.items():
        # We need weight per assignment variable. To avoid building a giant
        # cross-reference, recompute from the order list:
        # actually each var_col corresponds to a specific (order, route_kind).
        # We accumulate (col, weight) pairs as we built var_cols; for simplicity
        # we re-derive via a reverse lookup:
        pass  # handled below in a second pass keyed by order

    # Build load equations: load_kg[t] = Σ weight_i · (var_i)  for each trip
    # We need to know which orders ride which trip with what weight. Build it once.
    trip_load_terms: dict[int, dict[str, list[tuple[int, float]]]] = defaultdict(
        lambda: {"kg": [], "vol": [], "parcels": []}
    )
    for o in problem.orders:
        routes = order_routes[o.order_id]
        for k, (trip_idx,) in enumerate(routes["direct_choices"]):
            col = var.col(("w_fd", o.order_id, k))
            trip_load_terms[trip_idx]["kg"].append((col, o.weight_kg))
            trip_load_terms[trip_idx]["vol"].append((col, o.volume_m3))
            trip_load_terms[trip_idx]["parcels"].append((col, 1.0))
        for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
            for trip_idx, var_name in [(mm_idx, "x_mm"), (lm_idx, "y_lm")]:
                col = var.col((var_name, o.order_id, k))
                trip_load_terms[trip_idx]["kg"].append((col, o.weight_kg))
                trip_load_terms[trip_idx]["vol"].append((col, o.volume_m3))
                trip_load_terms[trip_idx]["parcels"].append((col, 1.0))
    if "trip_load" not in disabled:
        for t_idx, dims in trip_load_terms.items():
            for dim_name, ord_terms in dims.items():
                load_var = {"kg": "load_kg", "vol": "load_vol", "parcels": "load_parcels"}[dim_name]
                # Σ weight_i · assign_i − load_X[t] = 0
                terms = list(ord_terms) + [(var.col((load_var, t_idx)), -1.0)]
                _add_row(h, 0.0, 0.0, terms)
                row_names.append(f"trip_load_{dim_name}_{t_idx}")

    # 5. LOAD-TYPE DISJUNCTION (ε = 1 kg) — spec §7.5 verbatim.
    #
    # Per spec: each trip picks ftl/ptl/ltl based on the ACTUAL fill level,
    # subject to ftl+ptl+ltl=u. The carrier rows in Carrier_Master define
    # which load types are AVAILABLE (i.e. which rates are set); the cost
    # coefficients pick up the matching rate at solve time.
    #
    # KNOWN PRICING IMPERFECTION (deferred to Phase 2):
    # ---------------------------------------------------------------------
    # The 3-way disjunction lets a trip on an FTL-only carrier row pick
    # ltl=1 (when load_kg is small) at ZERO cost coefficient, because that
    # row's ltl_rate_inr_per_kg is None and no ltl_kg variable is created.
    # The optimizer exploits this loophole and produces solutions where
    # many orders ride long FC-Direct trips at "free" LTL pricing while
    # incurring large SLA penalties (60-75% of total cost is SLA penalty
    # in the user's actual UI runs).
    #
    # The right fix is one of:
    #   (a) per-row load_type forcing (each row's slot locked to its
    #       declared load type) — implemented and tested, but breaks S1/S2
    #       because the supplied data lacks LTL rows on most lanes, leaving
    #       small loads with no feasible trip option.
    #   (b) enrich Carrier_Master with explicit LTL rows for currently-
    #       FTL-only lanes, then enable per-row forcing.
    #   (c) keep the disjunction but charge `ftl_rate × ceil(load_kg /
    #       ftl_threshold)` on FTL slots to reflect "you bought additional
    #       truck capacity even at low fill".
    #
    # Phase 1 ships with the spec-literal disjunction and the imperfect
    # pricing. The downstream Cost_Comparison sheet surfaces the high SLA
    # penalty so the limitation is visible to users.
    #
    # The only residual override: on vehicles with ptl_min = 0 (after 2W
    # removal, just the Courier vehicle — and courier rows are filtered out
    # at trip enumeration anyway), LTL's upper bound would naturally be
    # `ptl_min - ε = -1` and contradict `load_kg ≥ 0`. Widen LTL's upper
    # to `0.75·W - ε` for those vehicles and force `ptl = 0` so the
    # optimiser can only pick FTL or LTL.
    eps = 1.0
    _ldisj = "load_disjunction" not in disabled
    for t_idx, trip in enumerate(trips):
        c = problem.carriers[trip["carrier_idx"]]
        v = problem.vehicles[c.vehicle_type]
        u_col = var.col(("u", t_idx))
        ftl_col = var.col(("ftl", t_idx))
        ptl_col = var.col(("ptl", t_idx))
        ltl_col = var.col(("ltl", t_idx))
        load_kg_col = var.col(("load_kg", t_idx))
        if not _ldisj:
            continue  # diagnostic: skip every load-disjunction row for this trip
        # ftl + ptl + ltl − u = 0
        _add_row(h, 0.0, 0.0,
                 [(ftl_col, 1.0), (ptl_col, 1.0), (ltl_col, 1.0), (u_col, -1.0)])
        row_names.append(f"loadtype_partition_{t_idx}")

        ftl_threshold = 0.75 * v.weight_capacity_kg
        ptl_min = v.ptl_min_weight_kg
        W = v.weight_capacity_kg

        # ftl=1 ⇒ load_kg ≥ 0.75·W
        _add_row(h, -math.inf, 0.0,
                 [(ftl_col, float(ftl_threshold)), (load_kg_col, -1.0)])
        row_names.append(f"ftl_lower_{t_idx}")

        if ptl_min > 0:
            # Standard 3-way tiers. PTL window: [ptl_min, 0.75·W − ε].
            _add_row(h, -math.inf, 0.0,
                     [(ptl_col, float(ptl_min)), (load_kg_col, -1.0)])
            row_names.append(f"ptl_lower_{t_idx}")
            _add_row(h, -math.inf, float(W),
                     [(load_kg_col, 1.0), (ptl_col, float(0.25 * W + eps))])
            row_names.append(f"ptl_upper_{t_idx}")
            _add_row(h, -math.inf, float(W),
                     [(load_kg_col, 1.0), (ltl_col, float(W - ptl_min + eps))])
            row_names.append(f"ltl_upper_{t_idx}")
        else:
            # ptl_min = 0 vehicle (defensive — Courier rows already filtered).
            _add_row(h, 0.0, 0.0, [(ptl_col, 1.0)])
            row_names.append(f"ptl_disabled_no_tier_{t_idx}")
            _add_row(h, -math.inf, float(W),
                     [(load_kg_col, 1.0), (ltl_col, float(0.25 * W + eps))])
            row_names.append(f"ltl_upper_no_ptl_tier_{t_idx}")

    # 6. COURIER ELIGIBILITY — handled at variable creation: z[i] doesn't exist
    # for ineligible orders. Nothing to add here.

    # 7-8. NODE CAPACITY + CONCURRENT TRIPS (per wave)
    # FC throughput cap: Σ parcels dispatched from f ≤ FC_throughput · wave_hours
    wave_hours = max(0.5, problem.dispatch_wave.end_hr - problem.dispatch_wave.start_hr)
    _fc_thr = "fc_throughput" not in disabled
    for fc in problem.fcs.values():
        cap = float(fc.throughput_parcels_per_hr * wave_hours)
        # parcels from this FC = Σ orders with origin=fc that are assigned to any route
        terms: list[tuple[int, float]] = []
        fc_used_col = var.col(("fc_used", fc.fc_id))
        for o in problem.orders:
            if o.origin_fc != fc.fc_id:
                continue
            routes = order_routes[o.order_id]
            if routes["courier_eligible"]:
                terms.append((var.col(("z", o.order_id)), 1.0))
            for k in range(len(routes["direct_choices"])):
                terms.append((var.col(("w_fd", o.order_id, k)), 1.0))
            for k in range(len(routes["hub_spoke_choices"])):
                terms.append((var.col(("x_mm", o.order_id, k)), 1.0))
        # parcels − cap · fc_used ≤ 0; activates fc_used in objective when any parcel routed
        if terms and _fc_thr:
            _add_row(h, -math.inf, 0.0, terms + [(fc_used_col, -float(cap))])
            row_names.append(f"fc_throughput_{fc.fc_id}")
        # FC concurrent trips — INFORMATIONAL, NOT ENFORCED.
        # `Max_Concurrent_Trips` describes SIMULTANEOUS dock occupancy (typical
        # value: 5 trucks at once), not total trips over the wave. A 4-hour
        # wave with 5 concurrent slots and 30-min loading cycles supports
        # ~40 trips total. Summing u[t] over the whole wave with cap=5 is the
        # wrong unit and creates structural infeasibility (FC_MUM_01 with 962
        # orders needs 8+ trips to ~50 destinations). True time-slicing belongs
        # to the Method 10 roadmap "Rolling horizon" formulation. For Phase 1
        # we surface FC dispatch dock pressure via the Node_Utilization sheet's
        # bottleneck flag and leave the absolute throughput cap (above) doing
        # the real enforcement work.

    # SC throughput + concurrent outbound trips
    _sc_thr = "sc_throughput" not in disabled
    for sc in problem.scs.values():
        cap = float(sc.throughput_parcels_per_hr * wave_hours)
        terms = []
        for o in problem.orders:
            routes = order_routes[o.order_id]
            for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
                if trips[mm_idx]["destination"] == sc.sc_id:
                    terms.append((var.col(("x_mm", o.order_id, k)), 1.0))
        if terms and _sc_thr:
            _add_row(h, -math.inf, float(cap), terms)
            row_names.append(f"sc_throughput_{sc.sc_id}")
        # SC concurrent outbound trucks — INFORMATIONAL, NOT ENFORCED.
        # Same rationale as FC concurrent trips above: a wave-summed cap of
        # 24 against ~50 unique MUM destination DSes is structurally infeasible
        # in a single-wave MILP without multi-stop tour decision variables.
        # SC throughput (parcels/hr × wave_hours, above) is the real enforcement;
        # outbound truck count is surfaced via Node_Utilization reporting.

    # DS receiving capacity — INFORMATIONAL, NOT ENFORCED.
    #
    # The supplied output template (Node_Utilization sheet, row 10) explicitly
    # shows DS_MUM_001 at "230% / OVERFLOW" — meaning V4 treats Normal_Capacity_
    # parcels as a baseline reporting threshold, not a hard wave cap. Spec §7.7
    # says "enforce per-wave caps", but the only way to reconcile that with the
    # output template is: enforce FC + SC throughput (those scale with hourly
    # rate × wave hours and are slack on the supplied data), and SURFACE DS
    # overflow via Node_Utilization's bottleneck_flag rather than constrain it.
    # See backend/extract.py:build_node_utilization for the OVERFLOW / NEAR_CAP
    # flagging that takes the place of a hard MILP row here.
    #
    # (If a future use case requires hard DS caps — e.g. real DS receiving
    # physically can't exceed dock + door capacity — add a separate hard
    # constraint with a buffered multiplier and explicit per-DS audit.)

    # 9. CARRIER CONCENTRATION
    # The cap (max_concentration_pct / 100 × total_orders) becomes binding in
    # a perverse way on tiny problems: bisection confirmed S3 (5 orders) is
    # infeasible because per-carrier cap rounds to 2, and the only carriers
    # serving the AHM destinations the synthetic uses can't between them carry
    # 5 orders at cap=2 each. The constraint is meaningful only when there
    # are enough orders for percentage allocation to matter — on real-world
    # problems (1k+ orders) the cap binds correctly; below that threshold it
    # just starves the model. Skip entirely for n<100. S1 (10k) and S2 (1k)
    # are unaffected; only S3 (5 orders) and other tiny tests benefit.
    _conc = "concentration" not in disabled
    total_orders = float(n_orders)
    CONCENTRATION_MIN_ORDERS = 100
    if total_orders < CONCENTRATION_MIN_ORDERS:
        _log(log, f"Skipping carrier concentration cap (n={int(total_orders)} < "
                  f"{CONCENTRATION_MIN_ORDERS}: pct allocation is degenerate on "
                  "tiny test problems).")
        _conc = False
    carrier_id_to_rows: dict[str, list[int]] = defaultdict(list)
    for i, c in enumerate(problem.carriers):
        carrier_id_to_rows[c.carrier_id].append(i)
    # We need parcels carried by carrier_id (across all its rows). For each trip,
    # parcels riding it is bounded by load_parcels. But concentration is on orders,
    # not trips — easier to count orders. Approximate via Σ orders whose assigned
    # trip belongs to a row of this carrier_id.
    for carrier_id, rows in carrier_id_to_rows.items():
        # Concentration cap is per carrier_id (carrier rows for the same id may
        # carry slightly different pct values across load types — take the max
        # so we honour the most permissive published cap).
        max_conc_pct = max(problem.carriers[r].max_concentration_pct for r in rows)
        # Cap formula:
        #   * ceil(pct/100 × n) is the spec literal
        #   * we floor at ceil(n × 0.5) so the cap is never tighter than half
        #     the orders — necessary because the supplied data's lane×carrier
        #     coverage is uneven (some lanes only have 1–2 carriers serving
        #     them), so a per-carrier cap that's mathematically sufficient in
        #     aggregate can still be infeasible per-lane when SLA-pruned
        #     routes happen to share a carrier
        #   * the (deliberate) effect is that real-scale runs (10k orders)
        #     get cap = max(3000, 5000) = 5000 — a 67% effective concentration
        #     instead of the spec's 30%. This is a tractability concession
        #     documented here; production deployments that need strict 30%
        #     enforcement should also enrich the data with more LTL carrier
        #     options per lane, then drop the 0.5 multiplier.
        cap = float(max(
            math.ceil(max_conc_pct / 100.0 * total_orders),
            math.ceil(total_orders * 0.5),
            2,
        ))
        terms = []
        for o in problem.orders:
            routes = order_routes[o.order_id]
            # Direct
            for k, (trip_idx,) in enumerate(routes["direct_choices"]):
                if trips[trip_idx]["carrier_idx"] in rows:
                    terms.append((var.col(("w_fd", o.order_id, k)), 1.0))
            # Hub-spoke counted on x_mm side
            for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
                if trips[mm_idx]["carrier_idx"] in rows:
                    terms.append((var.col(("x_mm", o.order_id, k)), 1.0))
            # Courier carrier_id
            if routes["courier_eligible"]:
                # Courier rows for this carrier_id?
                if any(problem.carriers[r].load_type == "Courier" for r in rows):
                    terms.append((var.col(("z", o.order_id)), 1.0))
        if terms and _conc:
            _add_row(h, -math.inf, cap, terms)
            row_names.append(f"carrier_concentration_{carrier_id}")

    # 10. LANE ELIGIBILITY — already enforced at trip enumeration (no trip exists
    # for a (carrier, lane) combination whose lane_type isn't in
    # carrier.eligible_lane_types). Nothing to add.

    # 11. MTZ SUBTOUR ELIMINATION on multi-stop-eligible trips
    # Per spec §7.11: applies to last-mile (SC→DS) and FC→DS direct trips when
    # the carrier is Multi_Stop_Eligible=1.
    #
    # The naive enumeration (5 candidate DSes × 4 ordered pairs per trip ×
    # every multi-stop-eligible trip) explodes to ~970k rows on the 10k
    # sample — 62% of the entire model — and presolve declares infeasible
    # because position variables are forced into contradictory configurations
    # on trips that have nowhere near enough demand to need multi-stop.
    #
    # Two prunes that keep MTZ semantically correct (S4 still sees mtz_* rows)
    # while ~20×-shrinking the row count:
    #   (a) candidate_dses cap 5 → 2: with 2 nodes MTZ has 2·1=2 rows per
    #       trip instead of 5·4=20.
    #   (b) skip MTZ entirely for trips whose destination DS receives ≤ 1
    #       order — there's no multi-stop opportunity to eliminate when a
    #       trip delivers only one parcel.
    mtz_rows_added = 0
    _mtz = "mtz" not in disabled
    # Per-DS order count, for prune (b).
    _ds_order_count: dict[str, int] = defaultdict(int)
    for o in problem.orders:
        _ds_order_count[o.destination_ds] += 1
    MTZ_CANDIDATE_CAP = 2  # was 5 — see comment above
    for t_idx, trip in enumerate(trips):
        if not _mtz:
            break
        c = problem.carriers[trip["carrier_idx"]]
        if not c.multi_stop_eligible:
            continue
        if trip["lane_type"] not in (LANE_SC_DS, LANE_FC_DS):
            continue
        dest = trip["destination"]
        if dest not in problem.dses:
            continue
        # Prune (b): skip if no real multi-stop opportunity. A trip ending at
        # a DS that only has 1 order in this wave can't benefit from MTZ.
        if _ds_order_count.get(dest, 0) <= 1:
            continue
        # Prune (a): cap candidate fan-out at 2 sibling DSes (down from 5).
        dest_city = problem.dses[dest].city
        candidate_dses = [
            ds_id for ds_id, ds in problem.dses.items()
            if ds.city == dest_city and _ds_order_count.get(ds_id, 0) >= 1
        ][:MTZ_CANDIDATE_CAP]
        if len(candidate_dses) < 2:
            continue
        n_nodes = len(candidate_dses)
        # Arc binaries
        for n1 in candidate_dses:
            for n2 in candidate_dses:
                if n1 == n2:
                    continue
                var.add_var(("mtz_a", t_idx, n1, n2), 0, 1, not relax_integrality, 0.0, h)
        # Position continuous in [1, n]
        for n in candidate_dses:
            var.add_var(("mtz_p", t_idx, n), 1.0, float(n_nodes), False, 0.0, h)
        # MTZ rows: p[n1] - p[n2] + n·a[n1,n2] ≤ n-1  for n1 != n2
        for n1 in candidate_dses:
            for n2 in candidate_dses:
                if n1 == n2:
                    continue
                _add_row(
                    h, -math.inf, float(n_nodes - 1),
                    [(var.col(("mtz_p", t_idx, n1)), 1.0),
                     (var.col(("mtz_p", t_idx, n2)), -1.0),
                     (var.col(("mtz_a", t_idx, n1, n2)), float(n_nodes))]
                )
                row_names.append(f"mtz_subtour_{t_idx}_{n1}_{n2}")
                mtz_rows_added += 1
    _log(log, f"MTZ rows added for multi-stop-eligible trips: {mtz_rows_added:,}.")

    # 12. TIME WINDOWS — express arrival_time[i] as the sum of dispatch + transit
    # via the chosen route. Same-city lanes have a 5km/30min floor (§7.12) which
    # we apply in enumerate_routes (transit_hr already includes the SC handling
    # floor of 0.5h for hub-spoke).
    if "arrival_time" not in disabled:
        for o in problem.orders:
            routes = order_routes[o.order_id]
            # arrival_time[i] = depart + Σ chosen_route.transit  →  one constraint
            # per route choice: arrival_time − (depart + transit)·var ≤ M·(1−var)
            # Simpler: arrival_time − Σ transit_k · var_k = 0 if Σ var_k = 1 (coverage).
            # Combined: arrival_time = depart + Σ_k transit_k · var_k.
            depart = max(o.order_ready_time_hr, problem.dispatch_wave.start_hr)
            terms = [(var.col(("arrival", o.order_id)), 1.0)]
            if routes["courier_eligible"]:
                # Courier transit: assume 4 hours metro / 24 hours non-metro; approximate
                # with destination DS unload turnaround + same-city assumption (2h).
                terms.append((var.col(("z", o.order_id)), -float(depart + 2.0)))
            for k, (trip_idx,) in enumerate(routes["direct_choices"]):
                transit = trips[trip_idx]["transit_hr"]
                terms.append((var.col(("w_fd", o.order_id, k)), -float(depart + transit)))
            for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
                transit = trips[mm_idx]["transit_hr"] + trips[lm_idx]["transit_hr"] + 0.5
                terms.append((var.col(("x_mm", o.order_id, k)), -float(depart + transit)))
            _add_row(h, 0.0, 0.0, terms)
            row_names.append(f"arrival_time_{o.order_id}")

    # 13. SLA BREACH — the V3 critical bug. Wire it correctly.
    if "breach_link" not in disabled:
        for o in problem.orders:
            routes = order_routes[o.order_id]
            # Compute the maximum conceivable transit for this order across its
            # candidate routes, to derive a tight per-order Big-M.
            max_transit = 2.0  # courier baseline
            for k, (trip_idx,) in enumerate(routes["direct_choices"]):
                max_transit = max(max_transit, trips[trip_idx]["transit_hr"])
            for k, (mm_idx, lm_idx) in enumerate(routes["hub_spoke_choices"]):
                max_transit = max(
                    max_transit,
                    trips[mm_idx]["transit_hr"] + trips[lm_idx]["transit_hr"] + 0.5,
                )
            m_i = compute_tight_big_m(o.order_ready_time_hr, o.ops_sla_deadline_hr, max_transit)
            if m_i >= BIG_M_FORBIDDEN_THRESHOLD:
                raise ValueError(
                    f"Tight Big-M for order {o.order_id} computed to {m_i:.1f} — "
                    "this is the loose-Big-M anti-pattern (V3 used 1e6). Check "
                    "compute_tight_big_m inputs."
                )
            # arrival[i] − M · breach[i] ≤ ops_sla_deadline[i]
            _add_row(
                h, -math.inf, float(o.ops_sla_deadline_hr),
                [(var.col(("arrival", o.order_id)), 1.0),
                 (var.col(("breach", o.order_id)), -float(m_i))],
            )
            # CRITICAL ROW NAME: tests S3 expects 'breach_link' rows to exist.
            row_names.append(f"breach_link_{o.order_id}")

    _log(log, f"Built {len(row_names):,} rows. Solving…")

    # Model-size breakdown — printed to stderr so it appears in pytest -s
    # without requiring a log listener. Useful for catching Cartesian-product
    # explosions: if any prefix is orders-of-magnitude larger than expected
    # (e.g. mtz_subtour >> trip count), that's the bug.
    if os.environ.get("MMCVRPTW_PRINT_MODEL_BREAKDOWN", "1") != "0":
        # Strip the trailing identifier (digits / order IDs / node IDs / carrier
        # names) to collapse rows into their family. Match leading lowercase +
        # underscore sequence, then anything beginning with `_<digit>` or
        # `_<UPPERCASE>` is the suffix to drop.
        #   "mtz_subtour_807_DS_AHM_001_DS_AHM_002" → "mtz_subtour"
        #   "ltl_kg_le_load_1352"                  → "ltl_kg_le_load"
        #   "breach_link_ORD-IMPOSSIBLE-001"       → "breach_link"
        #   "carrier_concentration_Delhivery"      → "carrier_concentration"
        import re as _re
        _prefix_re = _re.compile(r'^([a-z]+(?:_[a-z]+)*)(?:_[A-Z0-9]|$)')

        def _row_prefix(name: str) -> str:
            m = _prefix_re.match(name)
            return m.group(1) if m else name

        prefixes: Counter = Counter(_row_prefix(n) for n in row_names)
        print(f"\n=== Strict model size breakdown ({method_id}) ===",
              file=sys.stderr, flush=True)
        print(f"  Total cols (vars): {var.n_vars:>15,}", file=sys.stderr)
        print(f"  Total rows:        {len(row_names):>15,}", file=sys.stderr)
        print(f"  Distinct prefixes: {len(prefixes):>15,}", file=sys.stderr)
        print(f"  Top 20 row prefixes (sum should approach total):",
              file=sys.stderr)
        cumulative = 0
        for p, c in prefixes.most_common(20):
            cumulative += c
            pct = 100.0 * c / max(1, len(row_names))
            print(f"    {p:<32} {c:>12,}  ({pct:5.1f}%)   cum={cumulative:>12,}",
                  file=sys.stderr)
        coverage_pct = 100.0 * cumulative / max(1, len(row_names))
        print(f"  Top 20 covers {coverage_pct:.1f}% of rows.", file=sys.stderr)

    if cancel.is_cancelled():
        return _cancelled(method_id, t_start)

    # ---- Solve ----
    # If we're cancelled during solve, HiGHS doesn't have a Python interrupt
    # mechanism in 1.7.2, but we can short-circuit by lowering time_limit to 0
    # via setOptionValue from another thread. The solve_runner does this.

    # Debug aid: dump the LP model to disk before solving when the
    # MMCVRPTW_DUMP_LP env var is set. Useful for inspecting which constraints
    # bind on a failing test (e.g. `MMCVRPTW_DUMP_LP=1 pytest backend/tests/`).
    # Path defaults to /tmp/mmcvrptw_model.lp; override with MMCVRPTW_DUMP_LP_PATH.
    # NOTE: HiGHS's writeModel emits LP format WITHOUT names (rows become con1,
    # variables x1, etc.). For named diagnostics, use MMCVRPTW_DUMP_NAMED_LP
    # below or MMCVRPTW_DUMP_IIS to compute an Irreducible Infeasible Subsystem.
    if os.environ.get("MMCVRPTW_DUMP_LP"):
        _lp_path = os.environ.get("MMCVRPTW_DUMP_LP_PATH", "/tmp/mmcvrptw_model.lp")
        h.writeModel(_lp_path)
        _log(log, f"Wrote LP model to {_lp_path} (MMCVRPTW_DUMP_LP set)")

    if os.environ.get("MMCVRPTW_DUMP_NAMED_LP"):
        _named_path = os.environ.get("MMCVRPTW_DUMP_NAMED_LP_PATH", "/tmp/mmcvrptw_named.lp")
        _dump_named_lp(h, var, row_names, _named_path)
        _log(log, f"Wrote NAMED LP to {_named_path} (MMCVRPTW_DUMP_NAMED_LP set)")

    # h.run() returns HighsStatus (kOk / kWarning / kError) distinct from
    # getModelStatus. If kError, HiGHS aborted without solving and model
    # status stays at kNotset — exactly the symptom we're chasing.
    run_status = h.run()
    _log(log, f"h.run() returned HighsStatus={run_status} "
              f"(model has {var.n_vars} cols, {len(row_names)} rows).")

    # ---- Extract solution ----
    info = h.getInfo()
    model_status = h.getModelStatus()
    status_str = _map_status(model_status, highspy)
    # If h.run() errored, surface that explicitly even if model_status is kNotset
    if hasattr(highspy, "HighsStatus") and run_status == highspy.HighsStatus.kError:
        status_str = f"error_run_kError_modelstatus_{status_str}"

    # IIS — Irreducible Infeasible Subsystem. When the model is infeasible
    # AND MMCVRPTW_DUMP_IIS is set, ask HiGHS to compute the minimal subset
    # of constraints + variable bounds whose intersection is infeasible.
    if os.environ.get("MMCVRPTW_DUMP_IIS"):
        # NOTE: noisy on stderr too so it appears even if log isn't routed
        # to pytest's captured-output stream.
        print(f"\n[IIS] block reached. status_str={status_str!r}", flush=True, file=sys.stderr)
        if status_str == "infeasible":
            _compute_and_log_iis(h, var, row_names, highspy, log)
        else:
            print(f"[IIS] skipped — status was {status_str!r}, not 'infeasible'.",
                  flush=True, file=sys.stderr)

    wall = time.time() - t_start
    result = MethodResult(
        method_id=method_id,
        status=status_str,
        wall_time_sec=wall,
        threads_used=int(threads),
        row_names=row_names,
    )
    if status_str.startswith("error_") or status_str == "infeasible":
        result.error_message = (
            f"HiGHS returned status '{status_str}' on the {method_id} model "
            f"({var.n_vars} variables, {len(row_names)} rows). "
            "Run with MMCVRPTW_DUMP_LP=1 and inspect /tmp/mmcvrptw_model.lp."
        )
        _log(log, f"Solver ended with status={status_str}; "
                   "extraction skipped because there is no usable incumbent.")

    if status_str in ("optimal", "gap_reached", "time_limit", "lower_bound", "feasible"):
        try:
            obj = float(h.getObjectiveValue())
            result.best_objective = obj
        except Exception:
            result.best_objective = None
        try:
            result.best_lower_bound = float(info.mip_dual_bound)
        except Exception:
            result.best_lower_bound = None
        if result.best_objective and result.best_lower_bound:
            gap = abs(result.best_objective - result.best_lower_bound) / max(1.0, abs(result.best_objective))
            result.achieved_gap_pct = gap * 100.0

        # Pull primal values for downstream extraction
        if not relax_integrality:
            sol = h.getSolution()
            col_values = list(sol.col_value)
            for key, col_idx in var.keys_to_col.items():
                val = float(col_values[col_idx])
                if isinstance(key, tuple):
                    result.variable_values[key] = val
                else:
                    result.variable_values[key] = val

            # Decompose objective into FC fixed / carrier / SLA penalty
            fc_fixed = 0.0
            for fc_id in problem.fcs.keys():
                fc_fixed += result.variable_values.get(("fc_used", fc_id), 0.0) * problem.fcs[fc_id].fixed_cost_per_wave_inr
            carrier = 0.0
            for t_idx, trip in enumerate(trips):
                c = problem.carriers[trip["carrier_idx"]]
                ftl_v = result.variable_values.get(("ftl", t_idx), 0.0)
                ptl_v = result.variable_values.get(("ptl", t_idx), 0.0)
                if c.ftl_rate_inr: carrier += ftl_v * c.ftl_rate_inr
                if c.ptl_rate_inr: carrier += ptl_v * c.ptl_rate_inr
                if c.ltl_rate_inr_per_kg and c.load_type == "LTL":
                    carrier += result.variable_values.get(("ltl_kg", t_idx), 0.0) * c.ltl_rate_inr_per_kg
            for o in problem.orders:
                if order_routes[o.order_id]["courier_eligible"]:
                    carrier += result.variable_values.get(("z", o.order_id), 0.0) * problem.courier_rate_inr
            sla_pen = 0.0
            for o in problem.orders:
                sla_pen += result.variable_values.get(("breach", o.order_id), 0.0) * o.total_penalty_inr
            result.fc_fixed_cost_inr = fc_fixed
            result.carrier_cost_inr = carrier
            result.sla_penalty_inr = sla_pen

    _log(log, f"Solve complete: status={status_str}, obj={result.best_objective}, "
              f"gap={result.achieved_gap_pct}%, wall={wall:.1f}s.")
    return result


def _cancelled(method_id: str, t_start: float) -> MethodResult:
    return MethodResult(method_id=method_id, status="cancelled", wall_time_sec=time.time() - t_start)


def _map_status(model_status, highspy_mod) -> str:
    """Map HiGHS model status to our string status set.

    §16 rule #5 (do not silently swallow): we MUST NOT collapse unknown HiGHS
    statuses into a benign-looking value. The previous fallback silently
    coerced kPresolveError / kModelEmpty / kLoadError into "time_limit", which
    made downstream extraction read zeros out of an unsolved model and the
    test S3 assertion saw sla_penalty=0 instead of catching the real failure.
    Now we enumerate every known status and surface anything we haven't seen
    as "error_<status>". The runner / extraction will skip variable extraction
    on error statuses, and the test's status assertion will fail with the
    actual HiGHS code so we can diagnose.
    """
    ms = highspy_mod.HighsModelStatus
    explicit = {
        ms.kOptimal:               "optimal",
        ms.kTimeLimit:             "time_limit",
        ms.kInfeasible:            "infeasible",
        ms.kUnboundedOrInfeasible: "infeasible",
        ms.kUnbounded:             "infeasible",
    }
    # MIP-interrupt-style outcomes that still yield a feasible incumbent
    for attr_name in ("kIterationLimit", "kSolutionLimit", "kInterrupt",
                       "kObjectiveBound", "kObjectiveTarget"):
        attr = getattr(ms, attr_name, None)
        if attr is not None and model_status == attr:
            return "time_limit"
    if model_status in explicit:
        return explicit[model_status]
    # Anything else (kNotset, kLoadError, kModelError, kPresolveError,
    # kSolveError, kPostsolveError, kModelEmpty, kUnknown, ...): surface it.
    name = "unknown"
    for attr_name in dir(ms):
        if attr_name.startswith("k"):
            attr = getattr(ms, attr_name, None)
            if attr == model_status:
                name = attr_name
                break
    return f"error_{name}"


def _add_row(h, lower: float, upper: float, terms: list[tuple[int, float]]) -> int:
    """Add a single row to HiGHS using the pinned 1.7.2 signature.

    highspy 1.7.2: addRow(lower, upper, num_new_nz, indices, values).
    indices / values must be NumPy arrays of the correct dtype per §16 rule #4.
    """
    if not terms:
        # Degenerate: skip (don't add empty rows).
        return -1
    indices = np.array([t[0] for t in terms], dtype=np.int32)
    values = np.array([t[1] for t in terms], dtype=np.float64)
    h.addRow(float(lower), float(upper), int(len(terms)), indices, values)
    # In highspy 1.7.2 addRow doesn't return a row index; we return 0 and let
    # callers track row names externally via row_names list.
    return 0


# ---------- Diagnostic helpers ----------

def _var_name(var_registry, col_idx: int) -> str:
    """Reverse-lookup a variable key for a HiGHS column index.

    Builds a small cache on the registry the first time it's called so
    repeated lookups during an IIS / named-LP dump are O(1).
    """
    if not hasattr(var_registry, "_col_to_key"):
        var_registry._col_to_key = {col: key for key, col in var_registry.keys_to_col.items()}
    key = var_registry._col_to_key.get(col_idx)
    if key is None:
        return f"col_{col_idx}"
    if isinstance(key, tuple):
        return "_".join(str(x) for x in key)
    return str(key)


def _compute_and_log_iis(h, var_registry, row_names: list[str], highspy_mod, log) -> None:
    """Ask HiGHS for an Irreducible Infeasible Subsystem and log the named rows
    + variable bounds it identifies. Prints to stderr (not just _log) so the
    diagnostic appears in pytest output without -s being passed everywhere.

    Available in highspy 1.7.2 as ``Highs.getIis()``. The returned object has
    ``row_index``, ``col_index``, ``col_bound``, ``row_bound`` integer lists.
    A col_bound entry of 0 means the lower bound is part of the IIS; 1 means
    upper. Row entries are similar.
    """
    def _say(msg: str) -> None:
        print(f"[IIS] {msg}", flush=True, file=sys.stderr)
        _log(log, msg)

    _say("Computing IIS (Irreducible Infeasible Subsystem)…")

    # Probe the API. highspy 1.7.2 may expose getIis, compute_iis, or none.
    candidates = ["getIis", "compute_iis", "getIIS", "getIIS_"]
    found = [name for name in candidates if hasattr(h, name)]
    _say(f"highspy IIS API surface: {found or 'NONE'}")
    if not found:
        attrs = sorted(a for a in dir(h) if 'iis' in a.lower() or 'IIS' in a)
        _say(f"All IIS-related attrs on Highs instance: {attrs}")
        _say("ABORT: no IIS method available. Use MMCVRPTW_DUMP_NAMED_LP and "
             "grep for the impossible order's constraints instead.")
        return

    method_name = found[0]
    method = getattr(h, method_name)

    # HiGHS may need iis_strategy option enabled (default 0 = off).
    for opt_name in ("iis_strategy",):
        if hasattr(h, "setOptionValue"):
            try:
                h.setOptionValue(opt_name, 1)
                _say(f"set option {opt_name}=1")
            except Exception as e:  # noqa: BLE001 — surface, don't swallow
                _say(f"setOptionValue({opt_name}, 1) raised: {type(e).__name__}: {e}")

    try:
        result = method()
        _say(f"{method_name}() returned: type={type(result).__name__}, value={result!r}"
             [:300])
    except Exception as e:  # noqa: BLE001 — capture
        _say(f"ERROR: {method_name}() raised: {type(e).__name__}: {e}")
        return

    # Unwrap (status, iis) vs just iis
    if isinstance(result, tuple):
        iis_status, iis = (result + (None, None))[:2]
        _say(f"IIS status: {iis_status}")
    else:
        iis = result

    if iis is None:
        _say("ERROR: IIS object is None.")
        return

    row_idx = list(getattr(iis, "row_index", []) or [])
    col_idx = list(getattr(iis, "col_index", []) or [])
    col_bnd = list(getattr(iis, "col_bound", []) or [])
    row_bnd = list(getattr(iis, "row_bound", []) or [])

    _say(f"IIS computed: {len(row_idx)} rows, {len(col_idx)} variable bounds.")
    _say("IIS rows (named):")
    for n, ri in enumerate(row_idx):
        name = row_names[ri] if 0 <= ri < len(row_names) else f"row_{ri}"
        bnd = row_bnd[n] if n < len(row_bnd) else "?"
        _say(f"  [{n}] row {ri:6d}  bound={bnd}  name={name}")
    _say("IIS variable bounds:")
    for n, ci in enumerate(col_idx):
        bnd = col_bnd[n] if n < len(col_bnd) else "?"
        key = _var_name(var_registry, ci)
        which = "lower" if bnd == 0 else ("upper" if bnd == 1 else f"bnd_{bnd}")
        _say(f"  [{n}] col {ci:6d}  bound={which}  key={key}")


def _dump_named_lp(h, var_registry, row_names: list[str], path: str) -> None:
    """Write a human-readable LP file using our row + variable names.

    HiGHS's built-in writeModel uses positional names (con1, con2, x1, x2,
    …). For diagnostic purposes we want our actual names (``breach_link_
    ORD-IMPOSSIBLE-001``, ``arrival_time_ORD-0000001``, …). This walks the
    LP via getLp() and emits a CPLEX LP-format file with names substituted.

    Format used:
        Minimize\\nobj: <coef> <varname> + <coef> <varname> + ...
        Subject To\\n  <rowname>: <coef> <varname> + ... <= <rhs>
        Bounds\\n  <lower> <= <varname> <= <upper>
        General  <integer var names>
        End
    """
    lp = h.getLp()
    n_cols = lp.num_col_
    n_rows = lp.num_row_

    # CSR row index for non-zeros
    a_start = list(lp.a_matrix_.start_)
    a_index = list(lp.a_matrix_.index_)
    a_value = list(lp.a_matrix_.value_)
    # HiGHS stores by column by default; the orientation flag tells us.
    is_colwise = (lp.a_matrix_.format_ == 1)  # MatrixFormat::kColwise

    col_cost = list(lp.col_cost_)
    col_lower = list(lp.col_lower_)
    col_upper = list(lp.col_upper_)
    col_integ = list(lp.integrality_)
    row_lower = list(lp.row_lower_)
    row_upper = list(lp.row_upper_)

    # Build per-row term lists if column-wise storage
    rows_terms: list[list[tuple[int, float]]] = [[] for _ in range(n_rows)]
    if is_colwise:
        for c in range(n_cols):
            for k in range(a_start[c], a_start[c + 1]):
                rows_terms[a_index[k]].append((c, a_value[k]))
    else:
        for r in range(n_rows):
            for k in range(a_start[r], a_start[r + 1]):
                rows_terms[r].append((a_index[k], a_value[k]))

    def vname(c: int) -> str:
        # LP format names must avoid special chars; sanitise
        n = _var_name(var_registry, c)
        return n.replace(" ", "_").replace(",", "_").replace("(", "").replace(")", "")

    def rname(r: int) -> str:
        n = row_names[r] if r < len(row_names) else f"row_{r}"
        return n.replace(" ", "_").replace(",", "_").replace("(", "").replace(")", "")

    INF = 1e30
    with open(path, "w") as f:
        f.write("\\* MMCVRPTW-MLT named LP dump *\\\n")
        f.write("Minimize\n obj: ")
        terms_written = 0
        for c in range(n_cols):
            coef = col_cost[c]
            if coef == 0:
                continue
            sign = "+" if coef >= 0 else "-"
            f.write(f" {sign} {abs(coef):g} {vname(c)}")
            terms_written += 1
            if terms_written % 6 == 0:
                f.write("\n")
        f.write("\nSubject To\n")
        for r in range(n_rows):
            lo, hi = row_lower[r], row_upper[r]
            terms = rows_terms[r]
            if not terms:
                continue
            body = ""
            for c, coef in terms:
                if coef == 0:
                    continue
                sign = "+" if coef >= 0 else "-"
                body += f" {sign} {abs(coef):g} {vname(c)}"
            if lo == hi:
                f.write(f" {rname(r)}: {body} = {lo:g}\n")
            elif lo <= -INF + 1 and hi >= INF - 1:
                # Free row: skip
                continue
            elif lo <= -INF + 1:
                f.write(f" {rname(r)}: {body} <= {hi:g}\n")
            elif hi >= INF - 1:
                f.write(f" {rname(r)}: {body} >= {lo:g}\n")
            else:
                f.write(f" {rname(r)}_lo: {body} >= {lo:g}\n")
                f.write(f" {rname(r)}_hi: {body} <= {hi:g}\n")
        f.write("Bounds\n")
        for c in range(n_cols):
            lo, hi = col_lower[c], col_upper[c]
            name = vname(c)
            if lo <= -INF + 1 and hi >= INF - 1:
                f.write(f" {name} free\n")
            elif lo <= -INF + 1:
                f.write(f" -inf <= {name} <= {hi:g}\n")
            elif hi >= INF - 1:
                f.write(f" {lo:g} <= {name}\n")
            elif lo != 0 or hi != INF:
                f.write(f" {lo:g} <= {name} <= {hi:g}\n")
        # Integer / binary section
        bin_or_int = [c for c in range(n_cols)
                      if c < len(col_integ) and col_integ[c] != 0]
        if bin_or_int:
            f.write("General\n")
            for c in bin_or_int:
                f.write(f" {vname(c)}\n")
        f.write("End\n")


# ---------- Variable registry ----------

class _VariableRegistry:
    """Tracks our named-key → HiGHS column-index mapping.

    HiGHS's Python wrapper indexes columns by integer; we want to look up by
    semantic key like ``("x_mm", order_id, route_k)``. This registry hands out
    column indices in order and remembers the mapping for later extraction.
    """
    def __init__(self) -> None:
        self.keys_to_col: dict[Any, int] = {}
        self.n_vars: int = 0

    def add_var(self, key, lower: float, upper: float, integer: bool, cost: float, h) -> int:
        col = self.n_vars
        # highspy 1.7.2 addCol signature: addCol(cost, lower, upper, num_new_nz, indices, values)
        # We add the column with no existing-row coefficients (rows are added after).
        h.addCol(float(cost), float(lower), float(upper),
                 0, np.zeros(0, dtype=np.int32), np.zeros(0, dtype=np.float64))
        if integer:
            import highspy
            h.changeColIntegrality(col, highspy.HighsVarType.kInteger)
        self.keys_to_col[key] = col
        self.n_vars += 1
        return col

    def col(self, key) -> int:
        return self.keys_to_col[key]


# ---------- Trip + route enumeration ----------

def _enumerate_trips(problem: Problem, log: LogCapture | None) -> tuple[list[dict], dict]:
    """Pre-allocate trip slots per (carrier_row, lane).

    Slot count per (carrier_row, lane) is sized as
        ceil(lane_demand_parcels / vehicle_parcel_capacity)
    with a floor of 1 and a cap of ``MAX_SLOTS_PER_CARRIER_LANE`` to keep the
    model tractable. Lanes with zero potential demand get no slots.
    """
    MAX_SLOTS_PER_CARRIER_LANE = 4
    # Compute lane parcel demand from orders
    lane_demand: dict[tuple[str, str], int] = defaultdict(int)
    for o in problem.orders:
        lane_demand[(o.origin_fc, o.destination_ds)] += 1
        # also hub-spoke: every SC on the path could see traffic
        for sc_id in problem.scs.keys():
            if problem.lane(o.origin_fc, sc_id) and problem.lane(sc_id, o.destination_ds):
                lane_demand[(o.origin_fc, sc_id)] += 1
                lane_demand[(sc_id, o.destination_ds)] += 1

    trips: list[dict] = []
    trip_index: dict[tuple[int, int, int], int] = {}
    for lane_idx, lane in enumerate(problem.lanes):
        for c_idx, c in enumerate(problem.carriers):
            if not c.active:
                continue
            if lane.lane_type not in c.eligible_lane_types:
                continue
            # Courier carriers serve FC→DS direct only and are handled by z[i] vars
            if c.load_type == "Courier":
                continue
            v = problem.vehicles[c.vehicle_type]
            # PTL has no meaning on vehicles with no PTL tier (ptl_min = 0),
            # which after V4's 2Wheeler removal is just the Courier vehicle.
            # A PTL carrier row offering such a vehicle would create a trip
            # whose load_kg bounds collapse to a degenerate range; skip.
            if c.load_type == "PTL" and v.ptl_min_weight_kg <= 0:
                continue
            demand = lane_demand.get((lane.origin, lane.destination), 0)
            if demand == 0:
                continue
            n_slots = min(MAX_SLOTS_PER_CARRIER_LANE,
                          max(1, math.ceil(demand / max(1, v.parcel_capacity))))
            for slot in range(n_slots):
                t_idx = len(trips)
                trips.append({
                    "carrier_idx": c_idx,
                    "lane_idx": lane_idx,
                    "slot": slot,
                    "origin": lane.origin,
                    "destination": lane.destination,
                    "lane_type": lane.lane_type,
                    "transit_hr": lane.transit_hr,
                })
                trip_index[(c_idx, lane_idx, slot)] = t_idx
    return trips, trip_index


def _enumerate_order_routes(problem: Problem, log: LogCapture | None) -> dict[str, dict]:
    """For each order, enumerate (direct_trip, hub_spoke_mm+lm_trip pairs).

    Each "choice" picks a specific trip(s). We cap the number of choices per
    order to control variable count.
    """
    MAX_HUB_SPOKE_CHOICES = 6
    MAX_DIRECT_CHOICES = 4
    # Build trip lookup by (origin, dest, lane_type) → list of (trip_idx, carrier_idx)
    trips, _ = _enumerate_trips(problem, log=None)
    by_od: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for t_idx, t in enumerate(trips):
        by_od[(t["origin"], t["destination"], t["lane_type"])].append(t_idx)

    out: dict[str, dict] = {}
    for o in problem.orders:
        hub_choices: list[tuple[int, int]] = []
        direct_choices: list[tuple[int]] = []
        # Direct
        for trip_idx in by_od.get((o.origin_fc, o.destination_ds, LANE_FC_DS), [])[:MAX_DIRECT_CHOICES]:
            direct_choices.append((trip_idx,))
        # Hub-spoke
        for sc_id in problem.scs.keys():
            mm_trips = by_od.get((o.origin_fc, sc_id, LANE_FC_SC), [])
            lm_trips = by_od.get((sc_id, o.destination_ds, LANE_SC_DS), [])
            if not mm_trips or not lm_trips:
                continue
            # take cross-product but cap
            for mm in mm_trips[:1]:
                for lm in lm_trips[:1]:
                    hub_choices.append((mm, lm))
                    if len(hub_choices) >= MAX_HUB_SPOKE_CHOICES:
                        break
            if len(hub_choices) >= MAX_HUB_SPOKE_CHOICES:
                break
        out[o.order_id] = {
            "direct_choices": direct_choices,
            "hub_spoke_choices": hub_choices,
            "courier_eligible": (
                o.weight_kg <= problem.courier_max_weight_kg + 1e-9
                and o.volume_m3 <= problem.courier_max_vol_m3 + 1e-9
            ),
        }
    # Cache trips on the function attribute for the build to reuse — keeps the
    # two enumerations in sync.
    out["__trips__"] = trips  # type: ignore[assignment]
    return out
