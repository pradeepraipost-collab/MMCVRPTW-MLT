"""Diagnostic for the 3 failing self-tests. Run this from the project root
inside the activated venv: `source .venv/bin/activate && python diagnose.py`.

Prints:
  1. Whether highspy exposes changeColIntegrality (singular) or only the bulk variant.
  2. Integer vs continuous variable counts on a built Strict model.
  3. The time_limit option HiGHS sees after setOptionValue.
  4. The arrival_time and breach_link rows for ORD-IMPOSSIBLE-001, by exporting
     the model to LP format and grepping.
  5. After running the solve, the actual values of arrival/breach/route binaries
     for the impossible order.
"""
import sys, os, re, subprocess
sys.path.insert(0, ".")

import highspy
from backend.ingest import read_master_workbook
from backend.problem import build_problem
from backend.tests.conftest import build_synthetic_impossible_problem
from backend.methods.strict import _build_and_solve, _enumerate_trips
from backend.methods.base import LogCapture

print("=" * 70)
print("DIAGNOSTIC 1 — highspy API surface")
print("=" * 70)
h = highspy.Highs()
print(f"highspy version: {getattr(highspy, '__version__', 'unknown')}")
print(f"  changeColIntegrality (singular) present: {hasattr(h, 'changeColIntegrality')}")
print(f"  changeColsIntegrality (bulk) present:    {hasattr(h, 'changeColsIntegrality')}")
print(f"  HighsVarType.kInteger:                   {highspy.HighsVarType.kInteger}")
print(f"  HighsVarType.kContinuous:                {highspy.HighsVarType.kContinuous}")

# Test the singular call actually marks a column integer
h.addCol(1.0, 0.0, 1.0, 0, [], [])
if hasattr(h, 'changeColIntegrality'):
    h.changeColIntegrality(0, highspy.HighsVarType.kInteger)
    lp = h.getLp()
    integrality = list(lp.integrality_) if hasattr(lp, 'integrality_') else None
    print(f"  After singular call, lp.integrality_ = {integrality}")
print()

print("=" * 70)
print("DIAGNOSTIC 2 — build the S3 synthetic model, count int vs continuous")
print("=" * 70)
r = read_master_workbook("MMCVRPTW_MLT_MasterData_V4.xlsx")
problem = build_problem(r.frames)
sub, impossible_id = build_synthetic_impossible_problem(problem)
print(f"Synthetic problem: {len(sub.orders)} orders, impossible_id={impossible_id}")

# Mirror _build_and_solve up to just before h.run()
log = LogCapture()
# We re-implement the build using highspy directly so we can introspect.
# Easier: temporarily hack _build_and_solve to dump after build but before solve.
# We do this by calling it with a tiny time_cap; the build happens regardless.

# Patch: ask strict to build but stop at solve. The fastest path is to call
# _build_and_solve normally with time_cap=1s — model is built before run().
# But we can't easily inspect mid-build. Instead, after the solve, fetch the
# model and inspect.
result = _build_and_solve(
    problem=sub, method_id="strict_diag",
    relax_integrality=False, time_cap_sec=60.0, gap_target=0.05,
    threads=4, log=log, cancel=None,
)
# Inspect HiGHS LP after solve — we need to rebuild and stop before run, so:
print(f"Solve result: status={result.status}, obj={result.best_objective}, "
      f"sla_penalty={result.sla_penalty_inr}, wall={result.wall_time_sec:.2f}s")
print(f"Row count (by name): {len(result.row_names)}")
print(f"  arrival_time rows for impossible: "
      f"{[r for r in result.row_names if 'arrival_time_' + impossible_id in r]}")
print(f"  breach_link rows for impossible:  "
      f"{[r for r in result.row_names if 'breach_link_' + impossible_id in r]}")

# Variable values for impossible order
print(f"\nImpossible order solution values:")
for key in [("arrival", impossible_id), ("breach", impossible_id),
            ("z", impossible_id)]:
    v = result.variable_values.get(key)
    print(f"  {key} = {v}")
