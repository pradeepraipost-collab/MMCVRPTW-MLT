# MMCVRPTW-MLT — Design Summary V4

**Multi-Echelon Multi-Commodity Capacitated Vehicle Routing Problem with Time Windows and Multiple Load Types**

MILP formulation for wave-based ecommerce fulfilment network optimisation. **Local Python + HiGHS solver** with a **multi-method picker** that lets users trade solve-time against proximity-to-optimum on the same problem instance.

This document supersedes V3. Material changes are flagged inline as **[V4]**.

---

## 1. Problem class

| Component | Definition |
|---|---|
| Multi-Echelon | 3-tier network: FC → SC → DS |
| Multi-Commodity | Order types Prime / Standard with distinct SLA tiers |
| Capacitated | Hard caps at FC throughput, SC staging, DS receiving, truck weight / volume / parcel count |
| Vehicle Routing | Carrier + vehicle assignment with endogenous multi-stop sequencing |
| Time Windows | Order wave, dispatch wave, `Ops_SLA_Deadline` (= Customer_SLA − 4 hrs) |
| Multiple Load Types | FTL (≥75% fill), PTL (≥ carrier minimum), LTL (per-kg), Courier (FC_DIRECT, ≤2kg & ≤0.012m³) |
| Route Options | **Hub-Spoke (FC→SC→DS), FC-Direct (FC→DS), Courier (FC→customer)** — three first-class alternatives, optimizer picks cheapest subject to SLA |
| Formulation | Mixed Integer Linear Program (MILP) |

---

## 2. Objective function

```
MINIMISE  Total_FC_Fixed_Cost + Total_Carrier_Cost + Total_SLA_Penalty
```

SLA is enforced as a **soft penalty**. Solver may breach `Ops_SLA_Deadline` if savings exceed `Total_Penalty_INR`. **The `breach[i]` binary MUST be tied to a hard constraint linking arrival_time[i] − ops_sla_deadline[i] ≤ M·breach[i]; a dangling breach variable in the objective is a critical bug** (this is what V3 shipped with, do not repeat).

---

## 3. Decision variables (strict per-order formulation)

| Type | Variable | Meaning |
|---|---|---|
| Binary | `x_mm[i, f, s, c, v, ℓ, t]` | Order `i` on FC `f` → SC `s` middle-mile trip `t` |
| Binary | `y_lm[i, s, d, c, v, ℓ, t]` | Order `i` on SC `s` → DS `d` last-mile trip `t` |
| Binary | `w_fd[i, f, d, c, v, ℓ, t]` | Order `i` on FC `f` → DS `d` direct trip `t` |
| Binary | `z[i]` | Order `i` shipped FC_DIRECT courier |
| Binary | `u[t]` | Trip `t` is used |
| Binary | `ftl[t]`, `ptl[t]`, `ltl[t]` | Load type of trip `t` |
| Binary | `a[t, n1, n2]` | Multi-stop arc on trip `t` (MTZ) |
| Continuous | `p[t, n]` | Position of node `n` on trip `t` (MTZ subtour elim) |
| Continuous | `load_kg[t]`, `load_vol[t]`, `load_parcels[t]` | Trip totals |
| Continuous | `arrival_time[i]` | Order arrival timestamp at destination |
| Binary | `breach[i]` | 1 if `arrival_time[i] > ops_sla_deadline[i]` |

---

## 4. Scale (unchanged from V3)

| Component | Value | Source |
|---|---|---|
| FCs | 15, real coordinates and capacities (1,000–1,800 parcels/hr each) | `Origin_Master` sheet |
| SCs | 10 (4 Automated @ 28,000/hr, 6 Manual @ 4,500/hr) | `Intermediate_Master` sheet |
| DSes | 200 (57 active @ 40 parcels/wave, 143 minor @ 8 parcels/wave) | `Destination_Master` sheet |
| Lanes | 5,240 (FC→SC: 150, SC→DS: 2,000, FC→DS direct: 3,000, SC→SC: 90) | `Lane_Distance_Matrix` sheet |
| Default wave order volume | 10,000 orders | `Order_Data` sheet (in same workbook) |
| Tested range | 5,000–30,000 orders | — |

---

