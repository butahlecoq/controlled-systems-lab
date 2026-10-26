# Independent nonlinear plant replay

`CSL::simulation` consumes one complete, ordered control vector per physical
interval. The caller supplies a separate plant transition and terminal
objective, explicit plant identity and source, named parameters and units,
initial state, strictly increasing physical times with a declared time unit,
state/control units,
integration method, control-hold convention and finite nonnegative numerical
tolerances. The tolerances are retained metadata for this exact-map path; they
do not certify callback error or alter its returned state. The current method
is an authored exact discrete transition map:
the callback receives the state at the interval start and its constant control,
then returns the state at the next time. It is not a continuous ODE integrator.

`replay` records the complete declaration (including the declared initial
state), controls, computed states, original
plant objective and its unit, field-specific diagnostics and a separate
steady-clock replay duration. A missing declaration or incomplete control
history returns `unavailable` with named `missing_prerequisites`. Invalid
numeric inputs, nonfinite transition/objective outputs, callback failures,
cancellation and deadline exhaustion remain distinct statuses. The execution
context is checked after transition and objective callbacks as well as before
each stage. A failed replay
retains its available prefix but has no completed objective. The callback and
its declared source are caller-supplied evidence; this interface does not prove
that a claimed physical plant or exact transition is scientifically valid.

For the literal scalar plant `x[k+1] = x[k] + u[k] + u[k]^2`, with `x[0]=0`,
two intervals and a terminal-state objective, controls `(0,1)` and
`(0.5,0.5)` both sum to 1 under the separate linear integrator. Their nonlinear
terminal states and objectives are 2 and 1.5. The module test checks both
entire trajectories. A two-state interval-dependent fixture checks that
swapping controls changes the result and that physical times are passed in
the declared order.

This is sampled simulation of chosen controls. It makes no claim that a replay
control is feasible or optimal for the independent plant, that a linear
optimal-family claim transfers to the plant, or that a historical result was
reproduced. The recovered B04 table supplies some parameters and rounded
outcomes, but not a canonical complete control history and matching timing and
integration convention. No B04 plant adapter is provided until those inputs
are sourced. Association with linear witnesses belongs to VIZ-04, not this
plant stepper.

The [VIZ-04 analytic replay example](../examples/viz04-replay-comparison.html)
shows two labelled 2D projections of selected paths from a four-state toy plant.
It is not a B04 replay or a reachable-set boundary.
