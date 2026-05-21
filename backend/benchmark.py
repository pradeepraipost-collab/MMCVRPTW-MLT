"""Stratified-subset benchmark across all 5 enabled methods (spec §12).

Exposed via POST /api/benchmark. Writes results to
runs/<run_id>/benchmark.json in the exact shape documented in the spec.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .methods import METHOD_REGISTRY
from .methods.base import LogCapture
from .problem import Problem, stratified_sample


BENCHMARK_METHODS: list[str] = ["quick", "balanced", "strict", "heuristic", "lp_bound"]


def run_benchmark(
    run_id: str,
    problem: Problem,
    sample_size: int = 1000,
    seed: int = 42,
    output_dir: str | Path = "runs",
) -> dict[str, Any]:
    """Run all 5 enabled methods on a stratified subset and write benchmark.json.

    Returns the payload (also written to disk). Sequential by default — the
    parallel version requires multiprocessing because of the HiGHS GIL.
    """
    sub = stratified_sample(problem, n=sample_size, seed=seed)
    results: list[dict[str, Any]] = []
    for method_id in BENCHMARK_METHODS:
        method_cls = METHOD_REGISTRY[method_id]
        log = LogCapture()
        log.append(f"Benchmark: starting {method_id} on {len(sub.orders)} orders.")
        t0 = time.time()
        try:
            r = method_cls().solve(
                problem=sub,
                time_cap_sec=300.0 if method_id == "strict" else 180.0,
                gap_target=0.01,
                threads=8,
                log=log,
            )
            wall = time.time() - t0
            results.append({
                "method": method_id,
                "cost_inr": r.best_objective,
                "wall_time_sec": round(wall, 1),
                "gap_pct": (round(r.achieved_gap_pct, 2) if r.achieved_gap_pct is not None else None),
                "status": r.status,
            })
        except Exception as e:  # capture, surface (§16 rule #5)
            wall = time.time() - t0
            results.append({
                "method": method_id,
                "cost_inr": None,
                "wall_time_sec": round(wall, 1),
                "gap_pct": None,
                "status": f"error: {type(e).__name__}: {e}",
            })

    payload = {"sample_size": len(sub.orders), "seed": seed, "results": results}
    out = Path(output_dir) / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark.json").write_text(json.dumps(payload, indent=2))
    return payload
