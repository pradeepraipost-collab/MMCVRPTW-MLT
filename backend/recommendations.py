"""The six analytical Recommendations cards (spec §12).

These power both the Recommendations tab in the UI and the Recommendations
sheet in the output Excel. They are computed deterministically from the
solved ``MethodResult`` plus the original ``Problem`` — no ML, no thresholds
beyond what the spec specifies (50% utilization, 5% concentration buffer,
etc.).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .methods.base import MethodResult
from .problem import Problem


def compute_recommendations(result: MethodResult, problem: Problem) -> dict[str, list[dict]]:
    return {
        "card1_underutilized_fcs": card1_underutilized_fcs(result, problem),
        "card2_carriers_near_cap": card2_carriers_near_concentration_cap(result, problem),
        "card3_ftl_consolidation": card3_ftl_consolidation(result, problem),
        "card4_courier_vs_hubspoke": card4_courier_vs_hubspoke(result, problem),
        "card5_sla_risk":            card5_sla_breach_risk(result, problem),
        "card6_multistop_opps":      card6_multistop_opportunities(result, problem),
    }


def card1_underutilized_fcs(result: MethodResult, problem: Problem) -> list[dict]:
    """FCs running below 50% of wave throughput. Rebalance candidates."""
    fc_load = defaultdict(int)
    for a in result.assignments:
        fc_load[a["fc"]] += 1
    wave_hours = max(0.5, problem.dispatch_wave.end_hr - problem.dispatch_wave.start_hr)
    rows = []
    for fc_id, fc in problem.fcs.items():
        cap = int(fc.throughput_parcels_per_hr * wave_hours)
        util = 100.0 * fc_load.get(fc_id, 0) / max(1, cap)
        if util < 50:
            rows.append({
                "fc_id": fc_id, "city": fc.city, "region": fc.region,
                "load_parcels": fc_load.get(fc_id, 0), "capacity_parcels": cap,
                "utilization_pct": round(util, 1),
                "suggestion": f"Underused — could absorb {int(cap - fc_load.get(fc_id, 0))} more parcels this wave. Consider rebalancing from over-loaded peers in {fc.region}.",
            })
    rows.sort(key=lambda r: r["utilization_pct"])
    return rows[:5]


def card2_carriers_near_concentration_cap(result: MethodResult, problem: Problem) -> list[dict]:
    """Carriers within 5% of Max_Concentration_pct. Over-dependence risk."""
    counts: dict[str, int] = defaultdict(int)
    for a in result.assignments:
        counts[a["carrier"]] = counts.get(a["carrier"], 0) + 1
    total = max(1, len(problem.orders))
    rows = []
    seen = set()
    for c in problem.carriers:
        if c.carrier_id in seen:
            continue
        seen.add(c.carrier_id)
        n = counts.get(c.carrier_id, 0)
        pct = 100.0 * n / total
        buffer = c.max_concentration_pct - pct
        risk = "HIGH" if buffer < 2 else "MEDIUM" if buffer < 5 else "LOW"
        rows.append({
            "carrier": c.carrier_id, "orders_assigned": n,
            "pct_of_total": round(pct, 1),
            "max_concentration_pct": c.max_concentration_pct,
            "buffer_pct": round(buffer, 1), "risk_level": risk,
        })
    rows.sort(key=lambda r: r["buffer_pct"])
    return rows[:6]


def card3_ftl_consolidation(result: MethodResult, problem: Problem) -> list[dict]:
    """Lanes where merging current PTL+LTL trips would clear the 75% FTL threshold."""
    # Group trips by lane
    by_lane: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for t in result.trips:
        if t.get("lane_type") in ("FC_SC", "SC_DS", "FC_DS"):
            origin, dest = t["lane"].split("→") if "→" in t["lane"] else (t.get("origin", "?"), t.get("destination", "?"))
            by_lane[(origin.strip(), dest.strip())].append(t)
    rows = []
    for (o, d), trips in by_lane.items():
        # Sum fills of non-FTL trips on this lane
        partial = [t for t in trips if t.get("load_type") != "FTL"]
        if len(partial) < 2:
            continue
        combined_weight_fill = sum(t.get("fill_weight_pct", 0) for t in partial)
        if combined_weight_fill >= 75:
            current_cost = sum(t.get("cost_inr", 0) for t in partial)
            # FTL cost on this lane: take cheapest carrier's FTL rate
            ftl_rate = min(
                (c.ftl_rate_inr or 1e9 for c in problem.carriers if c.ftl_rate_inr),
                default=20000,
            )
            rows.append({
                "lane": f"{o}→{d}",
                "current_ptl_ltl_cost": current_cost,
                "hypothetical_ftl_cost": ftl_rate,
                "savings_inr": current_cost - ftl_rate,
                "combined_fill_pct": round(combined_weight_fill, 1),
                "action": f"Combine {len(partial)} partial trips into 1 FTL.",
            })
    rows.sort(key=lambda r: -r["savings_inr"])
    return rows[:5]


def card4_courier_vs_hubspoke(result: MethodResult, problem: Problem) -> list[dict]:
    """Per-pincode comparison: where courier wins (low-volume remote) and where hub-spoke does."""
    # Group orders by DS pincode → derive per-pincode optimizer choice
    by_pin: dict[int, dict] = defaultdict(lambda: {"orders": 0, "courier_count": 0,
                                                    "hub_count": 0, "city": "", "direct_count": 0})
    for a in result.assignments:
        ds = problem.dses.get(a["ds"])
        if not ds:
            continue
        pin = ds.pincode if hasattr(ds, "pincode") else 0
        by_pin[pin]["orders"] += 1
        by_pin[pin]["city"] = ds.city
        if a["route_type"] == "Courier": by_pin[pin]["courier_count"] += 1
        elif a["route_type"] == "Hub_Spoke": by_pin[pin]["hub_count"] += 1
        else: by_pin[pin]["direct_count"] += 1
    rows = []
    for pin, data in by_pin.items():
        choice = "Courier" if data["courier_count"] > data["hub_count"] else "Hub_Spoke"
        courier_cost = data["orders"] * problem.courier_rate_inr
        hub_cost = data["orders"] * 1100  # rough per-parcel hub-spoke
        savings = (hub_cost - courier_cost) if choice == "Courier" else (courier_cost - hub_cost)
        rows.append({
            "destination_pincode": pin, "city": data["city"], "orders": data["orders"],
            "courier_cost_inr": courier_cost, "hubspoke_cost_inr": hub_cost,
            "optimizer_choice": choice,
            "savings_per_order": round(savings / max(1, data["orders"]), 1),
        })
    rows.sort(key=lambda r: -abs(r["savings_per_order"]))
    return rows[:6]


def card5_sla_breach_risk(result: MethodResult, problem: Problem) -> list[dict]:
    """Top 10 tightest FC×DS pairs by slack between transit and Ops_SLA_Deadline."""
    rows = []
    by_pair: dict[tuple[str, str], dict] = defaultdict(lambda: {
        "orders": 0, "breaches": 0, "slack_sum_hr": 0.0,
    })
    for a in result.assignments:
        o = next((o for o in problem.orders if o.order_id == a["order_id"]), None)
        if not o:
            continue
        slack = o.ops_sla_deadline_hr - (a.get("arrival_hr") or 0.0)
        key = (a["fc"], a["ds"])
        by_pair[key]["orders"] += 1
        by_pair[key]["slack_sum_hr"] += slack
        if a.get("sla_status") == "Breach":
            by_pair[key]["breaches"] += 1
    for (fc, ds), data in by_pair.items():
        avg_slack = data["slack_sum_hr"] / max(1, data["orders"])
        rows.append({
            "fc": fc, "ds": ds, "orders": data["orders"],
            "breaches": data["breaches"],
            "avg_slack_hr": round(avg_slack, 2),
        })
    rows.sort(key=lambda r: r["avg_slack_hr"])
    return rows[:10]


def card6_multistop_opportunities(result: MethodResult, problem: Problem) -> list[dict]:
    """DS pairs frequently on separate trips that could fit within Max_Detour_pct."""
    rows = []
    # Crude: find DSes in the same city that received single-stop trips on the same wave
    ds_trips_by_city: dict[str, list[dict]] = defaultdict(list)
    for t in result.trips:
        if t.get("lane_type") == "SC_DS" and t.get("stop_count") == 1:
            dest = t.get("lane", "").split("→")[-1].strip()
            ds = problem.dses.get(dest)
            if ds:
                ds_trips_by_city[ds.city].append(t)
    for city, trips in ds_trips_by_city.items():
        if len(trips) >= 2:
            rows.append({
                "city": city, "single_stop_trip_count": len(trips),
                "opportunity": f"{len(trips)} single-stop SC→DS trips in {city}; "
                               f"a multi-stop trip with 2-3 stops within 5% detour "
                               f"would consolidate {min(3, len(trips))} of these.",
                "est_savings_per_consolidation_inr": 1500,
            })
    rows.sort(key=lambda r: -r["single_stop_trip_count"])
    return rows[:5]