# Sum of z + w_fd[*] + x_mm[*] for impossible order (should be 1.0)
total = result.variable_values.get(("z", impossible_id), 0.0) or 0.0
for k in range(20):
    total += result.variable_values.get(("w_fd", impossible_id, k), 0.0) or 0.0
    total += result.variable_values.get(("x_mm", impossible_id, k), 0.0) or 0.0
print(f"  coverage sum (z + Σw_fd + Σx_mm) = {total}")
print()

print("=" * 70)
print("DIAGNOSTIC 3 — export model to LP, grep for impossible order rows")
print("=" * 70)
# Rebuild the model fresh and write it BEFORE solving (cleanest).
# Easier: just write it after the solve we already did. HiGHS retains the model.
# We use Highs.writeModel via a fresh Highs instance with same model.
# Simplest hack: re-run _build_and_solve with time_cap=0.1 capturing the highs
# instance via a thread-local. Cleaner: refactor strict.py to expose the
# build function. For diagnostic purposes we'll use the LP solver path which
# also goes through _build_and_solve.
import importlib
strict_mod = importlib.import_module("backend.methods.strict")
# Monkey-patch h.run() so the model is preserved without solving for inspection
_orig_run = highspy.Highs.run
captured = {"h": None}
def _capture_run(self, *args, **kw):
    captured["h"] = self
    # Write model now, before run, so we capture pre-solve state
    self.writeModel("/tmp/s3_model.lp")
    return _orig_run(self, *args, **kw)
highspy.Highs.run = _capture_run
_ = _build_and_solve(
    problem=sub, method_id="strict_lpexport",
    relax_integrality=False, time_cap_sec=5.0, gap_target=0.05,
    threads=1, log=LogCapture(), cancel=None,
)
highspy.Highs.run = _orig_run

print("LP file written to /tmp/s3_model.lp")
print(f"File size: {os.path.getsize('/tmp/s3_model.lp')} bytes")
print()

# Grep for the impossible order rows
print(f"Looking for rows matching '{impossible_id}' in LP:")
with open("/tmp/s3_model.lp") as f:
    lp_text = f.read()
for pattern in [f"arrival_time_{impossible_id}", f"breach_link_{impossible_id}",
                f"breach_{impossible_id}", f"arrival_{impossible_id}"]:
    matches = [ln for ln in lp_text.splitlines() if pattern in ln]
    print(f"\n  '{pattern}' — {len(matches)} matching lines:")
    for m in matches[:6]:
        print(f"    {m}")

# Count integer vs continuous columns
print("\n" + "=" * 70)
print("DIAGNOSTIC 4 — integer vs continuous columns in the built model")
print("=" * 70)
# Parse the LP file for 'Integers' and 'Binaries' sections
int_section_match = re.search(r"(?m)^(Integers|Generals)\s*\n((?:[^\n]+\n)*?)(?=^[A-Z]|\Z)", lp_text)
bin_section_match = re.search(r"(?m)^Binaries?\s*\n((?:[^\n]+\n)*?)(?=^[A-Z]|\Z)", lp_text)
n_int = 0
n_bin = 0
if int_section_match:
    n_int = len(int_section_match.group(2).split())
if bin_section_match:
    n_bin = len(bin_section_match.group(1).split())
# Count total columns
n_cols_match = re.search(r"\\Columns: (\d+)", lp_text) or re.search(r"NCOLS\s*=?\s*(\d+)", lp_text)
print(f"  Integers section entries: {n_int}")
print(f"  Binaries section entries: {n_bin}")
print(f"  Total integer-marked columns: {n_int + n_bin}")
if n_int + n_bin == 0:
    print("  *** BUG: no columns marked integer/binary. Model is effectively an LP. ***")
print()

print("=" * 70)
print("DIAGNOSTIC 5 — time_limit option as seen by HiGHS")
print("=" * 70)
h2 = highspy.Highs()
h2.setOptionValue("output_flag", False)
h2.setOptionValue("time_limit", 60.0)
opt = h2.getOptionValue("time_limit")
print(f"  After setOptionValue('time_limit', 60.0), getOptionValue returns: {opt}")
print()

print("END OF DIAGNOSTIC")
