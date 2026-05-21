"""Background solver thread + SSE log capture + cooperative cancellation.

One ``SolveRun`` per /api/solve invocation. The FastAPI app keeps a dict keyed
by ``run_id`` and exposes the log via SSE (/api/solve_stream/{run_id}) and
cancellation via /api/cancel/{run_id}.

Per §16 rule #5 we do NOT wrap solver calls in ``except Exception: pass`` —
any exception is captured into ``run.error`` and surfaced to the UI.
"""
from __future__ import annotations

import asyncio
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from .methods import METHOD_REGISTRY, MethodResult
from .methods.base import LogCapture, CancellationToken
from .methods.roadmap import RoadmapMethod
from .problem import Problem


@dataclass
class SolveRun:
    run_id: str
    method_id: str
    problem: Problem
    log: LogCapture = field(default_factory=LogCapture)
    cancel_token: CancellationToken = field(default_factory=CancellationToken)
    status: str = "pending"  # pending | running | done | error | cancelled
    result: MethodResult | None = None
    error: str | None = None
    thread: threading.Thread | None = None
    t_start: float = 0.0
    t_end: float = 0.0

    def elapsed(self) -> float:
        if self.t_start == 0:
            return 0.0
        return (self.t_end or time.time()) - self.t_start


def start_solve(
    runs: dict[str, SolveRun],
    run_id: str,
    method_id: str,
    problem: Problem,
    time_cap_sec: float = 3600.0,
    gap_target: float = 0.01,
    threads: int = 8,
) -> SolveRun:
    """Spawn a background thread for the solve."""
    if method_id not in METHOD_REGISTRY:
        raise ValueError(f"Unknown method_id: {method_id}")
    method_cls = METHOD_REGISTRY[method_id]
    if method_cls is RoadmapMethod:
        raise NotImplementedError(
            f"Method {method_id} is on the Phase-2 roadmap (spec §11). "
            "See the Configure screen for the full explanation."
        )

    run = SolveRun(run_id=run_id, method_id=method_id, problem=problem)
    runs[run_id] = run

    def _worker():
        run.t_start = time.time()
        run.status = "running"
        run.log.append(f"Starting {method_id} solve (run_id={run_id}, time_cap={time_cap_sec}s, "
                       f"gap_target={gap_target*100:.1f}%, threads={threads}).")
        try:
            method = method_cls()
            run.result = method.solve(
                problem=problem,
                time_cap_sec=time_cap_sec,
                gap_target=gap_target,
                threads=threads,
                log=run.log,
                cancel=run.cancel_token,
            )
            if run.cancel_token.is_cancelled() or (run.result and run.result.status == "cancelled"):
                run.status = "cancelled"
            elif run.result and run.result.status in ("error",):
                run.status = "error"
                run.error = run.result.error_message
            else:
                run.status = "done"
        except NotImplementedError as e:
            run.status = "error"
            run.error = str(e)
            run.log.append(f"ERROR: {e}")
        except Exception as e:  # noqa: BLE001 — capture, surface, do not swallow
            run.status = "error"
            run.error = f"{type(e).__name__}: {e}"
            run.log.append(f"ERROR: {run.error}")
            run.log.append("Traceback:")
            for line in traceback.format_exc().splitlines():
                run.log.append(f"  {line}")
        finally:
            run.t_end = time.time()
            run.log.append(f"Run {run_id} finished with status={run.status} "
                           f"in {run.elapsed():.1f}s.")

    th = threading.Thread(target=_worker, name=f"solve-{run_id}", daemon=True)
    run.thread = th
    th.start()
    return run


def cancel_run(runs: dict[str, SolveRun], run_id: str) -> bool:
    if run_id not in runs:
        return False
    run = runs[run_id]
    if run.status not in ("pending", "running"):
        return False
    run.cancel_token.cancel()
    run.log.append("Cancel requested. The current solver step will stop at its next "
                   "checkpoint (≤5s). Note: HiGHS itself doesn't support mid-solve "
                   "Python interrupts in 1.7.2; if we're mid-solve, cancellation "
                   "takes effect after the current MIP node finishes.")
    return True


async def sse_log_stream(run: SolveRun):
    """Async generator emitting SSE events for new log lines, plus periodic
    status frames carrying incumbent / bound / gap.

    Format (sse-starlette): yields dicts with 'event' and 'data' keys.
    """
    # Send everything already buffered
    cursor = 0
    while True:
        snapshot = run.log.snapshot()
        if cursor < len(snapshot):
            for line in snapshot[cursor:]:
                yield {"event": "log", "data": line}
            cursor = len(snapshot)
        # Periodic status frame
        result = run.result
        status_payload = {
            "status": run.status,
            "elapsed_sec": round(run.elapsed(), 1),
            "incumbent": (result.best_objective if result else None),
            "bound": (result.best_lower_bound if result else None),
            "gap_pct": (result.achieved_gap_pct if result else None),
        }
        yield {"event": "status", "data": str(status_payload)}
        if run.status in ("done", "error", "cancelled"):
            yield {"event": "end", "data": run.status}
            return
        await asyncio.sleep(0.5)
