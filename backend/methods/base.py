"""Shared Method ABC plus utilities used by every method.

Naming: keep solver-API specifics out of base.py — each method file talks to
highspy directly with the call signatures that match the pinned version 1.7.2.
Test S5 enforces the pin; if it ever changes, every method file must be
re-validated.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..problem import Problem


# ---------- Result container ----------

@dataclass
class MethodResult:
    """Everything callers need from a solve.

    ``status`` values:
      ``optimal`` — solved to optimality (gap = 0).
      ``gap_reached`` — solver stopped because target gap was reached.
      ``time_limit`` — solver hit wall-clock cap with at least one incumbent.
      ``infeasible`` — model proved infeasible. **For Strict on the supplied
                       sample this would be the V3 critical bug (S1 enforces).**
      ``feasible_no_bound`` — Heuristic produced a feasible solution; no MIP gap.
      ``lower_bound`` — LP relaxation only (no integer solution to extract).
      ``error`` — solver crash or builder exception.
      ``cancelled`` — user clicked cancel.

    ``best_objective`` is total INR of the best incumbent (or LP objective for
    lp_bound). ``best_lower_bound`` is the proven dual bound where available.
    """
    method_id: str
    status: str
    best_objective: float | None = None
    best_lower_bound: float | None = None
    achieved_gap_pct: float | None = None
    wall_time_sec: float = 0.0
    threads_used: int = 1

    # Decomposed cost
    fc_fixed_cost_inr: float = 0.0
    carrier_cost_inr: float = 0.0
    sla_penalty_inr: float = 0.0

    # Variable values (extracted)
    variable_values: dict[str, Any] = field(default_factory=dict)
    row_names: list[str] = field(default_factory=list)

    # Diagnostics
    error_message: str | None = None
    log_excerpt: list[str] = field(default_factory=list)

    # For Order_Assignment / Trip_Plan extraction
    assignments: list[dict[str, Any]] = field(default_factory=list)
    trips: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    node_utilization: list[dict[str, Any]] = field(default_factory=list)

    def get_variable(self, name: str, *index) -> float | None:
        key = (name,) + index if index else name
        return self.variable_values.get(key) if isinstance(key, tuple) else self.variable_values.get(name)


# ---------- Cancellation token ----------

class CancellationToken:
    """Thread-safe flag for cooperative cancellation.

    The solve_runner sets this when /api/cancel/{run_id} is called. Methods
    check it before/after expensive steps and at solver callback boundaries.
    """
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


# ---------- Log capture for SSE ----------

class LogCapture:
    """Append-only log buffer with a watcher hook for SSE streaming.

    Each method logs human-readable progress here ("Building variables…",
    "Adding capacity constraints…"). The runner subscribes via ``add_listener``
    and pushes new lines down the SSE channel.
    """
    def __init__(self) -> None:
        self.lines: list[str] = []
        self._listeners: list[Callable[[str], None]] = []
        self._lock = threading.Lock()
        # Mirror to a python logger so console output also appears
        self._logger = logging.getLogger("mmcvrptw")

    def append(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        stamped = f"[{ts}] {line}"
        with self._lock:
            self.lines.append(stamped)
            listeners = list(self._listeners)
        self._logger.info(line)
        for cb in listeners:
            try:
                cb(stamped)
            except Exception as e:  # noqa: BLE001 — keep listeners isolated
                # Do NOT swallow silently per §16 rule #5 — surface to log
                self._logger.warning(f"SSE listener error: {e}")

    def add_listener(self, cb: Callable[[str], None]) -> None:
        with self._lock:
            self._listeners.append(cb)

    def snapshot(self) -> list[str]:
        with self._lock:
            return list(self.lines)


# ---------- Big-M helper (shared by Strict and Balanced) ----------

def compute_tight_big_m(
    order_ready_time_hr: float,
    ops_sla_deadline_hr: float,
    max_transit_hr: float,
) -> float:
    """Tightest Big-M for the SLA-breach constraint.

    arrival_time[i] − ops_sla_deadline[i] ≤ M · breach[i]

    M = max(1, max_arrival_for_this_order − deadline + 1.0)
    where max_arrival = order_ready + longest_feasible_transit + small slack.

    A generic 1e6 is FORBIDDEN (spec §9.3, §16 rule). Weak Big-Ms cause weak
    LP relaxations and 5-20× slower solves. Test S3 confirms breach is
    constrained, not just declared.
    """
    max_arrival = order_ready_time_hr + max_transit_hr + 0.5
    return max(1.0, max_arrival - ops_sla_deadline_hr + 1.0)


# ---------- Abstract Method ----------

class Method:
    """Abstract base. Each concrete method implements ``solve()``.

    The method receives the canonical ``Problem`` and a few solver controls:
    ``time_cap_sec`` (hard wall-clock cap), ``gap_target`` (e.g. 0.01 for 1%),
    ``threads`` (HiGHS thread count), a ``LogCapture`` for streaming progress,
    and a ``CancellationToken`` for cooperative cancellation.
    """
    id: str = "abstract"
    name: str = "Abstract"
    badge: str = ""

    def solve(
        self,
        problem: Problem,
        time_cap_sec: float = 3600.0,
        gap_target: float = 0.01,
        threads: int = 8,
        log: LogCapture | None = None,
        cancel: CancellationToken | None = None,
    ) -> MethodResult:
        raise NotImplementedError
