"""Parse a solved ``MethodResult`` into the seven output sheets' data shapes.

Each method already populates ``MethodResult.assignments`` and ``.trips`` for
the formats it can support (Quick + Heuristic fully; Strict + Balanced via
this module's ``extract_strict_assignments``). LP Bound returns no per-order
data — the writer fills those sheets with the "Not applicable for LP Bound"
sentinel.
"""
from __future__ import annotations

import datetime as _dt
from collections import defaultdict
from typing import Any

from .methods.base import MethodResult
from .problem import Problem


def hr_to_clock(hr: float, problem: Problem) -> str:
    if hr is None:
        return ""
    base = problem.wave_date
    dt = base + _dt.timedelta(hours=float(hr))
    return dt.strftime("%Y-%m-%d %H:%M")


def extract_strict_assignments(result: MethodResult, problem: Problem) -> None:
    """Populate result.assignments / .trips from strict's variable_values.

    Called by main.py after Strict and Balanced finish (Quick + Heuristic
    populate these themselves). Skipped for LP Bound.
    """
    if result.method_id in ("quick", "heuristic"):
        return  # already filled
    if not result.variable_values:
        return

    vv = result.variable_values

    # Determine each order's chosen route
    assignments: list[dict[str, Any]] = []
    for o in problem.orders:
        # Look for the active variable
        z = vv.get(("z", o.order_id), 0.0)
        if z > 0.5:
            depart = max(o.order_ready_time_hr, problem.dispatch_wave.start_hr)
            arrival = depart + 2.0
            assignments.append({
                "order_id": o.order_id, "route_type": "Courier",
                "fc": o.origin_fc, "sc": "", "ds": o.destination_ds,
                "carrier": next((c.carrier_id for c in problem.carriers if c.load_type == "Courier"), "Courier"),
                "vehicle": "Courier", "load_type": "Courier",
                "trip_id": f"TRIP_CR_{o.order_id}",
                "dispatch_time": hr_to_clock(depart, problem),
                "sla_status": "On_Time" if arrival <= o.ops_sla_deadline_hr else "Breach",
                "arrival_hr": arrival,
            })
            continue
        # Direct
        found = False
        for k in range(10):  # MAX_DIRECT_CHOICES is 4 but be defensive
            v = vv.get(("w_fd", o.order_id, k), 0.0)
            if v > 0.5:
                assignments.append({
                    "order_id": o.order_id, "route_type": "FC_Direct",
                    "fc": o.origin_fc, "sc": "", "ds": o.destination_ds,
                    "carrier": "—", "vehicle": "—", "load_type": "—",
                    "trip_id": f"TRIP_FD_{o.order_id}",
                    "dispatch_time": hr_to_clock(max(o.order_ready_time_hr, problem.dispatch_wave.start_hr), problem),
                    "sla_status": _sla_status_from_breach(vv, o),
                    "arrival_hr": vv.get(("arrival", o.order_id), 0.0),
                })
                found = True
                break
        if found:
            continue
        # Hub-spoke
        for k in range(10):
            v = vv.get(("x_mm", o.order_id, k), 0.0)
            if v > 0.5:
                assignments.append({
                    "order_id": o.order_id, "route_type": "Hub_Spoke",
                    "fc": o.origin_fc, "sc": "—", "ds": o.destination_ds,
                    "carrier": "—", "vehicle": "—", "load_type": "—",
                    "trip_id": f"TRIP_LM_{o.order_id}",
                    "dispatch_time": hr_to_clock(max(o.order_ready_time_hr, problem.dispatch_wave.start_hr), problem),
                    "sla_status": _sla_status_from_breach(vv, o),
                    "arrival_hr": vv.get(("arrival", o.order_id), 0.0),
                })
                break

    result.assignments = assignments


def _sla_status_from_breach(vv: dict, o) -> str:
    return "Breach" if vv.get(("breach", o.order_id), 0.0) > 0.5 else "On_Time"


