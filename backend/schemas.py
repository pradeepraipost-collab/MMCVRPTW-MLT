"""Pydantic request/response models for the FastAPI surface (spec §8).

These mirror the JSON contracts the frontend depends on. Keep them small and
explicit — request validation lives here, not scattered through endpoint code.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------- Upload ----------

class UploadValidationError(BaseModel):
    sheet: str | None = None
    column: str | None = None
    message: str


class UploadResponse(BaseModel):
    run_id: str
    filename: str
    preview_stats: dict[str, Any]
    validation: dict[str, Any]  # {"ok": bool, "errors": [UploadValidationError]}


# ---------- Master summary ----------

class MasterSummary(BaseModel):
    fcs: int
    scs: int
    dses_active: int
    dses_minor: int
    lanes_fc_sc: int
    lanes_sc_ds: int
    lanes_fc_ds_direct: int
    lanes_sc_sc: int
    carriers: int
    vehicles: int
    orders: int
    active_order_wave: str
    active_dispatch_wave: str


# ---------- Methods ----------

class MethodBullet(BaseModel):
    ok: bool
    text: str


class MethodConfig(BaseModel):
    """Method config exposed via /api/methods. Mirrors frontend src/data/methods.js."""
    id: str
    badge: str
    badge_color: str
    name: str
    tagline: str
    solve_time: str
    gap: str
    enabled: bool
    bullets: list[MethodBullet]
    detail: dict[str, Any]


# ---------- Solve ----------

class SolveRequest(BaseModel):
    run_id: str
    method_id: str = Field(..., description="quick | balanced | strict | heuristic | lp_bound")


class SolveStartResponse(BaseModel):
    run_id: str
    method_id: str
    started: bool
    message: str


class CancelResponse(BaseModel):
    run_id: str
    cancelled: bool
    message: str


# ---------- Results ----------

class CostBreakdown(BaseModel):
    fc_fixed_cost_inr: float
    carrier_cost_inr: float
    sla_penalty_inr: float
    total_inr: float


class SolveSummary(BaseModel):
    run_id: str
    run_date: str
    active_wave: str
    method_used: str
    status: str  # optimal | gap_reached | time_limit | infeasible | error | cancelled
    achieved_gap_pct: float | None
    target_gap_pct: float
    best_objective_inr: float | None
    best_lower_bound_inr: float | None
    wall_time_sec: float
    threads_used: int
    cost: CostBreakdown
    total_orders: int
    orders_via_courier: int
    orders_via_hub_spoke: int
    orders_via_fc_direct: int
    sla_met_pct: float


class ResultResponse(BaseModel):
    summary: SolveSummary
    order_assignment: list[dict[str, Any]]
    order_timeline: list[dict[str, Any]]
    trip_plan: list[dict[str, Any]]
    node_utilization: list[dict[str, Any]]
    recommendations: dict[str, Any]
    cost_comparison: dict[str, Any]


# ---------- Benchmark ----------

class BenchmarkRequest(BaseModel):
    run_id: str
    sample_size: int = 1000
    seed: int = 42


class BenchmarkMethodResult(BaseModel):
    method: str
    cost_inr: float | None
    wall_time_sec: float
    gap_pct: float | None
    status: str


class BenchmarkResponse(BaseModel):
    sample_size: int
    seed: int
    results: list[BenchmarkMethodResult]
