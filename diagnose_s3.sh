#!/usr/bin/env bash
# One-shot diagnostic for the S3 infeasibility. Dumps the LP, greps for
# empty-LHS rows, the impossible order's rows, and the small-coefficient
# range. Paste the full output back.

cd "$(dirname "$0")"
set -e
source .venv/bin/activate

echo "=========================================================="
echo "STEP 1 — Run S3 with LP dump"
echo "=========================================================="
MMCVRPTW_DUMP_LP=1 pytest backend/tests/test_S3_breach_wiring.py -v -s 2>&1 | tail -8

echo ""
echo "=========================================================="
echo "STEP 2 — LP file exists?"
echo "=========================================================="
ls -la /tmp/mmcvrptw_model.lp 2>&1
echo ""

echo "=========================================================="
echo "STEP 3 — Empty-LHS / RHS-bound = 0 rows (first 30)"
echo "=========================================================="
grep -B1 -A0 "<= 0$\|>= 0$\| = 0$" /tmp/mmcvrptw_model.lp 2>/dev/null | head -60

echo ""
echo "=========================================================="
echo "STEP 4 — Distinct small coefficients (< 0.01)"
echo "=========================================================="
grep -oE "\b0\.00[0-9]+\b" /tmp/mmcvrptw_model.lp 2>/dev/null | sort -u | head -20

echo ""
echo "=========================================================="
echo "STEP 5 — breach_link_ORD-IMPOSSIBLE-001 row"
echo "=========================================================="
grep -A2 "breach_link_ORD-IMPOSSIBLE-001" /tmp/mmcvrptw_model.lp 2>/dev/null | head -20

echo ""
echo "=========================================================="
echo "STEP 6 — arrival_time_ORD-IMPOSSIBLE-001 row"
echo "=========================================================="
grep -A2 "arrival_time_ORD-IMPOSSIBLE-001" /tmp/mmcvrptw_model.lp 2>/dev/null | head -20

echo ""
echo "=========================================================="
echo "STEP 7 — Sample of ptl_lower rows (zero-coef suspects)"
echo "=========================================================="
grep -A1 "ptl_lower" /tmp/mmcvrptw_model.lp 2>/dev/null | head -30

echo ""
echo "=========================================================="
echo "STEP 8 — Vehicle PTL_Min_Weight_kg values (0 → zero coef bug)"
echo "=========================================================="
python3 -c "
import sys; sys.path.insert(0, '.')
from backend.ingest import read_master_workbook
from backend.problem import build_problem
r = read_master_workbook('MMCVRPTW_MLT_MasterData_V4.xlsx')
p = build_problem(r.frames)
for vt, v in p.vehicles.items():
    print(f'  {vt:18s} weight_cap={v.weight_capacity_kg:>8.1f}  ptl_min={v.ptl_min_weight_kg:>8.1f}  vol_cap={v.volume_capacity_m3:>6.3f}  parcels={v.parcel_capacity}')
"

echo ""
echo "END OF DIAGNOSTIC"
