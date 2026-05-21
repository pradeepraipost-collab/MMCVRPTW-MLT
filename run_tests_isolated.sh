#!/usr/bin/env bash
# Run each self-test in its own pytest invocation (separate Python process).
# Use this to distinguish "real test failure" from "suite-order/state pollution".
#
# Interpretation:
#   - All 6 PASS individually → suite-order/state-pollution bug (highspy global
#     state, file-handle leak, memory pressure from S1's giant model, etc.)
#   - Some fail individually → real bug in that test's solve path
#
# Usage:
#   ./run_tests_isolated.sh

cd "$(dirname "$0")"
source .venv/bin/activate

echo "=== Running each S-test in isolation ==="
for t in test_S1_strict_feasibility test_S2_method_consistency \
         test_S3_breach_wiring test_S4_mtz_active \
         test_S5_highspy_version test_S6_output_template; do
    echo ""
    echo "--- $t ---"
    pytest "backend/tests/$t.py" -v --tb=line 2>&1 | tail -8
done
