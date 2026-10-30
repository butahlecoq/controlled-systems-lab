# Independent nonlinear plant replay

`CSL::simulation` consumes one complete, ordered control vector per physical
interval. The caller supplies a separate plant model and terminal objective,
explicit plant identity and source, named parameters and units, initial state,
strictly increasing physical times with a declared time unit, state/control
units, integration method and control-hold convention.

The exact-map method retains finite nonnegative numerical-policy tolerances as
metadata; they do not certify callback error or alter the returned state. Its
transition callback receives the state at the interval start and its constant
control, then returns the state at the next time.

The adaptive method requires a continuous derivative callback and
`IntegrationLimits` with positive absolute/relative tolerances and a nonzero
attempt budget per interval. It uses adaptive classical RK4 step doubling and
advances with the accepted two-half-step result. Each completed interval
records accepted/rejected attempts and a per-coordinate maximum of
`abs(two_half-full)/15` over accepted steps. These are observed local estimates,
not certified global error bounds. The record persists the applied limits and
the estimates with their state-coordinate units. Exact-map replay has no
applied integration limits or numerical integration residual.

`replay` records the complete declaration, controls, computed states, original
plant objective and its unit, field-specific diagnostics and a separate
steady-clock replay duration. The VIZ-04 v3 artifact saves named residual
measurements, numerical-policy metadata, applied integration limits and
per-interval receipts. V1 and v2 artifacts remain readable; v1 did not persist
residual evidence or numerical policy, while v2 had residual applicability and
policy metadata but no applied-limit receipt. Missing declarations or
incomplete control history return `unavailable` with named prerequisites.
Invalid numeric inputs, nonfinite outputs, callback failures, cancellation and
deadline exhaustion remain distinct statuses. The execution context is checked
before each stage and within integration. A failed replay retains its available
prefix but has no completed objective. The callbacks and their declared source
are caller-supplied evidence; this interface does not prove the scientific
validity of a claimed plant.

For the literal scalar plant `x[k+1] = x[k] + u[k] + u[k]^2`, with `x[0]=0`,
two intervals and a terminal-state objective, controls `(0,1)` and
`(0.5,0.5)` both sum to 1 under the separate linear integrator. Their nonlinear
terminal states and objectives are 2 and 1.5. The module test checks both
entire trajectories. A two-state interval-dependent fixture checks that
swapping controls changes the result and that physical times are passed in
declared order. A separate adaptive-RK4 check uses `x'=1+x^2`, `x(0)=0` and the
independent analytic solution `x(t)=tan(t)`.

This is sampled simulation of chosen controls. It makes no claim that a replay
control is feasible or optimal for the independent plant, that a linear
optimal-family claim transfers to the plant, or that a historical result was
reproduced. The recovered B04 table supplies some parameters and rounded
outcomes, but not a canonical complete control history and matching timing and
integration convention. No B04 plant adapter is provided until those inputs
are sourced. Association with linear witnesses belongs to VIZ-04, not this
plant stepper.

VIZ-04 records policy class separately from replay status and objective. The
nominal reference, frozen-coefficient regulator and selected linear witnesses
must not be collapsed into one policy or one objective record. The replay
artifact reports nonlinear feasibility, objective quality and global
optimality as `not_checked` unless separate evidence is added; a completed
replay alone establishes none of those claims. In particular, B04's nominal
`u=0` row is not a demonstrated zero-control solution from the perturbed B04
initial state.

The [VIZ-04 analytic replay example](../examples/viz04-replay-comparison.html)
shows two labelled 2D projections of selected paths from a four-state toy plant.
It is not a B04 replay or a reachable-set boundary.
The [adaptive RK4 oscillator example](../examples/adaptive-ode-replay.html)
shows a supported two-state integration against its analytic phase-plane curve.
