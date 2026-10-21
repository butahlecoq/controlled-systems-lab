# T-S01 and T-S02 acados cross-check evidence

Status: one native acados OCP-QP solve per canonical case, using the pinned v0.6.0 build recorded in the [MSVC recipe](tools/acados-v0.6.0-native-msvc-build.md). These are single-witness cross-checks, not paired comparisons, benchmarks, or reproduction claims. No timing values are used.

## Canonical inputs

Both cases use horizon 2, scalar dynamics `x[k+1] = x[k] + u[k]`, initial state `x[0] = 0`, unrestricted states, and independent stage controls `u[0], u[1] ∈ [0, 1]`.

| Case | Canonical terminal objective | acados OCP-QP variable terms | Constant term handling |
|---|---|---|---|
| T-S01 | `(x[2] − 1)^2`, represented by `Q=2`, `q=−2`, offset `1` | `0.5 Q x² + q x = x² − 2x` | The additive `1` is absent from the acados OCP-QP interface; it does not change the minimizer. Add it back when evaluating the canonical objective. The exact optimal family has `x[2]=1`, equivalently `u[0]+u[1]=1` within the control box. |
| T-S02 | Constant `3`, represented by a zero residual map and offset `3` | All variable quadratic and linear terms are zero | The zero-cost OCP-QP was accepted as-is. acados reports variable objective `0`; the independent checker evaluates the canonical objective as exactly `3`. No exact-composition fallback was used. |

## Solver results

Both calls used `FULL_CONDENSING_HPIPM`; each returned acados status `0` and process exit code `0`.

| Case | `x[0], x[1], x[2]` | `u[0], u[1]` | acados residuals: stationarity, dynamics, inequality, complementarity | Largest exact violation |
|---|---|---|---|---|
| T-S01 | `−1.3234086980704929e−16`, `0.49999999999203265`, `1.0000000000006328` | `0.49999999999203276`, `0.50000000000860023` | `1.5053735771646659e−14`, `0`, `2.3234086980704929e−16`, `6.6420395522627675e−13` | `6.3282712403633923e−13` |
| T-S02 | `0`, `0.098925751144616922`, `0.19785150228923384` | `0.098925751144616922`, `0.098925751144616922` | `0`, `0`, `9.9999999999999998e−17`, `1.2000359477832567e−15` | `0` |

## Reproducibility limits and review disposition

Exact-head review found that the one-time harness encoded its inputs directly and the checker did not consume every field in the canonical JSON. That JSON was assembled after the solver calls; it did not drive either run. Afterward, a supplemental exact checker was run over the preserved logs using the canonical JSON as its source for the recurrence, initial state, horizon, control bounds, and objective coefficients. It independently confirms T-S02's exact feasibility and constant objective, and derives the T-S01 terminal minimizer `x2=1`; the recorded T-S01 witness is not an exact member because `x2−1 = 1425/2251799813685248`. The post-hoc checker source and report are retained in the local smoke bundle as `check_ts01_ts02_from_canonical.py` and `posthoc-canonical-check-report.json`, with hashes `4c768eb8b5acd6f89e3f5559794b42813cbb1beba383a60220c5be8796f6643` and `cc76fa923a628f75d777c7df0e826c863478e75188753c60559e430629b1bc30`; the report binds to canonical input hash `ead35197a8ac389f5787781be152ae142dcc64db0d70eabe604119b5f1ab9354`.

This post-hoc check strengthens witness verification but cannot make the original solver invocations data-driven. Each case has already used its one permitted solver run, so the harness was not rerun. #515's independent witness-check and case-evidence criteria are now supported; parent #513's stricter requirement that canonical case data drive both execution and checking remains unmet.

The local `bundle-manifest.json` records SHA-256 hashes and sizes for the canonical JSON, compiled harness and source, raw outputs, checker, and checker report. Its SHA-256 is `DBC77A3140894DD2F820CEC0E7F83FDE8809674248507C4A822E24FCC054A3FD`. The manifest and the exact files it covers remain at the local scratch path above.

## Independent exact-arithmetic check

The separate checker parses each 17-digit solver value to its exact IEEE-754 binary rational, then evaluates the initial condition, both dynamics equations, both control bounds, the terminal objective, and T-S01's optimal-family equality without using acados or repository solver/checker code.

- **T-S01:** the raw floating-point tuple is not a literal exact member of the optimal family: `x[2]−1 = 1425/2251799813685248 ≈ 6.3282712403633923e−13`. The exact dynamics residuals are `51545133/2417851639229258349412352` and `−1/18014398509481984`; `x[0]` also differs from zero by `−319980589/2417851639229258349412352`. Controls are exactly inside `[0,1]`. The checker therefore records numerical agreement with a nonzero exact optimal-family violation, rather than claiming exact membership.
- **T-S02:** all initial, dynamics, and control constraints hold exactly for the captured binary values. The constant objective is exactly `3`; every feasible history is optimal. The zero-variable objective representation was accepted by acados.

The local scratch bundle under `D:\work\PhD\builds\acados-v0.6.0-build\smoke\` contains the canonical JSON, harness source, compiled executable, per-case raw logs and exit codes, and checker sources/reports. The original `bundle-manifest.json` covers the original canonical JSON, solver logs/exits, and `check_ts01_ts02.py` / `exact-check-report.json`; it does **not** list the later post-hoc files. The supplemental `check_ts01_ts02_from_canonical.py` and `posthoc-canonical-check-report.json` are identified separately by their SHA-256 hashes above. All artifacts remain local as required by the parent specification.

No solver run was repeated. There is no timing or performance claim.
