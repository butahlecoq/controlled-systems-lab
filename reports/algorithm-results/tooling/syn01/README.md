# SYN-01 nominal forward report

This is a descriptive, single-adapter measurement of the public
`nominal_forward()` operation on the two scalar analytic fixtures already
present in `tests/unit/reachability/nominal_forward_tests.cpp`. It makes no
comparison, speedup, capacity, or scalability claim. Geometry/reachability
support remains **Unestablished**.

The two-step integrator uses `x0=0`, controls `u0,u1 in [0,1]`, and
`x[t+1]=x[t]+u[t]`; expected marginals are `{0}`, `[0,1]`, `[0,2]`. The
authored LTV fixture uses `x0=1`, `x1=2*x0+u0+1`, and
`x2=-x1+2*u1-2`, with state constraints `X0=[0,2]`, `X1=[3,4]`,
`X2=[-5,-4]`; expected marginals are `{1}`, `[3,4]`, `[-5,-4]`. The
unconstrained propagated terminal image before applying `X2` is `[-6,-3]`.

Every repetition constructs and resolves a fresh problem and selects fresh
providers. One warmup plus seven measured repetitions run per fixture, with
fixture order alternating forward/reverse each round. The driver reports
`setup_ns`, `solve_ns`, `oracle_ns`, and `execute_ns` separately. Setup covers
problem construction/resolution and provider registration/selection/preparation;
solve covers `nominal_forward()`; oracle covers immediate result consumption
and a complete one-dimensional H-row bound calculation; execute spans setup
through that independent check. Build, process startup, JSON serialization,
collector validation, and rendering are excluded. Per-provider operation
counts come from returned stage provenance; provider operation durations are
not available through the public seam.

The event format records an explicit timing state for each phase: `available`
for a completed phase, `partial` when a phase throws after beginning, and
`not_reached` when execution never entered it. A not-reached duration is JSON
`null`; partial durations retain elapsed time. This prevents zero from being
mistaken for a measured phase. The record separately identifies the nominal
forward module at the CMake project version and the fixed measured source
commit. It lists selected provider IDs and actual versions, including the
transitive HiGHS, Qhull, and hull-reducer registrations used by affine sum.

The oracle checks every returned halfspace and equality row against literal
expected bounds over the returned binary64 values. It is not a real-arithmetic
certificate. Failures and unsupported/empty outcomes remain in captured raw
driver output under a `collection-failures/` record marked
`accepted_measurement: false`; they are not filtered or presented as a valid
report bundle. Only a complete, oracle-passing record can enter the registered
report catalogue.

`records.json` and `raw-events.jsonl` are the saved source for all derived
tables and figures. Run `render_saved.py` to regenerate HTML and SVG without
executing the solver. `scripts/reports/syn01_registered_reports.py` validates
the native bundle and maps it to the repository's schema-3 envelope, manifest,
staging, and deterministic offline ZIP conventions. The publication map
documents the crosswalk. Publication remains pending until independent report
review and an authorized catalogue update.

The report does not claim a measured limiter or application capacity. A
separate source-level profile is required before attributing latency to a
specific implementation path.
