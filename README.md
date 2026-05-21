# MMCVRPTW-MLT V4

**Multi-Echelon Multi-Commodity Capacitated Vehicle Routing Problem with Time Windows and Multiple Load Types.** Wave-based ecommerce fulfilment network optimiser. Local Python + HiGHS MILP solver with a multi-method picker that trades solve-time against proximity-to-optimum on the same problem instance.

See `MMCVRPTW_MLT_Design_Summary_V4.md` for the authoritative spec.

## Install

1. **Python 3.11+** — install from <https://www.python.org/downloads/>.
2. **Node.js 18+** — install from <https://nodejs.org/>.

No other prerequisites. Everything else is installed automatically by the launcher on first run.

## Run

```bash
# macOS / Linux
./run.sh
```

```cmd
REM Windows
run.bat
```

On the first run, the launcher creates `.venv/`, installs the pinned Python dependencies from `requirements.txt`, runs the six mandatory self-tests from spec §15, installs the frontend dependencies, then starts the backend on `http://localhost:8000` and the frontend on `http://localhost:5173` (which the browser opens automatically).

Subsequent runs reuse the cached environments and are fast.

## What it does

You upload the 15-sheet master Excel (with `Order_Data` at sheet 15, 20 columns, 10k orders in the supplied sample). On the Configure screen you pick one of five solve methods — Quick (60–180 s, aggregated cells), Balanced (3–6 min, per-FC decomposition), Strict (20–60 min, monolithic per-order MILP), Heuristic (10–30 s, greedy + 2-opt), or LP Bound (5–15 s, diagnostic relaxation). The solver streams its log live, then renders results across seven tabs: Summary, Order Assignment, Order Timeline, Trip Plan, Node Utilization, Recommendations, and Cost Comparison vs a courier-only baseline. The full output is also downloadable as a 7-sheet Excel matching `MMCVRPTW_MLT_OutputTemplate_V4.xlsx`.

## Architecture map

```
MMCVRPTW-MLT/
├── MMCVRPTW_MLT_Design_Summary_V4.md          authoritative spec
├── MMCVRPTW_MLT_MasterData_V4.xlsx            sample 10k-order master
├── MMCVRPTW_MLT_OutputTemplate_V4.xlsx        output formatting template
├── backend/
│   ├── main.py                                FastAPI app, SSE log streaming, all endpoints
│   ├── schemas.py                             Pydantic request/response models
│   ├── ingest.py                              15-sheet workbook reader + Order_Data validator
│   ├── problem.py                             Typed Problem dataclasses
│   ├── methods/
│   │   ├── base.py                            Abstract Method, shared utilities, MethodResult
│   │   ├── quick.py                           Method 1 — aggregated demand cells
│   │   ├── balanced.py                        Method 2 — per-FC decomposition
│   │   ├── strict.py                          Method 3 — monolithic per-order MILP (reference)
│   │   ├── heuristic.py                       Method 4 — greedy + 2-opt
│   │   ├── lp_bound.py                        Method 5 — LP relaxation diagnostic
│   │   └── roadmap.py                         Methods 6-10 stubs (raise NotImplementedError)
│   ├── solve_runner.py                        Background thread, SSE log capture, cancellation
│   ├── extract.py                             Parse solved model into assignments / trips / etc.
│   ├── output_writer.py                       Write 7-sheet xlsx preserving template formatting
│   ├── recommendations.py                     The six analytical cards
│   ├── cost_comparison.py                     Courier-only baseline computation
│   ├── benchmark.py                           Run all 5 methods on a stratified subset
│   └── tests/                                 MANDATORY self-tests S1-S6 (anti-shortcut gate)
├── frontend/
│   ├── package.json, vite.config.js, tailwind.config.js, postcss.config.js, index.html
│   └── src/
│       ├── index.css                          Design tokens (Space Grotesk / Syne / JetBrains Mono)
│       ├── App.jsx, main.jsx
│       ├── context/AppContext.jsx             V4 app state (no profiles, just method_id)
│       ├── components/
│       │   ├── Sidebar.jsx                    Adapted from ui_reference; 3 nav groups
│       │   ├── KpiCard.jsx, DataTable.jsx
│       │   ├── MethodCard.jsx                 10-method picker card
│       │   ├── MethodExplanationPanel.jsx     "solves / does NOT solve" + algorithm steps
│       │   └── SolverLogConsole.jsx           SSE log viewer
│       ├── data/methods.js                    The 10-method config (full content per spec §11)
│       └── pages/
│           ├── Upload.jsx                     Step 1 — drag-drop the 15-sheet xlsx
│           ├── Configure.jsx                  Step 2 — the 10-method picker (central UI piece)
│           ├── Solve.jsx                      Step 3 — live solver log via SSE
│           ├── Results.jsx                    Step 4 — 7 result tabs + download
│           ├── InputDashboard.jsx             Network overview (home)
│           └── DataExplorer.jsx               Browse loaded master sheets
├── runs/                                       one folder per solve (output.xlsx, log, benchmark.json)
├── requirements.txt                            pinned Python deps (highspy==1.7.2 — see S5)
├── run.sh / run.bat                            launchers; gate on self-tests
└── README.md                                   this file
```

## Troubleshooting

**Python or Node not found.** Install the prerequisites above. The launchers re-check and abort with a clear message if a required tool is missing.

**Port already in use.** Stop whatever is on `:8000` (backend) or `:5173` (frontend). On macOS / Linux: `lsof -ti:8000 | xargs kill`. On Windows: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F`.

**`highspy` install fails.** The pinned version is `1.7.2`. On macOS Apple Silicon, you may need Xcode command-line tools (`xcode-select --install`). On Windows, install the Microsoft C++ Build Tools. If the upstream wheel for your platform is missing, `pip` will try to compile from source — that takes a few minutes but should succeed on a stock dev machine.

**A self-test fails on launch.** Read the test name printed by pytest. Each test enforces a specific anti-shortcut from spec §15 — for example, S1 catches the V3 infeasibility bug, S3 catches a dangling `breach` variable, S4 catches dropped MTZ. Fix the underlying issue; do not edit the test to make it pass.

**Solve takes longer than expected.** That's normal for MILP — Strict on 10k orders is 20–60 minutes; Quick is 60–180 seconds; if you want a fast answer use Quick or Heuristic. The Solve page shows live elapsed time and best-incumbent / best-bound / gap so you can decide whether to wait or cancel.

**The browser doesn't open automatically.** Visit `http://localhost:5173` manually after the launcher finishes its "Starting frontend" line.