## 5. Master Excel — **15 sheets, single workbook upload [V4]**

**[V4 change]** The user now uploads ONE Excel file containing all 14 master sheets PLUS an `Order_Data` sheet at position 15. This reverses the V3 decision to externalize orders to a CSV — V4 returns to a single-file upload for simpler UX.

### Sheet inventory (in order)

| # | Sheet | Rows | Description |
|---|---|---|---|
| 1 | Project_Overview | — | Cover sheet with V4 changelog |
| 2 | Origin_Master | 15 FCs | MUM, DEL, BLR, HYD, CHE, PUN, AHM, KOL, LKN, JPR, IND, NAG, GUW, BHU, COK |
| 3 | Intermediate_Master | 10 SCs | 4 Automated (MUM, DEL, BLR, HYD) + 6 Manual (CHE, KOL, AHM, PUN, LKN, IND) |
| 4 | Destination_Master | 200 DSes | Distributed across 20 cities; 57 active + 143 minor |
| 5 | Vehicle_Types | 5 | 40ft, 20ft, 14ft, Ace, Courier — real capacities (2Wheeler removed in V4: doesn't fit the 3 V4 route types) |
| 6 | Carrier_Master | 25 rows / 6 unique carriers | Carrier × Vehicle × Load_Type rows |
| 7 | SLA_Config | 80 | FC_Region × DS_City × Priority → SLA hours |
| 8 | Penalty_Config | 6 | WISMO + Compensation + Repurchase_Risk → Total_Penalty_INR |
| 9 | Pick_Pack_Config | 12 rows | 5 weight bins + 5 vol bins + 2 priority multipliers |
| 10 | Origin_Order_Waves | 6 | Order placement windows; Wave 3 active by default |
| 11 | Origin_Dispatch_Waves | 6 | Truck dispatch windows; Wave 3 active by default |
| 12 | Node_Schedule | 120 | FC waves (90) + SC waves (30) |
| 13 | DS_Dispatch_Waves | 1,200 | 200 DS × 6 waves |
| 14 | Lane_Distance_Matrix | 5,240 | Includes 3,000 FC→DS direct lanes |
| 15 | **Order_Data** **[V4]** | varies (10,000 in sample) | **20 columns, all populated. App rejects uploads with < 20 columns.** |

### Header structure — uniform across all 15 sheets

Every sheet: **row 1 = banner, row 2 = column names, row 3+ = data.**

Read with `pandas.read_excel(..., header=1)`. The literal "skiprows=2" wording from earlier docs is **wrong** — it would skip both the banner and the headers. Confirm by inspecting any sheet manually before coding the loader.

---

## 6. Order_Data sheet — 20 columns required [V4]

**[V4]** Orders are no longer a separate CSV. They live in the 15th sheet of the master workbook. The app must:

1. Verify Sheet 15 exists and is named exactly `Order_Data`.
2. Verify it has all 20 columns listed below, in order, with non-null values in every cell.
3. **Reject** the upload (with a clear error message in the UI) if any column is missing or if any cell is null. Do NOT silently derive missing values.

### Schema (20 columns, all populated)

| # | Column | Notes |
|---|---|---|
| 1 | Order_ID | Unique |
| 2 | Origin_Node | Must match an FC_ID in Origin_Master |
| 3 | Destination_Node | Must match a DS_ID in Destination_Master |
| 4 | Destination_Node_Pincode | |
| 5 | Weight_kg | |
| 6 | Volume_m3 | |
| 7 | Order_Placed_Time | Format: YYYY-MM-DD HH:MM |
| 8 | Customer_SLA_Deadline | |
| 9 | Priority | Prime / Standard |
| 10 | PickPack_Time_min | Derived from Pick_Pack_Config |
| 11 | Order_Ready_Time | Placed + PickPack |
| 12 | FC_Region | From Origin_Master |
| 13 | DS_City | From Destination_Master |
| 14 | SLA_hrs | From SLA_Config |
| 15 | SLA_Tier | Same-day (≤14h) / Next-day (≤40h) / 2-day |
| 16 | WISMO_Cost_INR | From Penalty_Config |
| 17 | Compensation_INR | |
| 18 | Repurchase_Risk_INR | |
| 19 | Total_Penalty_INR | |
| 20 | Ops_SLA_Deadline | Customer_SLA − 4 hrs |

### Sample distribution (in the supplied 10,000-order Order_Data sheet)

- 10,000 orders for Wave 3 (placed 04:00–08:00 on 2026-05-20)
- FC origin: proportional to FC throughput (MUM/CHE/HYD heaviest)
- DS destination: heavy metro skew (MUM/DEL/BLR/HYD/CHE = ~63% of orders)
- Prime/Standard mix: 30% / 70%
- Weight distribution: 60% <2kg, 30% 2–5kg, 8% 5–15kg, 2% >15kg
- SLA Tier mix: 65% Same-day, 35% Next-day

---

## 7. Constraint set (strict spec — all required)

1. **Coverage** — every order is shipped exactly once via one of three routes:
   - `Σ z[i] + Σ x_mm[i,...] + Σ w_fd[i,...] = 1` for each order `i`
   - Hub-spoke path: `Σ x_mm[i,f,s,...] = Σ y_lm[i,s,d,...]` (must continue from same SC)
2. **Flow consistency** — same SC on middle-mile and last-mile when hub-spoke chosen.
3. **Trip activation** — order can ride only on a used trip.
4. **Trip capacities** — `load_kg[t] ≤ Weight_Capacity_kg[v]`, same for volume and parcel count. Values from Vehicle_Types directly, no scaling.
5. **Load type rules (linearised disjunction)** —
   - `ftl[t] = 1` ⇒ `load_kg[t] ≥ 0.75 · Weight_Capacity_kg[v]`
   - `ptl[t] = 1` ⇒ `PTL_Min_Weight_kg[v] ≤ load_kg[t] < 0.75 · Weight_Capacity_kg[v]`
   - `ltl[t] = 1` ⇒ `load_kg[t] < PTL_Min_Weight_kg[v]`
   - `ftl[t] + ptl[t] + ltl[t] = u[t]`
   - ε-tightening (ε = 1 kg) for strict inequalities.
6. **Courier eligibility** — `z[i] = 1` only if `Weight_kg[i] ≤ Courier_max_wt` AND `Volume_m3[i] ≤ Courier_max_vol`. Ineligible orders have `z[i]` removed from the model.
7. **Node capacity per wave** — FC, SC, DS each enforce per-wave caps (from master sheets).
8. **Concurrent trips** — FC ≤ `Max_Concurrent_Trips`; SC ≤ `Max_Concurrent_Outbound_Trucks`; DS ≤ `Inbound_Dock_Bays`.
9. **Carrier concentration** — orders via carrier `c` ≤ `Max_Concentration_pct / 100 × total_orders`.
10. **Lane eligibility** — variables exist only for active (origin, dest) lanes with `Eligible_Lane_Types` matching the vehicle.
11. **Multi-stop routing (MTZ)** — applies to last-mile (SC→DS) **and FC→DS direct** trips when carrier `Multi_Stop_Eligible=1`.
12. **Time windows** — FC dispatch in active `Origin_Dispatch_Waves`; SC processing in `Node_Schedule`; DS arrival in `DS_Dispatch_Waves`. Same-city lanes get **5 km / 30 min floor** at model-build time.
13. **SLA breach (soft, MUST be wired)** — `arrival_time[i] − Ops_SLA_Deadline[i] ≤ M · breach[i]` with **tightened Big-M** (compute per-order based on max conceivable transit time, not a generic 1e6). **The breach variable must influence the objective only when this constraint is active; a breach binary with no constraint is a critical bug.**

---

## 8. Objective (with FC-Direct term)

```
Minimise:
    Σ_f (FC_Fixed_Cost[f] × FC_used[f])
  + Σ_t (FTL_Rate[t]·ftl[t] + PTL_Rate[t]·ptl[t] + LTL_Rate[t]·load_kg[t]·ltl[t])
  + Σ_i (Courier_Rate × z[i])
  + Σ_i (Total_Penalty_INR[i] × breach[i])
```

The trip term covers **all three lane types** (FC→SC, SC→DS, FC→DS direct) — same per-trip rates apply regardless of lane type.

---

## 9. Cost comparison output

Every solve produces a `Cost_Comparison` sheet in the output with:

- **Courier-Only Baseline cost** — hypothetical cost if every order shipped FC_DIRECT (courier @ ₹85 for eligible parcels, weighted-up rate for heavier orders requiring oversize courier service)
- **Optimizer cost** — actual solution
- **Savings (INR and %)**
- Per-route-type breakdown (Hub-Spoke / FC-Direct / Courier)

The point: validate that the optimizer's routing is meaningfully better than the naive "just send everything courier" baseline.

---

## 10. Solver outputs

Output Excel has **7 sheets** (see `MMCVRPTW_MLT_OutputTemplate_V4.xlsx`):

1. **Solve_Summary** — run metadata, status, gap, cost breakdown, order KPIs, cost comparison, load type mix. **[V4]** Now includes a `Method_Used` row identifying which of the 5 methods produced the result.
2. **Order_Assignment** — per-order route_type, FC, SC, DS, carrier, vehicle, load_type, trip_id, dispatch_time, sla_status
3. **Order_Timeline** — per-order timestamps: FC_Dispatch, SC_Arrival, SC_Dispatch, DS_Arrival, DS_Dispatch, Customer_ETA, Ops_SLA_Deadline, SLA_Status
4. **Trip_Plan** — per-trip lane_type, carrier, vehicle, load_type, stop sequence, parcels, distance, fill %, cost, departure/arrival
5. **Node_Utilization** — per-node load vs capacity, utilization %, bottleneck flag
6. **Recommendations** — six analytical cards (see §12)
7. **Cost_Comparison** — Optimizer vs Courier-Only baseline

**No new sheets in V4.** Benchmarking data lives in a separate `benchmark.json` file in `runs/<run_id>/`, not in the user-facing Excel.

---

## 11. Solver — single profile + method picker [V4]

**[V4 major change]** The previous profile system (Fast / Balanced / Strict / Diagnostic) is replaced with:

- **One solver profile**: 1% MIP gap target, 60 minute hard wall-clock cap.
- **Method picker**: at solve time, the user chooses from 5 solve methods (Phase 1) or sees 5 more roadmap methods (Phase 2). Each method has its own time/quality trade-off.

If a solve hits the 60-minute cap before reaching 1% gap, return the best incumbent found with the achieved gap displayed in the UI. Do not return failure.

### Method 1 — Quick (Aggregated demand cells)

- **Solve time:** 60–180 s
- **Confirmed gap:** 1–3%
- **What it solves:** All cost math, all capacity constraints, SLA penalty, courier rules, FTL/PTL/LTL load disjunction. Demand grouped by `(FC, DS, Priority)` cohorts (~3,175 cells for the 10k sample).
- **What it does NOT solve:** Per-order routing decisions — order assignments are reconstructed post-solve by deterministically allocating individual orders to the optimized parcel-count flows.
- **Mechanism:** Aggregate orders into cells → build flow MILP with parcel-count variables per (cell, path) → solve with HiGHS → post-process to per-order assignments.

### Method 2 — Balanced (Per-FC decomposition)

- **Solve time:** 3–6 min
- **Confirmed gap:** ~3–5% (1–2% proven per sub-MILP, with calibrated estimate for cross-FC coupling)
- **What it solves:** Full per-order x/y/w/z binaries within each FC's sub-problem, MTZ multi-stop within each FC, SLA breach with tightened Big-M, FTL/PTL/LTL disjunction, FC-local capacity coupling.
- **What it does NOT solve:** Cross-FC SC load balancing (post-validated with a fixup MILP if violated), global carrier concentration (pro-rated per FC by order share).
- **Mechanism:** Partition orders by origin FC → spawn 15 HiGHS instances (4-min cap each, threads divided across cores) → merge solutions → validate global SC/carrier caps → run a small rebalancing MILP if any violation (~30–60s extra).

### Method 3 — Strict (Monolithic per-order MILP)

- **Solve time:** 20–60 min
- **Confirmed gap:** 1% (mathematically proven from LP dual bound)
- **What it solves:** Everything in §7. Single coupled MILP, all couplings exact.
- **What it does NOT solve:** Nothing — this is the spec-literal solve.
- **Mechanism:** Build full per-order MILP → run HiGHS with 8 threads → return at 1% gap or 60-min cap (whichever first).

### Method 4 — Heuristic (Greedy + 2-opt local search)

- **Solve time:** 10–30 s
- **Confirmed gap:** None — no optimality bound from this method
- **What it solves:** Returns a feasible answer using greedy assignment (cheapest feasible route per order, processed in deadline order) followed by 2-opt local search on trip sequences.
- **What it does NOT solve:** No optimality proof, no MILP. Typically 10–25% worse cost than MILP solutions.
- **Mechanism:** Sort orders by `Ops_SLA_Deadline` ascending → for each order, evaluate all feasible (route, carrier, vehicle, load_type) options → assign cheapest → after all assigned, run 2-opt swaps on multi-stop trip sequences.

### Method 5 — LP Bound (Diagnostic relaxation)

- **Solve time:** 5–15 s
- **Confirmed gap:** Provides a lower bound only — not a solution
- **What it solves:** Drops integrality. Gives the LP relaxation cost — a mathematical floor on what any integer solution can achieve. Useful for sanity-checking that the model is feasible at all and as a reference for evaluating other methods' gaps.
- **What it does NOT solve:** No integer solution. The variable values are fractional and don't correspond to a real plan.
- **Mechanism:** Build full per-order LP (no binaries) → run HiGHS simplex → return objective and dual bound.

### Methods 6–10 (Roadmap, not built in Phase 1)

These appear in the UI as visible-but-disabled cards with full explanations, but are not implemented. They are listed for transparency about the full solver landscape:

- **6 — Greedy warm start + Aggregated MILP** — Method 4 result fed as `mipStart` to Method 1. Expected to cut Quick's time by 30–60%.
- **7 — Benders decomposition** — Master (routing) + subproblems (capacity feasibility). Implemented as Python cut-loop since HiGHS lacks lazy callbacks.
- **8 — Column generation (Dantzig-Wolfe)** — Set-partitioning master + shortest-path pricing oracle. The method production VRP solvers use.
- **9 — Lagrangian relaxation** — Dualise the carrier-concentration caps; subgradient updates on the multipliers. Convergence-dependent.
- **10 — Rolling horizon** — Split the 4-hour dispatch wave into 30-min slices; solve each slice sequentially. Requires a time axis the current single-wave use case doesn't have, but useful for multi-wave extensions.

### Method selection UX

On the Configure screen, all 10 methods are shown as cards in a grid. Each card displays:

- Method badge (QUICK / BALANCED / STRICT / HEURISTIC / LP BOUND / ROADMAP)
- Solve-time estimate · expected gap
- "What it solves" (green checks)
- "What it does NOT solve" (red crosses)
- A 4-step algorithm breakdown
- An optimality-bound footnote explaining how the gap claim is computed

Phase 1 cards have an active Run button. Roadmap cards have a "Phase 2 — not yet built" badge with a disabled button but full explanation text intact.

---

## 12. Recommendations — six cards (unchanged)

| # | Card | What it shows |
|---|---|---|
| 1 | **Under-utilized FCs** | FCs below 50% throughput. Suggestion: rebalance or candidates for surge support. |
| 2 | **Carriers near concentration cap** | Carriers within 5% of `Max_Concentration_pct`. Risk of over-dependence. |
| 3 | **FTL consolidation opportunities** | Lanes where merging current PTL+LTL would clear the 75% FTL threshold. Estimated savings shown. |
| 4 | **Courier vs Hub-Spoke trade-off** | Per-pincode comparison. Where courier wins (low volume, remote DSes) and where hub-spoke wins (metros). |
| 5 | **SLA-breach risk** | Top 10 tightest FC×DS pairs by slack between transit and Ops_SLA_Deadline. |
| 6 | **Multi-stop opportunities missed** | DS pairs frequently on separate trips that could fit within Max_Detour_pct. |

---

## 13. Performance expectations (per method, 10k-order sample)

| Method | Variables | Wall-clock | Confirmed gap |
|---|---|---|---|
| Quick — Aggregated | ~15k | 60–180 s | 1–3% (proven from LP dual) |
| Balanced — Per-FC decomp | ~70k total / ~5k per sub | 3–6 min (parallel) | ~3–5% (sub-proven + coupling estimate) |
| Strict — Monolithic | ~150k | 20–60 min | 1% (proven) or whatever achieved at 60-min cap |
| Heuristic — Greedy+2-opt | n/a | 10–30 s | None (no bound) |
| LP Bound — Relaxation | ~150k (continuous) | 5–15 s | Lower-bound-only diagnostic |

These are estimates. MILP solve times have high variance — same model on slightly different data can be 2–10× faster or slower.

---

## 14. Stack and runtime

- **Backend:** Python 3.11+, FastAPI, uvicorn, pandas, openpyxl, **highspy (pinned to a tested version)**, pydantic. SSE for streaming the solver log to the UI.
- **Frontend:** **Vite + React 18 + Tailwind CSS** (matching the WaveLoad reference project's design system exactly — see prompt for the design-token spec).
- **Charts:** Chart.js via npm install.
- **Tables:** Tabulator via npm install (paginated, sortable, filterable for 10k-row tables).
- **Launch:** `run.sh` (mac/Linux) and `run.bat` (Windows) start the backend and frontend, wait for both to be ready, open the browser to `http://localhost:8765`. First run installs Python deps into `.venv/` and npm deps into `frontend/node_modules/`. Subsequent runs are fast.
- **Node.js required**: Yes, Node 18+ must be installed by the user.

---

## 15. V4 changelog (vs V3)

| # | V3 state | V4 change |
|---|---|---|
| 1 | Master Excel = 14 sheets; orders in separate CSV | Master Excel = 15 sheets; **Order_Data is sheet 15**. Single-file upload. |
| 2 | App could derive missing order columns from masters | App **rejects** uploads where Order_Data lacks any of the 20 columns. No silent derivation. |
| 3 | 4 solver profiles (Fast/Balanced/Strict/Diagnostic) | 1 profile (1% gap, 60-min cap) + **method picker** with 5 implemented + 5 roadmap. |
| 4 | Solver chosen automatically; no user choice of method | User explicitly picks method on Configure screen with full trade-off explanation. |
| 5 | Frontend: vanilla HTML/JS, no build step | Frontend: **Vite + React + Tailwind**, matches WaveLoad project's design system. |
| 6 | Output had 7 sheets | Output has 7 sheets (unchanged); benchmarking data lives in `runs/<run_id>/benchmark.json`. |
| 7 | Solve_Summary had no method field | Solve_Summary row 8 = `Method_Used` (Quick/Balanced/Strict/Heuristic/LP Bound). |
| 8 | (Latent bug) `breach[i]` declared but not constrained | **Required:** `breach[i]` MUST be tied to `arrival_time[i] − ops_sla_deadline[i] ≤ M·breach[i]`. Self-test enforced. |
| 9 | (Latent bug) MTZ silently dropped under "deviations" | **Required:** MTZ present in Strict and Balanced (per-FC). Self-test verifies subtour-elimination is active. |
| 10 | (Latent bug) `addCols` signature mismatch crashed solver | **Required:** `highspy` pinned in `requirements.txt`; all solver calls match the pinned version's signatures. |

---

## 16. Honest caveats — please read

**The network is representative, not real Amazon scale.** Amazon India operates ~60 FCs, ~30 SCs, and 500–2,000 DSes. The 15/10/200 network here is a representative subset. Insights (routing patterns, bottleneck logic, FTL/PTL/LTL economics) are **structurally valid** at real scale, but the absolute numbers are smaller.

**Multi-stop routing via MTZ is the hardest part of the formulation.** Solve time is sensitive to data shape. If multi-stop opportunities are dense (many DS pairs close together on the same lane), expect longer solves.

**The method picker is a real engineering choice, not a marketing gimmick.** Each of the 5 implemented methods is a different algorithmic strategy with different optimality guarantees. Quick is appropriate for iteration and demos. Balanced is the daily-ops default. Strict is for monthly planning where 30 minutes of compute is fine. Heuristic and LP Bound are diagnostic tools. Use the right one for the moment.

**Method choice does not change the underlying problem.** All 5 methods solve the same MMCVRPTW-MLT problem against the same input data and the same constraint set. They differ in *how* they search and *what* they guarantee about the result, not in *what* problem they pose.