def build_order_timeline(result: MethodResult, problem: Problem) -> list[dict[str, Any]]:
    """Build the Order_Timeline sheet rows."""
    timeline = []
    for a in result.assignments:
        o = next((o for o in problem.orders if o.order_id == a["order_id"]), None)
        if not o:
            continue
        depart = max(o.order_ready_time_hr, problem.dispatch_wave.start_hr)
        if a["route_type"] == "Courier":
            timeline.append({
                "order_id": o.order_id,
                "fc_dispatch": "", "sc_arrival": "", "sc_dispatch": "",
                "ds_arrival": "", "ds_dispatch": "",
                "customer_eta": hr_to_clock(depart + 2.0, problem),
                "ops_sla_deadline": hr_to_clock(o.ops_sla_deadline_hr, problem),
                "sla_status": a.get("sla_status", "On_Time"),
            })
        elif a["route_type"] == "FC_Direct":
            timeline.append({
                "order_id": o.order_id,
                "fc_dispatch": hr_to_clock(depart, problem),
                "sc_arrival": "", "sc_dispatch": "",
                "ds_arrival": hr_to_clock(a.get("arrival_hr") or (depart + 4.0), problem),
                "ds_dispatch": hr_to_clock((a.get("arrival_hr") or depart + 4.0) + 0.5, problem),
                "customer_eta": hr_to_clock((a.get("arrival_hr") or depart + 6.0) + 1.0, problem),
                "ops_sla_deadline": hr_to_clock(o.ops_sla_deadline_hr, problem),
                "sla_status": a.get("sla_status", "On_Time"),
            })
        else:  # Hub_Spoke
            timeline.append({
                "order_id": o.order_id,
                "fc_dispatch": hr_to_clock(depart, problem),
                "sc_arrival": hr_to_clock(depart + 1.0, problem),
                "sc_dispatch": hr_to_clock(depart + 1.5, problem),
                "ds_arrival": hr_to_clock(a.get("arrival_hr") or (depart + 5.0), problem),
                "ds_dispatch": hr_to_clock((a.get("arrival_hr") or depart + 5.0) + 0.5, problem),
                "customer_eta": hr_to_clock((a.get("arrival_hr") or depart + 6.0) + 1.0, problem),
                "ops_sla_deadline": hr_to_clock(o.ops_sla_deadline_hr, problem),
                "sla_status": a.get("sla_status", "On_Time"),
            })
    return timeline


def build_node_utilization(result: MethodResult, problem: Problem) -> list[dict[str, Any]]:
    """Per-node load vs capacity for Node_Utilization sheet."""
    fc_load: dict[str, int] = defaultdict(int)
    sc_load: dict[str, int] = defaultdict(int)
    ds_load: dict[str, int] = defaultdict(int)
    for a in result.assignments:
        if a.get("fc"): fc_load[a["fc"]] += 1
        if a.get("sc"): sc_load[a["sc"]] += 1
        if a.get("ds"): ds_load[a["ds"]] += 1
    wave_hours = max(0.5, problem.dispatch_wave.end_hr - problem.dispatch_wave.start_hr)
    rows = []
    for fc_id, fc in problem.fcs.items():
        cap = int(fc.throughput_parcels_per_hr * wave_hours)
        load = fc_load.get(fc_id, 0)
        util = 100.0 * load / max(1, cap)
        rows.append({"node_id": fc_id, "node_type": "FC", "load_parcels": load,
                     "capacity_parcels": cap, "utilization_pct": round(util, 1),
                     "bottleneck_flag": "OVERFLOW" if util > 100 else ("NEAR_CAP" if util > 90 else ""),
                     "notes": ""})
    for sc_id, sc in problem.scs.items():
        cap = int(sc.throughput_parcels_per_hr * wave_hours)
        load = sc_load.get(sc_id, 0)
        util = 100.0 * load / max(1, cap)
        rows.append({"node_id": sc_id, "node_type": "SC", "load_parcels": load,
                     "capacity_parcels": cap, "utilization_pct": round(util, 1),
                     "bottleneck_flag": "OVERFLOW" if util > 100 else ("NEAR_CAP" if util > 90 else ""),
                     "notes": "(throughput basis)"})
    for ds_id, ds in problem.dses.items():
        cap = ds.normal_capacity_parcels
        load = ds_load.get(ds_id, 0)
        util = 100.0 * load / max(1, cap)
        rows.append({"node_id": ds_id, "node_type": "DS", "load_parcels": load,
                     "capacity_parcels": cap, "utilization_pct": round(util, 1),
                     "bottleneck_flag": "OVERFLOW" if util > 100 else ("NEAR_CAP" if util > 90 else ""),
                     "notes": f"{ds.ds_type} DS"})
    return rows


def order_kpis(result: MethodResult, problem: Problem) -> dict:
    n = len(problem.orders)
    counts = {"Courier": 0, "Hub_Spoke": 0, "FC_Direct": 0}
    breaches = 0
    # Load-type mix: count orders by trip's load_type, and trip count by type
    load_type_orders: dict[str, int] = defaultdict(int)
    load_type_trips: dict[str, int] = defaultdict(int)
    for a in result.assignments:
        counts[a["route_type"]] = counts.get(a["route_type"], 0) + 1
        if a.get("sla_status") == "Breach":
            breaches += 1
        lt = a.get("load_type", "")
        if lt:
            load_type_orders[lt] += 1
    for t in result.trips:
        lt = t.get("load_type", "")
        if lt:
            load_type_trips[lt] += 1
    return {
        "total_orders": n,
        "orders_via_courier": counts.get("Courier", 0),
        "orders_via_hub_spoke": counts.get("Hub_Spoke", 0),
        "orders_via_fc_direct": counts.get("FC_Direct", 0),
        "sla_met_pct": round(100.0 * (n - breaches) / max(1, n), 2),
        "sla_breaches": breaches,
        "avg_cost_per_order": round(
            (result.best_objective or 0.0) / max(1, n), 2
        ),
        "load_type_orders": dict(load_type_orders),
        "load_type_trips": dict(load_type_trips),
    }
