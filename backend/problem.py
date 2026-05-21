"""Typed Problem dataclasses built from the raw master DataFrames.

Methods consume ``Problem`` directly rather than re-parsing the workbook. This
keeps ingest concerns (sheet structure, validation) out of the solver code
and gives every method the same canonical view of the network.

The wave date is fixed by inspecting Order_Data; the active dispatch wave's
start/end define the dispatch window in absolute hours-since-midnight on that
date. All times are normalised to ``hours since wave_start_midnight`` (a single
float per order/trip) so the MILP is a clean continuous formulation.

The Eligible_Lane_Types field on Carriers uses 'FC_DIRECT' to refer to FC→DS
lanes; the Lane_Distance_Matrix uses 'FC_DS' for those same lanes. The function
``_normalise_lane_type`` resolves this so callers can use a single consistent
lane-type vocabulary downstream.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd


# ---------- Lane type vocabulary ----------
# Internal lane-type strings. Carrier_Master uses 'FC_DIRECT' for FC→DS direct;
# Lane_Distance_Matrix uses 'FC_DS'. We normalise both into LANE_FC_DS below.

LANE_FC_SC = "FC_SC"
LANE_SC_DS = "SC_DS"
LANE_FC_DS = "FC_DS"   # FC→DS direct (carrier docs call this FC_DIRECT)
LANE_SC_SC = "SC_SC"
ALL_LANE_TYPES = (LANE_FC_SC, LANE_SC_DS, LANE_FC_DS, LANE_SC_SC)

_LANE_TYPE_ALIASES = {
    "FC_DIRECT": LANE_FC_DS,
    "FC_DS": LANE_FC_DS,
    "FC_SC": LANE_FC_SC,
    "SC_DS": LANE_SC_DS,
    "SC_SC": LANE_SC_SC,
}


def _normalise_lane_type(s: str) -> str:
    return _LANE_TYPE_ALIASES.get(str(s).strip().upper(), str(s).strip())


def _parse_eligible_lane_types(field_value: str | None) -> frozenset[str]:
    if field_value is None or (isinstance(field_value, float) and pd.isna(field_value)):
        return frozenset()
    return frozenset(_normalise_lane_type(p) for p in str(field_value).split("|") if p.strip())


# ---------- Master entities ----------

@dataclass(frozen=True)
class FC:
    fc_id: str
    city: str
    region: str
    lat: float
    lon: float
    fixed_cost_per_wave_inr: float
    max_concurrent_trips: int
    throughput_parcels_per_hr: int
    surge_throughput_parcels_per_hr: int
    dock_bays_outbound: int
    wave_staging_capacity_parcels: int


@dataclass(frozen=True)
class SC:
    sc_id: str
    city: str
    sc_type: str  # Automated | Manual
    lat: float
    lon: float
    throughput_parcels_per_hr: int
    max_inbound_docks: int
    max_concurrent_outbound_trucks: int
    max_parcels_staging: int


@dataclass(frozen=True)
class DS:
    ds_id: str
    city: str
    region: str
    lat: float
    lon: float
    normal_capacity_parcels: int
    ds_type: str  # Active | Minor
    inbound_dock_bays: int
    unload_turnaround_min: float


@dataclass(frozen=True)
class Vehicle:
    vehicle_type: str
    weight_capacity_kg: float
    volume_capacity_m3: float
    parcel_capacity: int
    min_load_pct_ftl: float   # e.g. 75
    ptl_min_weight_kg: float
    ptl_min_vol_m3: float
    eligible_lane_types: frozenset[str]


@dataclass(frozen=True)
class Carrier:
    """One row of Carrier_Master = one (carrier, vehicle_type, load_type) combo."""
    carrier_id: str
    carrier_name: str
    vehicle_type: str
    load_type: str  # FTL | PTL | LTL | Courier
    ftl_rate_inr: float | None
    ptl_rate_inr: float | None
    ltl_rate_inr_per_kg: float | None
    courier_rate_inr_per_parcel: float | None
    courier_max_weight_kg: float | None
    courier_max_vol_m3: float | None
    multi_stop_eligible: bool
    max_stops: int
    stop_delay_min: float
    max_concentration_pct: float
    eligible_lane_types: frozenset[str]
    active: bool


@dataclass(frozen=True)
class Lane:
    origin: str
    destination: str
    distance_km: float
    transit_hr: float
    lane_type: str
    max_detour_pct: float


@dataclass(frozen=True)
class Order:
    order_id: str
    origin_fc: str
    destination_ds: str
    weight_kg: float
    volume_m3: float
    priority: str  # Prime | Standard
    sla_tier: str  # Same-day | Next-day | 2-day
    fc_region: str
    ds_city: str
    order_ready_time_hr: float    # hours from wave midnight
    ops_sla_deadline_hr: float    # hours from wave midnight
    customer_sla_hr: float
    total_penalty_inr: float


@dataclass(frozen=True)
class Wave:
    wave_id: str
    start_hr: float
    end_hr: float


@dataclass
class Problem:
    """Canonical typed view of the loaded master + orders."""
    wave_date: datetime
    fcs: dict[str, FC]
    scs: dict[str, SC]
    dses: dict[str, DS]
    vehicles: dict[str, Vehicle]
    carriers: list[Carrier]              # 25-ish rows; key is (carrier_id, vehicle, load_type)
    lanes: list[Lane]
    orders: list[Order]
    order_wave: Wave
    dispatch_wave: Wave
    node_schedule: pd.DataFrame
    ds_dispatch_waves: pd.DataFrame
    sla_config: pd.DataFrame
    penalty_config: pd.DataFrame
    pick_pack_config: pd.DataFrame
    # Convenience: lanes indexed by (origin, destination)
    lanes_by_od: dict[tuple[str, str], Lane] = field(default_factory=dict)

    # Derived
    multi_stop_eligible_carrier_count: int = 0

    @property
    def courier_max_weight_kg(self) -> float:
        for c in self.carriers:
            if c.load_type == "Courier" and c.courier_max_weight_kg is not None:
                return float(c.courier_max_weight_kg)
        return 2.0  # spec §1 default

    @property
    def courier_max_vol_m3(self) -> float:
        for c in self.carriers:
            if c.load_type == "Courier" and c.courier_max_vol_m3 is not None:
                return float(c.courier_max_vol_m3)
        return 0.012

    @property
    def courier_rate_inr(self) -> float:
        for c in self.carriers:
            if c.load_type == "Courier" and c.courier_rate_inr_per_parcel is not None:
                return float(c.courier_rate_inr_per_parcel)
        return 85.0

    def lane(self, origin: str, destination: str) -> Lane | None:
        return self.lanes_by_od.get((origin, destination))


# ---------- Builder ----------

def _hour(time_str: str | float, base_date: datetime) -> float:
    """Convert 'HH:MM' or 'HH:MM (prev)' string to hours since base_date midnight."""
    if time_str is None or (isinstance(time_str, float) and pd.isna(time_str)):
        return 0.0
    s = str(time_str).strip()
    prev = False
    if "(prev)" in s:
        prev = True
        s = s.replace("(prev)", "").strip()
    parts = s.split(":")
    h = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 0
    val = h + m / 60.0
    if prev:
        val -= 24.0
    return val


def _hours_from_datetime(dt_value, base_date: datetime) -> float:
    """Convert a pandas/Excel datetime cell to hours since base_date midnight."""
    if pd.isna(dt_value):
        return 0.0
    if isinstance(dt_value, str):
        dt = pd.to_datetime(dt_value)
    else:
        dt = pd.Timestamp(dt_value)
    delta = dt.to_pydatetime() - base_date
    return delta.total_seconds() / 3600.0


def build_problem(frames: dict[str, pd.DataFrame]) -> Problem:
    """Turn the raw frames from ingest.read_master_workbook into a Problem."""
    # --- Wave date is inferred from Order_Data (all orders are on the same day per §6) ---
    od_raw = frames["Order_Data"]
    first_dt = pd.to_datetime(od_raw["Order_Placed_Time"].iloc[0])
    wave_date = datetime(first_dt.year, first_dt.month, first_dt.day)

    # --- FCs ---
    fcs: dict[str, FC] = {}
    for r in frames["Origin_Master"].itertuples(index=False):
        fcs[r.FC_ID] = FC(
            fc_id=r.FC_ID, city=r.City, region=r.Region,
            lat=float(r.Latitude), lon=float(r.Longitude),
            fixed_cost_per_wave_inr=float(r.Fixed_Cost_per_Wave_INR),
            max_concurrent_trips=int(r.Max_Concurrent_Trips),
            throughput_parcels_per_hr=int(r.FC_Throughput_parcels_per_hr),
            surge_throughput_parcels_per_hr=int(r.FC_Surge_Throughput_parcels_hr),
            dock_bays_outbound=int(r.Dock_Bays_Outbound),
            wave_staging_capacity_parcels=int(r.Wave_Staging_Capacity_parcels),
        )

    # --- SCs ---
    scs: dict[str, SC] = {}
    for r in frames["Intermediate_Master"].itertuples(index=False):
        scs[r.SC_ID] = SC(
            sc_id=r.SC_ID, city=r.City, sc_type=r.Type,
            lat=float(r.Latitude), lon=float(r.Longitude),
            throughput_parcels_per_hr=int(r.Throughput_parcels_per_hr),
            max_inbound_docks=int(r.Max_Inbound_Docks),
            max_concurrent_outbound_trucks=int(r.Max_Concurrent_Outbound_Trucks),
            max_parcels_staging=int(r.Max_Parcels_Staging),
        )

    # --- DSes ---
    dses: dict[str, DS] = {}
    for r in frames["Destination_Master"].itertuples(index=False):
        dses[r.DS_ID] = DS(
            ds_id=r.DS_ID, city=r.City, region=r.Region,
            lat=float(r.Latitude), lon=float(r.Longitude),
            normal_capacity_parcels=int(r.Normal_Capacity_parcels),
            ds_type=r.DS_Type,
            inbound_dock_bays=int(r.Inbound_Dock_Bays),
            unload_turnaround_min=float(r.Unload_Turnaround_min),
        )

    # --- Vehicles ---
    vehicles: dict[str, Vehicle] = {}
    for r in frames["Vehicle_Types"].itertuples(index=False):
        vehicles[r.Vehicle_Type] = Vehicle(
            vehicle_type=r.Vehicle_Type,
            weight_capacity_kg=float(r.Weight_Capacity_kg),
            volume_capacity_m3=float(r.Volume_Capacity_m3),
            parcel_capacity=int(r.Parcel_Capacity),
            min_load_pct_ftl=float(r.Min_Load_pct_FTL),
            ptl_min_weight_kg=float(r.PTL_Min_Weight_kg) if not pd.isna(r.PTL_Min_Weight_kg) else 0.0,
            ptl_min_vol_m3=float(r.PTL_Min_Vol_m3) if not pd.isna(r.PTL_Min_Vol_m3) else 0.0,
            eligible_lane_types=_parse_eligible_lane_types(r.Eligible_Lane_Types),
        )

    # --- Carriers (one row per carrier × vehicle × load_type) ---
    carriers: list[Carrier] = []
    cm = frames["Carrier_Master"]
    for r in cm.itertuples(index=False):
        carriers.append(Carrier(
            carrier_id=str(r.Carrier_ID),
            carrier_name=str(r.Carrier_Name),
            vehicle_type=str(r.Vehicle_Type),
            load_type=str(r.Load_Type),
            ftl_rate_inr=float(r.FTL_Rate_INR_per_trip) if not pd.isna(r.FTL_Rate_INR_per_trip) else None,
            ptl_rate_inr=float(r.PTL_Rate_INR_per_trip) if not pd.isna(r.PTL_Rate_INR_per_trip) else None,
            ltl_rate_inr_per_kg=float(r.LTL_Rate_INR_per_kg) if not pd.isna(r.LTL_Rate_INR_per_kg) else None,
            courier_rate_inr_per_parcel=float(r.Courier_Rate_INR_per_parcel) if not pd.isna(r.Courier_Rate_INR_per_parcel) else None,
            courier_max_weight_kg=float(r.Courier_Max_Weight_kg) if not pd.isna(r.Courier_Max_Weight_kg) else None,
            courier_max_vol_m3=float(r.Courier_Max_Vol_m3) if not pd.isna(r.Courier_Max_Vol_m3) else None,
            multi_stop_eligible=bool(int(r.Multi_Stop_Eligible)) if not pd.isna(r.Multi_Stop_Eligible) else False,
            max_stops=int(r.Max_Stops) if not pd.isna(r.Max_Stops) else 1,
            stop_delay_min=float(r.Stop_Delay_min) if not pd.isna(r.Stop_Delay_min) else 0.0,
            max_concentration_pct=float(r.Max_Concentration_pct) if not pd.isna(r.Max_Concentration_pct) else 100.0,
            eligible_lane_types=_parse_eligible_lane_types(r.Eligible_Lane_Types),
            active=bool(int(r.Carrier_Active)) if not pd.isna(r.Carrier_Active) else True,
        ))

    # --- Lanes ---
    lanes: list[Lane] = []
    lanes_by_od: dict[tuple[str, str], Lane] = {}
    for r in frames["Lane_Distance_Matrix"].itertuples(index=False):
        lt = _normalise_lane_type(r.Lane_Type)
        ln = Lane(
            origin=str(r.Origin_Node), destination=str(r.Destination_Node),
            distance_km=float(r.Road_Distance_km),
            transit_hr=float(r.Mean_Transit_Time_hr),
            lane_type=lt,
            max_detour_pct=float(r.Max_Detour_pct) if not pd.isna(r.Max_Detour_pct) else 0.0,
        )
        lanes.append(ln)
        lanes_by_od[(ln.origin, ln.destination)] = ln

    # --- Waves ---
    def _active_wave(df: pd.DataFrame, start_col: str, end_col: str) -> Wave:
        active = df[df["Active_Wave"] == 1]
        if len(active) == 0:
            raise ValueError(f"No active wave in {df.columns}")
        row = active.iloc[0]
        return Wave(
            wave_id=str(row["Wave_ID"]),
            start_hr=_hour(row[start_col], wave_date),
            end_hr=_hour(row[end_col], wave_date),
        )

    order_wave = _active_wave(frames["Origin_Order_Waves"], "Order_Window_Start", "Order_Window_End_Cutoff")
    dispatch_wave = _active_wave(frames["Origin_Dispatch_Waves"], "Dispatch_Start", "Dispatch_End")

    # --- Orders ---
    orders: list[Order] = []
    for r in frames["Order_Data"].itertuples(index=False):
        orders.append(Order(
            order_id=str(r.Order_ID),
            origin_fc=str(r.Origin_Node),
            destination_ds=str(r.Destination_Node),
            weight_kg=float(r.Weight_kg),
            volume_m3=float(r.Volume_m3),
            priority=str(r.Priority),
            sla_tier=str(r.SLA_Tier),
            fc_region=str(r.FC_Region),
            ds_city=str(r.DS_City),
            order_ready_time_hr=_hours_from_datetime(r.Order_Ready_Time, wave_date),
            ops_sla_deadline_hr=_hours_from_datetime(r.Ops_SLA_Deadline, wave_date),
            customer_sla_hr=float(r.SLA_hrs),
            total_penalty_inr=float(r.Total_Penalty_INR),
        ))

    p = Problem(
        wave_date=wave_date,
        fcs=fcs, scs=scs, dses=dses,
        vehicles=vehicles, carriers=carriers, lanes=lanes,
        orders=orders,
        order_wave=order_wave, dispatch_wave=dispatch_wave,
        node_schedule=frames.get("Node_Schedule", pd.DataFrame()),
        ds_dispatch_waves=frames.get("DS_Dispatch_Waves", pd.DataFrame()),
        sla_config=frames.get("SLA_Config", pd.DataFrame()),
        penalty_config=frames.get("Penalty_Config", pd.DataFrame()),
        pick_pack_config=frames.get("Pick_Pack_Config", pd.DataFrame()),
        lanes_by_od=lanes_by_od,
        multi_stop_eligible_carrier_count=sum(1 for c in carriers if c.multi_stop_eligible),
    )
    return p


# ---------- Subsetting (for benchmark + tests) ----------

def stratified_sample(p: Problem, n: int, seed: int = 42) -> Problem:
    """Return a Problem with ``n`` orders sampled, stratified by (origin_fc, priority).

    Other entities (FCs, lanes, etc.) are unchanged — only the order list is
    subset. Used by the benchmark (§12) and self-test S2.
    """
    import random
    if n >= len(p.orders):
        return p
    rnd = random.Random(seed)
    # Group orders by (origin_fc, priority) so sample preserves distribution
    groups: dict[tuple[str, str], list[Order]] = {}
    for o in p.orders:
        groups.setdefault((o.origin_fc, o.priority), []).append(o)
    # Per-group quota proportional to share
    total = len(p.orders)
    out: list[Order] = []
    for key, ords in groups.items():
        share = len(ords) / total
        take = max(1, int(round(share * n)))
        rnd.shuffle(ords)
        out.extend(ords[:take])
    # Trim to exactly n
    rnd.shuffle(out)
    out = out[:n]
    return Problem(
        wave_date=p.wave_date,
        fcs=p.fcs, scs=p.scs, dses=p.dses,
        vehicles=p.vehicles, carriers=p.carriers, lanes=p.lanes,
        orders=out,
        order_wave=p.order_wave, dispatch_wave=p.dispatch_wave,
        node_schedule=p.node_schedule,
        ds_dispatch_waves=p.ds_dispatch_waves,
        sla_config=p.sla_config,
        penalty_config=p.penalty_config,
        pick_pack_config=p.pick_pack_config,
        lanes_by_od=p.lanes_by_od,
        multi_stop_eligible_carrier_count=p.multi_stop_eligible_carrier_count,
    )


# ---------- Candidate routes ----------

@dataclass(frozen=True)
class HubSpokeRoute:
    """A hub-spoke candidate: FC → SC → DS via two trips."""
    order_id: str
    fc: str
    sc: str
    ds: str
    transit_hr: float


@dataclass(frozen=True)
class DirectRoute:
    """An FC → DS direct candidate."""
    order_id: str
    fc: str
    ds: str
    transit_hr: float


def enumerate_routes_for_order(
    p: Problem, o: Order, sla_slack_hr: float = 0.5
) -> tuple[list[HubSpokeRoute], list[DirectRoute], bool]:
    """Enumerate feasible (hub_spoke, fc_direct) routes plus courier eligibility.

    Lane pruning (per §16 rule #1): skip routes whose minimum transit alone
    already misses Ops_SLA_Deadline by more than ``sla_slack_hr``. This is the
    legitimate alternative to V3's banned ``PER_LANE_CARRIER_CAP`` — we narrow
    the candidate set by SLA, not by an arbitrary carrier limit.
    """
    hub: list[HubSpokeRoute] = []
    direct: list[DirectRoute] = []

    fc = o.origin_fc
    ds = o.destination_ds

    # Direct: lane FC → DS exists?
    direct_lane = p.lane(fc, ds)
    if direct_lane is not None and direct_lane.lane_type == LANE_FC_DS:
        # Minimum dispatch is order_ready_time, but also bounded below by wave start
        depart = max(o.order_ready_time_hr, p.dispatch_wave.start_hr)
        arrival = depart + direct_lane.transit_hr
        if arrival <= o.ops_sla_deadline_hr + 24.0:  # generous filter
            direct.append(DirectRoute(o.order_id, fc, ds, direct_lane.transit_hr))

    # Hub-spoke: FC → any SC with a Lane to DS
    for sc_id in p.scs.keys():
        mm = p.lane(fc, sc_id)
        lm = p.lane(sc_id, ds)
        if mm is None or lm is None:
            continue
        if mm.lane_type != LANE_FC_SC or lm.lane_type != LANE_SC_DS:
            continue
        total = mm.transit_hr + lm.transit_hr + 0.5  # 30 min SC handling floor (§7-12)
        depart = max(o.order_ready_time_hr, p.dispatch_wave.start_hr)
        arrival = depart + total
        if arrival <= o.ops_sla_deadline_hr + 24.0:
            hub.append(HubSpokeRoute(o.order_id, fc, sc_id, ds, total))

    courier_eligible = (
        o.weight_kg <= p.courier_max_weight_kg + 1e-9
        and o.volume_m3 <= p.courier_max_vol_m3 + 1e-9
    )
    return hub, direct, courier_eligible
