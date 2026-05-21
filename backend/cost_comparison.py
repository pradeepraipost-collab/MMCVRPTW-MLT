"""Courier-only baseline + per-route-type breakdown for the Cost_Comparison sheet.

The "courier-only" baseline assumes every order ships FC_DIRECT at the courier
rate (₹85 per parcel for eligible items; weighted-up rate for heavier items
requiring oversize courier service). The optimizer's actual cost is compared
to this; the savings figure is the headline number on the Cost_Comparison tab.
"""
from __future__ import annotations

from typing import Any

from .methods.base import MethodResult
from .problem import Problem


# Heuristic upcharge for orders that exceed the courier weight/vol limits and
# would in reality need oversize courier service. Same model as V3: ₹85 base
# scaled by weight bin.
def _baseline_per_parcel_cost(o, problem: Problem) -> float:
    if o.weight_kg <= problem.courier_max_weight_kg + 1e-9 and o.volume_m3 <= problem.courier_max_vol_m3 + 1e-9:
        return problem.courier_rate_inr
    # Oversize: scale by weight band per V3 convention
    if o.weight_kg <= 5:
        return problem.courier_rate_inr * 4.0
    if o.weight_kg <= 15:
        return problem.courier_rate_inr * 10.0
    return problem.courier_rate_inr * 25.0


def compute_cost_comparison(result: MethodResult, problem: Problem) -> dict[str, Any]:
    """Return the Cost_Comparison sheet payload (matches output template structure)."""
    baseline = sum(_baseline_per_parcel_cost(o, problem) for o in problem.orders)
    optimizer = result.best_objective or 0.0
    savings_inr = baseline - optimizer
    savings_pct = (savings_inr / max(1.0, baseline)) * 100.0 if baseline else 0.0

    # Per-route-type breakdown
    counts = {"Hub_Spoke": 0, "FC_Direct": 0, "Courier": 0}
    cost_by_type = {"Hub_Spoke": 0.0, "FC_Direct": 0.0, "Courier": 0.0}
    for a in result.assignments:
        counts[a["route_type"]] = counts.get(a["route_type"], 0) + 1
    # Approximate per-route-type cost split based on carrier_cost share
    cost_by_type["Courier"] = counts["Courier"] * problem.courier_rate_inr
    remaining_carrier = max(0.0, result.carrier_cost_inr - cost_by_type["Courier"])
    if counts["Hub_Spoke"] + counts["FC_Direct"] > 0:
        share_hs = counts["Hub_Spoke"] / max(1, counts["Hub_Spoke"] + counts["FC_Direct"])
        cost_by_type["Hub_Spoke"] = remaining_carrier * share_hs
        cost_by_type["FC_Direct"] = remaining_carrier * (1.0 - share_hs)

    return {
        "baseline_cost_inr": baseline,
        "optimizer_cost_inr": optimizer,
        "savings_inr": savings_inr,
        "savings_pct": savings_pct,
        "breakdown_by_route_type": [
            {"route_type": "Hub_Spoke",  "orders": counts["Hub_Spoke"],
             "cost_inr": cost_by_type["Hub_Spoke"],
             "avg_inr_per_order": cost_by_type["Hub_Spoke"] / max(1, counts["Hub_Spoke"])},
            {"route_type": "FC_Direct",  "orders": counts["FC_Direct"],
             "cost_inr": cost_by_type["FC_Direct"],
             "avg_inr_per_order": cost_by_type["FC_Direct"] / max(1, counts["FC_Direct"])},
            {"route_type": "Courier",    "orders": counts["Courier"],
             "cost_inr": cost_by_type["Courier"],
             "avg_inr_per_order": problem.courier_rate_inr},
            {"route_type": "FC_Fixed_Cost", "orders": None,
             "cost_inr": result.fc_fixed_cost_inr,
             "avg_inr_per_order": result.fc_fixed_cost_inr / max(1, len(problem.orders))},
            {"route_type": "SLA_Penalty", "orders": None,
             "cost_inr": result.sla_penalty_inr,
             "avg_inr_per_order": result.sla_penalty_inr / max(1, len(problem.orders))},
        ],
        "takeaways": [
            (f"Optimizer is {savings_pct:.1f}% cheaper than the courier-only baseline."
             if savings_pct >= 0
             else f"Optimizer is {abs(savings_pct):.1f}% MORE expensive than courier-only — "
                  "indicates SLA penalties or FC fixed costs are dominating; "
                  "review the breakdown for tuning opportunities."),
            f"Hub-spoke consolidation handled {counts['Hub_Spoke']} orders "
            f"({100*counts['Hub_Spoke']/max(1, len(problem.orders)):.1f}%).",
            f"FC→DS direct used for {counts['FC_Direct']} orders "
            f"({100*counts['FC_Direct']/max(1, len(problem.orders)):.1f}%).",
            f"Pure courier preserved for {counts['Courier']} orders where it wins on cost.",
        ],
    }
