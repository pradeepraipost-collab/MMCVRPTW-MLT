"""Roadmap methods 6-10 — stubs that raise NotImplementedError (spec §11).

These appear in the UI as fully-explained cards with disabled Run buttons. The
backend's ``/api/solve`` endpoint returns HTTP 400 when a roadmap method is
requested. The transparency commitment from §16 rule #7: each roadmap card
still carries the full "solves / does NOT solve" content, derived from this
module's class docstrings and the ``METHOD_REGISTRY`` entry.
"""
from __future__ import annotations

from ..problem import Problem
from .base import Method, MethodResult, LogCapture, CancellationToken


_ROADMAP_NOTICE = (
    "This method is documented in spec §11 but not implemented in Phase 1. "
    "See the Configure screen for the full transparency card explaining what "
    "it would solve and what it would NOT solve."
)


class RoadmapMethod(Method):
    id = "roadmap"
    name = "Roadmap method (Phase 2)"
    badge = "ROADMAP"

    def solve(
        self,
        problem: Problem,
        time_cap_sec: float = 0.0,
        gap_target: float = 0.0,
        threads: int = 1,
        log: LogCapture | None = None,
        cancel: CancellationToken | None = None,
    ) -> MethodResult:
        raise NotImplementedError(_ROADMAP_NOTICE)
