"""FastAPI app — exposes the API surface from spec §8.

CORS is open to ``http://localhost:*`` only (spec §8 final line). Solves run
in background threads spawned by ``solve_runner.start_solve``; the SSE
endpoint streams log lines + status frames to the Solve page.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from . import benchmark as _benchmark
from . import output_writer
from . import recommendations as _reco
from . import cost_comparison as _ccmp
from . import extract as _extract
from .ingest import read_master_workbook, summarise
from .methods import METHOD_REGISTRY
from .methods.roadmap import RoadmapMethod
from .problem import Problem, build_problem
from . import schemas
from .solve_runner import SolveRun, cancel_run, sse_log_stream, start_solve


app = FastAPI(title="MMCVRPTW-MLT V4 API", version="0.4.0")

# CORS: localhost only (any port)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- In-memory state ----------
# In production this would be Redis / SQLite; for a single-user local app a
# dict is fine. Each run_id maps to the loaded Problem and any started solves.
problems: dict[str, Problem] = {}
uploads: dict[str, dict[str, Any]] = {}  # run_id → {filename, preview_stats}
runs: dict[str, SolveRun] = {}


# ---------- /api/upload ----------

@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    """Accept the 15-sheet master xlsx. Validates strictly (§6) and rejects
    incomplete uploads with a clear UI-facing error."""
    run_id = f"RUN-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    tmp_path = Path("runs") / run_id / "master.xlsx"
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    tmp_path.write_bytes(content)

    result = read_master_workbook(tmp_path)
    if not result.ok:
        # Surface validation errors directly — V4 §6 forbids silent recovery.
        return JSONResponse(
            status_code=400,
            content={
                "run_id": run_id,
                "filename": file.filename,
                "validation": {"ok": False, "errors": [e.to_dict() for e in result.errors]},
                "preview_stats": result.preview_stats,
            },
        )

    problem = build_problem(result.frames)
    problems[run_id] = problem
    uploads[run_id] = {"filename": file.filename, "preview_stats": result.preview_stats}

    return {
        "run_id": run_id,
        "filename": file.filename,
        "preview_stats": result.preview_stats,
        "validation": {"ok": True, "errors": [e.to_dict() for e in result.errors]},
    }


# ---------- /api/master_summary/{run_id} ----------

@app.get("/api/master_summary/{run_id}")
def master_summary(run_id: str) -> dict:
    if run_id not in problems:
        raise HTTPException(404, f"Unknown run_id {run_id}")
    p = problems[run_id]
    return {
        "fcs": len(p.fcs),
        "scs": len(p.scs),
        "dses_active": sum(1 for d in p.dses.values() if d.ds_type == "Active"),
        "dses_minor": sum(1 for d in p.dses.values() if d.ds_type != "Active"),
        "lanes_fc_sc": sum(1 for ln in p.lanes if ln.lane_type == "FC_SC"),
        "lanes_sc_ds": sum(1 for ln in p.lanes if ln.lane_type == "SC_DS"),
        "lanes_fc_ds_direct": sum(1 for ln in p.lanes if ln.lane_type == "FC_DS"),
        "lanes_sc_sc": sum(1 for ln in p.lanes if ln.lane_type == "SC_SC"),
        "carriers": len(set(c.carrier_id for c in p.carriers)),
        "vehicles": len(p.vehicles),
        "orders": len(p.orders),
        "active_order_wave": p.order_wave.wave_id,
        "active_dispatch_wave": p.dispatch_wave.wave_id,
    }


# ---------- /api/methods ----------

@app.get("/api/methods")
def list_methods() -> list[dict]:
    """Return the 10-method config (mirrors frontend src/data/methods.js)."""
    return _METHODS_CONFIG


# ---------- /api/solve ----------

@app.post("/api/solve")
def solve(req: schemas.SolveRequest) -> dict:
    if req.run_id not in problems:
        raise HTTPException(404, f"Unknown run_id {req.run_id}")
    method_id = req.method_id
    if method_id not in METHOD_REGISTRY:
        raise HTTPException(400, f"Unknown method_id {method_id}")
    if METHOD_REGISTRY[method_id] is RoadmapMethod:
        raise HTTPException(
            400,
            f"Method '{method_id}' is on the Phase-2 roadmap (spec §11). "
            "See the Configure screen for full transparency on what it would solve."
        )
    problem = problems[req.run_id]
    run = start_solve(runs, req.run_id, method_id, problem,
                      time_cap_sec=3600.0, gap_target=0.01, threads=8)
    return {
        "run_id": run.run_id, "method_id": method_id,
        "started": True,
        "message": f"Solve started: {method_id} on {len(problem.orders)} orders.",
    }


# ---------- /api/solve_stream/{run_id} ----------

@app.get("/api/solve_stream/{run_id}")
async def solve_stream(run_id: str, request: Request):
    if run_id not in runs:
        raise HTTPException(404, f"No solve run for {run_id}")
    return EventSourceResponse(sse_log_stream(runs[run_id]))


# ---------- /api/cancel/{run_id} ----------

@app.post("/api/cancel/{run_id}")
def cancel(run_id: str) -> dict:
    ok = cancel_run(runs, run_id)
    return {"run_id": run_id, "cancelled": ok,
            "message": "Cancel signalled." if ok else "Nothing to cancel."}


# ---------- /api/result/{run_id} ----------

@app.get("/api/result/{run_id}")
def result(run_id: str) -> dict:
    if run_id not in runs:
        raise HTTPException(404, f"No solve run for {run_id}")
    run = runs[run_id]
    if run.status not in ("done", "error", "cancelled"):
        return {"status": run.status, "elapsed_sec": run.elapsed()}
    if run.result is None:
        return {"status": run.status, "error": run.error}
    r = run.result
    problem = run.problem
    _extract.extract_strict_assignments(r, problem)
    timeline = _extract.build_order_timeline(r, problem)
    node_util = _extract.build_node_utilization(r, problem)
    kpis = _extract.order_kpis(r, problem)
    recos = _reco.compute_recommendations(r, problem)
    ccmp = _ccmp.compute_cost_comparison(r, problem)
    # Write Excel as a side effect so /download has a file ready
    out_path = Path("runs") / run_id / "output.xlsx"
    output_writer.write_output(r, problem, out_path, run_id)
    return {
        "summary": {
            "run_id": run_id, "run_date": time.strftime("%Y-%m-%d"),
            "active_wave": problem.order_wave.wave_id,
            "method_used": r.method_id, "status": r.status,
            "achieved_gap_pct": r.achieved_gap_pct, "target_gap_pct": 1.0,
            "best_objective_inr": r.best_objective,
            "best_lower_bound_inr": r.best_lower_bound,
            "wall_time_sec": r.wall_time_sec,
            "threads_used": r.threads_used,
            "cost": {
                "fc_fixed_cost_inr": r.fc_fixed_cost_inr,
                "carrier_cost_inr": r.carrier_cost_inr,
                "sla_penalty_inr": r.sla_penalty_inr,
                "total_inr": r.fc_fixed_cost_inr + r.carrier_cost_inr + r.sla_penalty_inr,
            },
            **kpis,
        },
        "order_assignment": r.assignments,
        "order_timeline": timeline,
        "trip_plan": r.trips,
        "node_utilization": node_util,
        "recommendations": recos,
        "cost_comparison": ccmp,
    }


# ---------- /api/download/{run_id} ----------

@app.get("/api/download/{run_id}")
def download(run_id: str):
    p = Path("runs") / run_id / "output.xlsx"
    if not p.exists():
        raise HTTPException(404, f"No output for run {run_id}. Make sure /api/result/{run_id} was called first.")
    return FileResponse(p, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=f"{run_id}_output.xlsx")


# ---------- /api/benchmark ----------

@app.post("/api/benchmark")
def benchmark_run(req: schemas.BenchmarkRequest) -> dict:
    if req.run_id not in problems:
        raise HTTPException(404, f"Unknown run_id {req.run_id}")
    return _benchmark.run_benchmark(req.run_id, problems[req.run_id],
                                    sample_size=req.sample_size, seed=req.seed)


@app.get("/api/benchmark/{run_id}")
def benchmark_get(run_id: str) -> dict:
    p = Path("runs") / run_id / "benchmark.json"
    if not p.exists():
        raise HTTPException(404, f"No benchmark for {run_id}. POST /api/benchmark first.")
    return json.loads(p.read_text())


# ---------- Static methods config (sourced from spec §11) ----------
# This MIRRORS frontend/src/data/methods.js. Keep both in sync.
_METHODS_CONFIG: list[dict] = [
    {
        "id": "quick", "badge": "QUICK", "badge_color": "amber",
        "name": "Aggregated cells",
        "tagline": "Demand cells + warm start. The fast lane.",
        "solve_time": "60–180 s", "gap": "1–3%", "enabled": True,
        "bullets": [
            {"ok": True, "text": "Solves the full problem in < 2 min"},
            {"ok": True, "text": "Proven gap from LP dual bound"},
            {"ok": True, "text": "All cost & SLA math intact"},
            {"ok": False, "text": "Per-order routes reconstructed post-solve"},
        ],
        "detail": {
            "subproblems": 1, "parallelism": "8-way",
            "solves": [
                "All cost calculations (FC fixed, carrier, courier, SLA penalty)",
                "All capacity constraints (FC throughput, SC staging, DS receiving, vehicle caps)",
                "FTL / PTL / LTL load disjunction with ε-tightening",
                "Carrier concentration caps (global)",
                "Courier eligibility (weight + volume)",
                "SLA breach with tightened Big-M",
            ],
            "does_not_solve": [
                "Per-order routing (orders within same FC,DS,Priority cohort share a route)",
                "MTZ multi-stop (single-stop trips only; opportunities surfaced in Rec 6)",
            ],
            "algorithm": [
                {"step": "Aggregate", "desc": "Group orders by (Origin_FC, Destination_DS, Priority) into ~3,175 cells."},
                {"step": "Build", "desc": "Flow MILP with parcel-count vars per (cell, candidate path)."},
                {"step": "Solve", "desc": "HiGHS 8 threads, 2-min cap."},
                {"step": "Reconstruct", "desc": "Deterministically assign individual orders to optimized flows."},
            ],
            "bound": "The 1–3% gap is HiGHS's MIP gap on the aggregated model. Mathematically tight for the aggregated problem; reconstruction preserves cost exactly.",
        },
    },
    {
        "id": "balanced", "badge": "BALANCED", "badge_color": "teal",
        "name": "Per-FC decomposition",
        "tagline": "Parallel sub-MILPs, one per origin FC. The daily-ops default.",
        "solve_time": "3–6 min", "gap": "3–5%", "enabled": True,
        "bullets": [
            {"ok": True, "text": "Full per-order x/y/w/z binaries within each FC"},
            {"ok": True, "text": "MTZ multi-stop within each FC"},
            {"ok": True, "text": "SLA breach with tightened Big-M"},
            {"ok": False, "text": "Cross-FC SC load balancing (post-validated, rebalance MILP)"},
        ],
        "detail": {
            "subproblems": 15, "parallelism": "15-way process pool",
            "solves": [
                "Full per-order routing inside each FC's sub-problem",
                "MTZ multi-stop within each FC",
                "SLA breach with tight Big-M",
                "FTL / PTL / LTL disjunction",
                "FC-local capacity coupling",
            ],
            "does_not_solve": [
                "Cross-FC SC load balancing (validated globally; rebalance MILP if violated)",
                "Global carrier concentration (pro-rated per FC by order share)",
            ],
            "algorithm": [
                {"step": "Partition", "desc": "Split orders by origin FC into 15 subsets."},
                {"step": "Solve", "desc": "Spawn 15 HiGHS instances (4-min cap each)."},
                {"step": "Merge", "desc": "Combine per-FC solutions."},
                {"step": "Rebalance", "desc": "If global SC/carrier caps violated, run small MILP on overflow (~30-60s)."},
            ],
            "bound": "Per sub-MILP gap is 1-2% (proven). Cross-FC coupling estimated at ~2-3% → total ~3-5%.",
        },
    },
    {
        "id": "strict", "badge": "STRICT", "badge_color": "purple",
        "name": "Monolithic per-order MILP",
        "tagline": "The spec-literal solve. One coupled model.",
        "solve_time": "20–60 min", "gap": "1%", "enabled": True,
        "bullets": [
            {"ok": True, "text": "Every constraint from spec §7 coupled exactly"},
            {"ok": True, "text": "Per-order routing decisions"},
            {"ok": True, "text": "MTZ on multi-stop-eligible trips"},
            {"ok": True, "text": "1% gap mathematically proven from LP dual"},
        ],
        "detail": {
            "subproblems": 1, "parallelism": "8-way HiGHS threads",
            "solves": ["Everything in §7. Single coupled MILP, all couplings exact."],
            "does_not_solve": ["Nothing — this is the spec-literal solve."],
            "algorithm": [
                {"step": "Build", "desc": "Per-order x/y/w/z + trip + MTZ + breach variables (~150k total)."},
                {"step": "Add rows", "desc": "All 13 constraint families from §7."},
                {"step": "Solve", "desc": "HiGHS 8 threads with 60-min hard cap."},
                {"step": "Extract", "desc": "Return at 1% gap or time cap, whichever first."},
            ],
            "bound": "Gap is HiGHS's mip_rel_gap: 100·(obj - dual)/|obj|. Dual bound is rigorous.",
        },
    },
    {
        "id": "heuristic", "badge": "HEURISTIC", "badge_color": "amber",
        "name": "Greedy + 2-opt",
        "tagline": "No MILP. Fast feasible answer for iteration.",
        "solve_time": "10–30 s", "gap": "None (no bound)", "enabled": True,
        "bullets": [
            {"ok": True, "text": "Returns a feasible answer in seconds"},
            {"ok": True, "text": "Useful as a warm-start source"},
            {"ok": False, "text": "No optimality bound"},
            {"ok": False, "text": "Typically 10-25% worse cost than MILP solutions"},
        ],
        "detail": {
            "subproblems": 0, "parallelism": "Sequential",
            "solves": [
                "Feasible assignment respecting all capacities and SLA",
                "Greedy carrier + load type choice per order",
                "2-opt local search on multi-stop trips",
            ],
            "does_not_solve": [
                "No MILP",
                "No optimality proof",
                "Cost typically 10-25% above MILP solutions",
            ],
            "algorithm": [
                {"step": "Sort", "desc": "Orders sorted by Ops_SLA_Deadline ascending."},
                {"step": "Assign", "desc": "Each order → cheapest feasible (route, carrier, vehicle, load_type)."},
                {"step": "Group", "desc": "Assigned orders bundled into trips by (carrier, vehicle, lane)."},
                {"step": "2-opt", "desc": "Local swaps on multi-stop trips with 3+ stops."},
            ],
            "bound": "None. Use LP Bound to derive a lower bound for comparison.",
        },
    },
    {
        "id": "lp_bound", "badge": "LP BOUND", "badge_color": "blue",
        "name": "LP relaxation",
        "tagline": "Diagnostic only — gives a lower bound, not a plan.",
        "solve_time": "5–15 s", "gap": "Lower bound only", "enabled": True,
        "bullets": [
            {"ok": True, "text": "Mathematical floor on what any integer solution can achieve"},
            {"ok": True, "text": "Sanity-check model feasibility"},
            {"ok": True, "text": "Reference for evaluating other methods' gaps"},
            {"ok": False, "text": "Fractional variables — does not produce a real plan"},
        ],
        "detail": {
            "subproblems": 1, "parallelism": "8-way",
            "solves": [
                "Continuous relaxation of the full strict model",
                "Returns LP objective + dual bound (they're the same for LP)",
            ],
            "does_not_solve": [
                "No integer solution",
                "Variables fractional; assignments don't correspond to a real shipment plan",
            ],
            "algorithm": [
                {"step": "Build", "desc": "Same as Strict but every variable continuous."},
                {"step": "Solve", "desc": "HiGHS dual simplex."},
                {"step": "Return", "desc": "LP optimum = lower bound on all integer solutions."},
                {"step": "Skip", "desc": "Output sheets requiring integer assignments show 'Not applicable for LP Bound'."},
            ],
            "bound": "LP optimum IS the lower bound. Tight when relaxation is tight; otherwise loose.",
        },
    },
    # Roadmap (Phase 2) — full content per §16 rule #7 transparency commitment
    {
        "id": "greedy_warmstart", "badge": "ROADMAP — Phase 2", "badge_color": "slate",
        "name": "Greedy warm-start + Aggregated MILP",
        "tagline": "Method 4 result fed as mipStart to Method 1. Expected −30 to −60% solve time.",
        "solve_time": "30–90 s (projected)", "gap": "1–3%", "enabled": False,
        "bullets": [
            {"ok": True, "text": "Same optimality guarantee as Quick"},
            {"ok": True, "text": "Substantially faster (warm-started)"},
            {"ok": False, "text": "Not yet implemented"},
            {"ok": False, "text": "Heuristic warm-start can mislead HiGHS on novel data"},
        ],
        "detail": {
            "subproblems": 1, "parallelism": "8-way",
            "solves": ["Same constraint set as Quick", "Warm-started from Heuristic"],
            "does_not_solve": ["Same gaps as Quick (per-order routing approximation)"],
            "algorithm": [
                {"step": "Heuristic", "desc": "Run Method 4 (Greedy + 2-opt) first."},
                {"step": "Convert", "desc": "Translate per-order assignments to cell-flow integer values."},
                {"step": "Warm-start", "desc": "Pass as mipStart to HiGHS."},
                {"step": "Solve", "desc": "Aggregated MILP closes the gap from the warm start."},
            ],
            "bound": "Inherited from Quick (1-3% from LP dual on aggregated model).",
        },
    },
    {
        "id": "benders", "badge": "ROADMAP — Phase 2", "badge_color": "slate",
        "name": "Benders decomposition",
        "tagline": "Master = routing; subproblems = capacity feasibility. Python cut-loop (no HiGHS lazy callbacks).",
        "solve_time": "10–25 min (projected)", "gap": "1%", "enabled": False,
        "bullets": [
            {"ok": True, "text": "Theoretically convergent to optimality"},
            {"ok": True, "text": "Subproblems are LP-easy (capacity feasibility)"},
            {"ok": False, "text": "Not yet implemented"},
            {"ok": False, "text": "HiGHS lacks lazy callbacks → outer Python loop adds overhead"},
        ],
        "detail": {
            "subproblems": "1 master + many subproblems", "parallelism": "Sub LP solves parallelisable",
            "solves": ["Master routing MILP", "Subproblem LPs for capacity feasibility", "Optimality + feasibility cuts"],
            "does_not_solve": ["Subject to slow convergence on tight problems"],
            "algorithm": [
                {"step": "Master", "desc": "Solve routing master (no capacity constraints)."},
                {"step": "Subproblems", "desc": "LP-check capacity at each FC/SC/DS."},
                {"step": "Cuts", "desc": "Add feasibility/optimality cuts back to master."},
                {"step": "Loop", "desc": "Repeat until no cuts added."},
            ],
            "bound": "Converges to 1% via LP duality on the master.",
        },
    },
    {
        "id": "column_generation", "badge": "ROADMAP — Phase 2", "badge_color": "slate",
        "name": "Column generation (Dantzig-Wolfe)",
        "tagline": "Set-partitioning master + shortest-path pricing. The production-grade VRP method.",
        "solve_time": "15–45 min (projected)", "gap": "1%", "enabled": False,
        "bullets": [
            {"ok": True, "text": "State-of-the-art for VRP-class problems"},
            {"ok": True, "text": "Natural LP bound from restricted master"},
            {"ok": False, "text": "Not yet implemented"},
            {"ok": False, "text": "Pricing oracle (constrained shortest path) needs custom code"},
        ],
        "detail": {
            "subproblems": "1 master + per-vehicle pricing", "parallelism": "Pricing parallelisable",
            "solves": ["Set-partitioning master over routes", "Resource-constrained shortest path pricing"],
            "does_not_solve": ["Pricing convergence can stall on degenerate instances"],
            "algorithm": [
                {"step": "Initial routes", "desc": "Seed restricted master with feasible routes (from Heuristic)."},
                {"step": "Master LP", "desc": "Solve set-partitioning LP; get duals."},
                {"step": "Pricing", "desc": "Find routes with negative reduced cost."},
                {"step": "Branch + price", "desc": "Branch on fractional master vars; price at each node."},
            ],
            "bound": "Restricted master LP gives a valid lower bound; converges to 1%.",
        },
    },
    {
        "id": "lagrangian", "badge": "ROADMAP — Phase 2", "badge_color": "slate",
        "name": "Lagrangian relaxation",
        "tagline": "Dualise carrier-concentration caps; subgradient updates on multipliers.",
        "solve_time": "5–20 min (projected)", "gap": "2–4%", "enabled": False,
        "bullets": [
            {"ok": True, "text": "Decouples carrier-concentration constraints"},
            {"ok": True, "text": "Each iteration is cheap"},
            {"ok": False, "text": "Not yet implemented"},
            {"ok": False, "text": "Convergence-dependent; primal recovery is non-trivial"},
        ],
        "detail": {
            "subproblems": "1 per iteration (relaxed)", "parallelism": "Iteration-level",
            "solves": ["Carrier-relaxed routing MILP per iteration", "Multiplier updates via subgradient"],
            "does_not_solve": ["Need separate primal recovery (e.g. heuristic + projection)"],
            "algorithm": [
                {"step": "Initialise", "desc": "Set Lagrangian multipliers for carrier-concentration."},
                {"step": "Solve relaxed", "desc": "Drop carrier caps; price into objective via multipliers."},
                {"step": "Update", "desc": "Subgradient step on multipliers using constraint violation."},
                {"step": "Recover", "desc": "Project relaxed solution back into the feasible set."},
            ],
            "bound": "Lagrangian dual gives a lower bound; primal-dual gap typically 2-4%.",
        },
    },
    {
        "id": "rolling_horizon", "badge": "ROADMAP — Phase 2", "badge_color": "slate",
        "name": "Rolling horizon",
        "tagline": "Split the 4-hour wave into 30-min slices; solve each slice sequentially.",
        "solve_time": "2–5 min (projected)", "gap": "Variable", "enabled": False,
        "bullets": [
            {"ok": True, "text": "Natural fit for streaming / multi-wave operations"},
            {"ok": True, "text": "Each slice is small and fast"},
            {"ok": False, "text": "Not yet implemented"},
            {"ok": False, "text": "Requires multi-wave use case; current spec is single-wave"},
        ],
        "detail": {
            "subproblems": "8 per wave (30-min slices)", "parallelism": "Sequential by design",
            "solves": ["Each time-slice's routing decisions optimally"],
            "does_not_solve": ["Cross-slice coupling (e.g. orders in slice 1 affecting slice 3)"],
            "algorithm": [
                {"step": "Slice", "desc": "Divide the dispatch wave into 30-min slices."},
                {"step": "Solve slice", "desc": "Optimise routing for orders ready in this slice."},
                {"step": "Commit", "desc": "Freeze decisions; advance to next slice."},
                {"step": "Repeat", "desc": "Continue until all orders dispatched or wave ends."},
            ],
            "bound": "Sliding optimum; no global bound. Best when slice horizon is short.",
        },
    },
]
