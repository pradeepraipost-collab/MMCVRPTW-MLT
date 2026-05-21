"""One file per method (spec §3 layout). Shared utilities live in base.py.

Method 3 (Strict) is the reference per-order MILP. Methods 1, 2, 4, 5 are
variants/relaxations of that reference. Methods 6-10 are roadmap stubs.
"""
from .base import Method, MethodResult, LogCapture
from .strict import StrictMethod
from .quick import QuickMethod
from .balanced import BalancedMethod
from .heuristic import HeuristicMethod
from .lp_bound import LPBoundMethod
from .roadmap import RoadmapMethod

METHOD_REGISTRY: dict[str, type[Method]] = {
    "strict": StrictMethod,
    "quick": QuickMethod,
    "balanced": BalancedMethod,
    "heuristic": HeuristicMethod,
    "lp_bound": LPBoundMethod,
    "greedy_warmstart": RoadmapMethod,
    "benders": RoadmapMethod,
    "column_generation": RoadmapMethod,
    "lagrangian": RoadmapMethod,
    "rolling_horizon": RoadmapMethod,
}


def get_method(method_id: str) -> type[Method]:
    if method_id not in METHOD_REGISTRY:
        raise ValueError(f"Unknown method_id: {method_id}")
    return METHOD_REGISTRY[method_id]
