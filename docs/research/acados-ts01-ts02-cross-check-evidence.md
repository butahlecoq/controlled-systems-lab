# T-S01 and T-S02 acados cross-check evidence

Status: the original Windows runs and the owner-authorized Linux reruns are recorded below. Each Linux case used one additional native acados OCP-QP solve with pinned v0.6.0. These are single-witness cross-checks, not paired comparisons, benchmarks, or reproduction claims. No timing values are used.

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

This post-hoc check strengthens witness verification but cannot make the original solver invocations data-driven. At that point, each case had used its one permitted run, so the original harness was not rerun. The owner later authorized one additional attempt for T-S01 and T-S02. Those attempts are documented below.

The local `bundle-manifest.json` records SHA-256 hashes and sizes for the canonical JSON, compiled harness and source, raw outputs, checker, and checker report. Its SHA-256 is `DBC77A3140894DD2F820CEC0E7F83FDE8809674248507C4A822E24FCC054A3FD`. The manifest and the exact files it covers remain at the local scratch path above.

## Independent exact-arithmetic check

The separate checker parses each 17-digit solver value to its exact IEEE-754 binary rational, then evaluates the initial condition, both dynamics equations, both control bounds, the terminal objective, and T-S01's optimal-family equality without using acados or repository solver/checker code.

- **T-S01:** the raw floating-point tuple is not a literal exact member of the optimal family: `x[2]−1 = 1425/2251799813685248 ≈ 6.3282712403633923e−13`. The exact dynamics residuals are `51545133/2417851639229258349412352` and `−1/18014398509481984`; `x[0]` also differs from zero by `−319980589/2417851639229258349412352`. Controls are exactly inside `[0,1]`. The checker therefore records numerical agreement with a nonzero exact optimal-family violation, rather than claiming exact membership.
- **T-S02:** all initial, dynamics, and control constraints hold exactly for the captured binary values. The constant objective is exactly `3`; every feasible history is optimal. The zero-variable objective representation was accepted by acados.

The local scratch bundle under `D:\work\PhD\builds\acados-v0.6.0-build\smoke\` contains the canonical JSON, harness source, compiled executable, per-case raw logs and exit codes, and checker sources/reports. The original `bundle-manifest.json` covers the original canonical JSON, solver logs/exits, and `check_ts01_ts02.py` / `exact-check-report.json`; it does **not** list the later post-hoc files. The supplemental `check_ts01_ts02_from_canonical.py` and `posthoc-canonical-check-report.json` are identified separately by their SHA-256 hashes above. All artifacts remain local as required by the parent specification.

## Owner-authorized Linux reruns

On 2026-10-22, the owner authorized one additional end-to-end attempt for each case. The authorization kept the pinned acados release, OCP-QP solver route, and existing per-run limits. It prohibited a B04 retry, solver tuning, benchmarking, and pairing.

The original canonical JSON files were not available on this Linux host. I reconstructed both files from the frozen definitions in #513 before building either client. The JSON and generated clients are local under `/tmp/acados-ts01-ts02-inputs/`.

The T-S01 JSON SHA-256 is `c8addec6f341de7226fd4814c31eacb27ce499f342e74c9a8a902b3645d0b745`. The T-S02 JSON SHA-256 is `fc999a294136d560250f1e7f31450a4250bbb02f95a272287a982587b5dcc3e8`. The generator read each file and copied its dynamics, bounds, and objective coefficients into the OCP-QP client. The independent checker reads the same JSON and the captured IEEE-754 values.

The source checkout was acados v0.6.0 commit `503364817c872d474ab5bed219c26760ac267769` with the pinned recursive submodules. It had no tracked source edits. A pre-existing untracked CMake distribution remained in the checkout. The build and install paths were separate.

The build used Linux x86-64, GCC 16.2.1, and CMake 3.31.6. It produced Release static libraries with generic BLASFEO and HPIPM. OpenMP and optional QP solvers were disabled. Ninja was unavailable, so CMake used Unix Makefiles.

Each process had a 300-second timeout and an 8-GiB `RLIMIT_AS` cap. The harness invoked `FULL_CONDENSING_HPIPM` once per case and did not collect timing data.

| Case | Process outcome | Independent check | Evidence |
|---|---|---|---|
| T-S01 | `ocp_qp_solve` returned status 0. The client then exited with signal 11 while reading `x[0]`. The saved core shows that `ocp_qp_out_get` wrote a `double` through a pointer-to-pointer argument, and the client then dereferenced that solution value as an address. I recovered the solver status, residuals, and solution vector from the core. No solver rerun occurred. | The exact checker passed the `1e-9` tolerance. The witness is not an exact member of the optimal family: `x[2] - 1 = 1425/2251799813685248`, and `u[0] + u[1] - 1 = 11403/18014398509481984`. Maximum exact feasibility violation is `319980589/2417851639229258349412352`. | Local `results/T-S01/core.dump`, `core-recovery.json`, `witness.json`, and `check-report.json`. |
| T-S02 | One process exit 0; acados status 0. | The exact checker passed. Initial and dynamics equations and control bounds hold exactly for the captured binary values. The canonical objective is exactly 3, so every feasible history is optimal. | Local `results/T-S02/solver.stdout`, `witness.json`, and `check-report.json`. |

The T-S01 core dump preserves the result from the one authorized solve. Its saved exit status remains `-11` because the output wrapper crashed after the solve returned. The recovered witness and exact check are supplemental evidence, not a claim that the original wrapper completed successfully. T-S01's exact family equality remains false for the binary witness, although its violations fall below the declared tolerance.

The local input directory `/tmp/acados-ts01-ts02-inputs/` retains the canonical case files, generator and checker sources, generated C clients, executables, raw outputs, per-case invocation markers, core analysis, and hashes. Its `bundle-manifest.json` SHA-256 is `2d8c19ccf05a063a310e9d7f4bcd0f87d39a35d0ae2379c450bb67d5cc806492`. The acados build directory contains generated static libraries only and can be removed after this evidence update. No benchmark or B04 solve was run.
