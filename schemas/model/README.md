# Continuous affine model document v1

`csl.continuous-model/1` is a separate, executable model-input document for
`input::load_continuous_model`. It does not change the closed
`csl.scenario/1` discrete transition grammar. A loaded document retains its
original bytes and a SHA-256 content digest. Call `model::discretize` explicitly
before passing the returned discrete `SystemModel` and physical times to
`model::snapshot` or a later problem builder.

`times` contains T+1 finite strictly increasing physical state times. `A`, `B`,
`E` and `offset` are continuous-time rates in `x'=Ax+Bu+Ew+a`, not already
discrete transition matrices. Their shapes are n×n, n×m, n×p and n. A 0-column
matrix needs explicit `rows`, `cols` and empty `values`. The hold is zero order
for both u and w over each `[times[k],times[k+1]]`. An LTI record is constant
throughout the grid. Each LTV `start`/`end` pair is linearly interpolated within
its own interval; adjacent interval endpoints may differ.

The integration settings are positive finite local absolute/relative tolerances
and a positive attempt limit per interval. The adapter uses RK4 step doubling,
returns the accepted two-half-step solution and records the largest observed
local difference/15 for each interval. That number is an estimate, not a
certified global error bound. A failed or exhausted integration returns no
discrete model. Descriptor mass matrices, nonlinear dynamics and alternative
input holds require separate capabilities.

The [JSON schema](continuous-v1.schema.json) is an authoring aid. The native
loader also enforces duplicate-key, finite binary64, exact-integer, quota,
matrix-shape and time-grid rules. See the
[minimal 2D input](../../tests/fixtures/input/continuous-double-integrator.json).
