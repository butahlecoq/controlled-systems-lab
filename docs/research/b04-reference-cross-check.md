# B04 reference cross-check attempt

This evidence belongs to issue #517 and the separate owner-authorized variant `b04-reference-v1`. It records two unsuccessful acados attempts. The second was explicitly authorized by the owner on 2026-10-23; the solver-success and HiGHS-certificate gates remain unmet. Per the owner's direction, this optional cross-check does not gate the main comparison work or the research-note task. No reproduction claim is made.

## Frozen variant

The canonical input in [`evidence/b04-reference-v1/canonical-case.json`](evidence/b04-reference-v1/canonical-case.json) uses the displayed B04 dynamics and printed initial state, horizon 16, continuous controls in `[-1,1]` at every stage, and the stated flow box at states 0 through 16. The initial state is fixed at stage 0 and also satisfies the flow box. The exact checker verifies all 17 states. The acados harness fixes the initial state and applies flow bounds at stages 1 through 16, which is equivalent for this fixed, in-box initial state. `benchmarks/scenarios/b04-historical.json` was not changed. The published objective `30.899` is not an acceptance target: the displayed terminal plane has a different optimum, and the historical discrepancy remains unresolved.

## Exact and HiGHS results

The exact checker uses rational arithmetic to minimize the squared terminal residual over the full reachable terminal plane. It constructs a rational control history that reaches that minimizer and verifies every control and flow bound. The exact squared norm is `2958186538093451/114292546875` (about `25882.584813940441`); the corresponding norm is about `160.88065394552709`. This proves the global optimum for the frozen reference variant, independently of either solver's floating-point result. The checker, generated harness sources, canonical input, and reports are included under [`evidence/b04-reference-v1`](evidence/b04-reference-v1/).

The project HiGHS adapter was run on the two-dimensional reachable terminal plane using the `QuadraticTerminal` convention `0.5*x'Q*x + q'x + c`. Its optimal result corresponds to a half squared norm of `12941.292406970297`; the required conversion `sqrt(2 * value)` gives `160.88065394552757`, about `4.8e-13` above the exact norm. The adapter reports numerical residuals but its raw diagnostics explicitly state `certificates=unavailable` and `bounds=unavailable`. Therefore the exact rational argument establishes the optimum, while the literal issue requirement for a HiGHS optimal-value certificate is not demonstrated by this adapter output.

## Original acados attempt

The original `FULL_CONDENSING_HPIPM` invocation returned `ACADOS_MAXITER` (status `2`) and process exit code `1`. Its residuals were stationarity `5.6455610319972038e-07`, dynamics `0`, inequality `4.5474735088646412e-13`, and complementarity `3.6124345366580944e-08`. Exact checking of the returned floating-point witness found maximum constraint deviation `6.4233063312713057e-12` and norm `160.88065394549295`; these do not change the non-success solver status.

## Owner-authorized follow-up acados attempt (2026-10-23)

The owner authorized one additional attempt after the original cap had been consumed. The same frozen `canonical-case.json`, generated OCP-QP source, pinned acados v0.6.0 build, `FULL_CONDENSING_HPIPM` route, 300-second wall limit and 8-GiB address-space cap were used. The client exited `1`; acados again returned `ACADOS_MAXITER` (status `2`). Residuals were stationarity `5.6455610319972038e-07`, dynamics `0`, inequality `4.5474735088646412e-13`, and complementarity `3.6124345366580944e-08`. The exact checker found maximum constraint deviation `6.4233063312713057e-12`, witness norm `160.88065394549295`, and exact reference optimum norm `160.88065394552709`. The close witness objective does not convert `ACADOS_MAXITER` into success.

The prior project HiGHS result was reused for the comparison; it reports numerical `optimal`, but exposes neither a certificate nor an optimality bound. The exact rational analysis independently proves the frozen variant's optimum, but does not satisfy that literal adapter-certificate requirement. No HiGHS rerun, solver tuning, benchmark, or third acados attempt was made. Raw stdout/stderr, exit, generated client, checker report and hashes for the new attempt are retained under `/tmp/opencode/acados-stage3-linux/harness/B04`; the combined manifest is `/tmp/opencode/acados-stage3-linux/followup-manifest.json` (SHA-256 `89b3e3475790286a62403bb15bf62fa9108716cd13ce1c89867fc8e407898f4a`).

## Evidence integrity

`evidence/b04-reference-v1/evidence-manifest.json` records SHA-256 hashes for the frozen case, exact checker, generated harnesses, compile logs, solver outputs, exits, and reports. The complete local bundle also remains at `D:\work\PhD\builds\acados-v0.6.0-build\smoke\b04-reference-v1`; the committed copy makes its text evidence reviewable in the PR. The pinned acados source checkout was commit `503364817c872d474ab5bed219c26760ac267769` (v0.6.0). The earlier all-terminal-state HiGHS preflight was an unreachable relaxation and is excluded from the evidence and acceptance results.

The acados-success and literal HiGHS-certificate criteria remain unmet after the authorized retry. The owner has accepted the result as an optional, inconclusive external cross-check rather than a gate on the main comparison program. The original acceptance criteria are not represented as technically satisfied; this disposition is recorded separately on the issue. No further acados attempt is authorized.
