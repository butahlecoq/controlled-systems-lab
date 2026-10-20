# B04 reference cross-check attempt

This evidence belongs to issue #517 and the separate owner-authorized variant `b04-reference-v1`. It is an unsuccessful one-run acados attempt; it does not complete the ticket and makes no historical reproduction claim.

## Frozen variant

The canonical input is `canonical-case.json` in the local evidence bundle. It uses the displayed B04 dynamics and printed initial state, horizon 16, continuous controls in `[-1,1]` at all stages, and the stated flow-box bounds at stages 1 through 16. `benchmarks/scenarios/b04-historical.json` was not changed. The published objective `30.899` is not an acceptance target: the displayed terminal plane has a different optimum, and the historical discrepancy remains unresolved.

## Independent exact result

The exact checker uses rational arithmetic to minimize the squared terminal residual over the full reachable terminal plane. It constructs a rational control history that reaches that minimizer and verifies every control and flow bound. The exact squared norm is `2958186538093451/114292546875` (about `25882.584813940441`); the corresponding norm is about `160.88065394552709`. This proves the global optimum for the frozen reference variant, independently of either solver's floating-point result.

The project HiGHS adapter was run on the two-dimensional reachable terminal plane using the `QuadraticTerminal` convention `0.5*x'Q*x + q'x + c`. Its optimal result corresponds to a half squared norm of `12941.292406970297`; the required conversion `sqrt(2 * value)` gives `160.88065394552757`, about `4.8e-13` above the exact norm. The adapter reports numerical residuals; the exact rational argument supplies the independent global-optimality proof.

## Single acados attempt

The one permitted `FULL_CONDENSING_HPIPM` invocation returned `ACADOS_MAXITER` (status `2`) and process exit code `1`. Its residuals were stationarity `5.6455610319972038e-07`, dynamics `0`, inequality `4.5474735088646412e-13`, and complementarity `3.6124345366580944e-08`. Exact checking of the returned floating-point witness found maximum constraint deviation `6.4233063312713057e-12` and norm `160.88065394549295`; however, these do not change the non-success solver status. The acceptance criterion requiring an acados solve with success status is therefore unmet. The solver was not invoked again.

## Evidence location and integrity

The complete local evidence bundle is at `D:\work\PhD\builds\acados-v0.6.0-build\smoke\b04-reference-v1`. `evidence-manifest.json` records SHA-256 hashes for the frozen case, generated harnesses, binaries, compile logs, solver outputs, exits, and exact checker reports. The pinned acados source checkout was commit `503364817c872d474ab5bed219c26760ac267769` (v0.6.0). The earlier all-terminal-state HiGHS preflight was an unreachable relaxation and is excluded from the evidence manifest and acceptance results.

Issue #517 must remain open: its acados success criterion was not met, and this note records an attempt rather than ticket completion.
