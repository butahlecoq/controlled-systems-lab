# OPT-12 cross-query LP warm starts

Date: 2026-10-18. This design is limited to an optional HiGHS simplex workspace optimization. It is independent of the archival within-solve basis reuse in OPT-06.

## Contract

- Warm-start state belongs to one exclusive `LPWorkspace`. It is private to the selected backend and is never serialized, shared across workspaces, or exposed as a HiGHS container.
- The adapter caches only a valid native simplex basis returned by a completed optimal solve. A cache entry records its producing native adapter/version and row/column dimensions.
- A cached basis is eligible only when it came from this workspace and both row and column counts match the next LP. Objective, coefficient, RHS, and bound changes with unchanged dimensions are allowed as hints; the backend remains responsible for accepting or rejecting the basis for the changed numerical model.
- A dimension mismatch, unavailable basis, unsupported input, interruption, exception, rejected basis, or non-optimal/numerically rejected result invalidates the cache. The next solve runs cold when no eligible hint exists.
- Basis installation is advisory. Rejection or an invalid warm result triggers a new cold solve with a fresh native solver. The cold result is authoritative. The adapter does not turn a hint into an outcome claim or evidence.
- Cold and warm execution use the same mathematical LP and result checks. Correctness is judged by independently known feasibility/status and primal checks, including changed rows, columns, variable/row bounds, and degenerate models.
- The feature is opt-in and disabled by default. Raw diagnostics identify cache state, compatibility, basis acceptance, fallback, setup time, solve time, and simplex iterations when available.

## Validation and cost observation

Contract tests compare independently checked cold and warm outcomes for optimal and infeasible LPs after compatible changes, and exercise dimension changes, degenerate bases, rejected hints, and two independent workspaces. The observations separate model setup from solve work. A tiny LP records the basis-transfer overhead even when the warm path saves no simplex iterations; no general speedup claim follows from the test.

## Limits

The initial implementation is specific to HiGHS simplex. Other LP backends remain cold unless they implement their own private state under the same workspace isolation rule. Numerical solver reports remain subject to the adapter's existing binary64 feasibility checks and do not become mathematical certificates through basis reuse.
