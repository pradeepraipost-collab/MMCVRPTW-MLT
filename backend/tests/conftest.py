"""Shared fixtures: project paths + helpers to load the supplied problem.

The supplied master Excel and output template live at the project root; tests
locate them by walking up from this file.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from backend.ingest import read_master_workbook
from backend.problem import (
    Problem, Order, build_problem, stratified_sample,
    LANE_FC_SC, LANE_SC_DS, LANE_FC_DS,
)


def _project_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return _project_root()


@pytest.fixture(scope="session")
def master_path(project_root) -> Path:
    return project_root / "MMCVRPTW_MLT_MasterData_V4.xlsx"


@pytest.fixture(scope="session")
def template_path(project_root) -> Path:
    return project_root / "MMCVRPTW_MLT_OutputTemplate_V4.xlsx"


@pytest.fixture(scope="session")
def problem(master_path) -> Problem:
    result = read_master_workbook(master_path)
    assert result.ok, f"Master Excel failed validation: {[e.to_dict() for e in result.errors]}"
    return build_problem(result.frames)


@pytest.fixture
def small_problem(problem) -> Problem:
    """1k-order stratified subset used by S2 and S6."""
    return stratified_sample(problem, n=1000, seed=42)


def build_synthetic_impossible_problem(problem: Problem) -> tuple[Problem, str]:
    """Build a 5-order problem where one order has an Ops_SLA_Deadline that
    cannot possibly be met by any feasible route. Used by test S3 to confirm
    breach[i] is wired (not just declared)."""
    from dataclasses import replace
    impossible_order_id = "ORD-IMPOSSIBLE-001"
    base_orders = problem.orders[:4]
    # Construct an order whose ready time is the wave start and whose deadline
    # is one minute later — no route can complete in that time.
    o_impossible = replace(
        problem.orders[0],
        order_id=impossible_order_id,
        order_ready_time_hr=problem.dispatch_wave.start_hr,
        ops_sla_deadline_hr=problem.dispatch_wave.start_hr + 1.0 / 60.0,
        total_penalty_inr=10_000.0,
    )
    sub = Problem(
        wave_date=problem.wave_date,
        fcs=problem.fcs, scs=problem.scs, dses=problem.dses,
        vehicles=problem.vehicles, carriers=problem.carriers, lanes=problem.lanes,
        orders=list(base_orders) + [o_impossible],
        order_wave=problem.order_wave, dispatch_wave=problem.dispatch_wave,
        node_schedule=problem.node_schedule,
        ds_dispatch_waves=problem.ds_dispatch_waves,
        sla_config=problem.sla_config, penalty_config=problem.penalty_config,
        pick_pack_config=problem.pick_pack_config,
        lanes_by_od=problem.lanes_by_od,
        multi_stop_eligible_carrier_count=problem.multi_stop_eligible_carrier_count,
    )
    return sub, impossible_order_id
