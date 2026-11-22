# ADR 0022: Preserve MPC compiled coordinate and row layout

Date: 2026-11-22
Status: Accepted

## Context

The receding-horizon compiler maps authored state, control, stage, and terminal
constraints into one quadratic program. Tests inspect specific rows and
columns, so the layout must remain explicit when remaining-horizon compilation
shifts the local stage origin.

## Decision

- Order compiled decision coordinates as the full state history followed by
  the control history. A terminal constraint addresses only `x[T]`; there is
  no terminal control column.
- Preserve the compiled row groups: initial and dynamics equations, state and
  control bounds, stage availability constraints, then terminal-state
  constraints. Stage constraints precede terminal rows.
- Compile a remaining horizon against its local stage sequence while retaining
  the source constraint at each corresponding absolute stage.

## Consequences

Source-model regression tests may pin selected row/column positions to verify
that coupling coefficients and terminal sections land in the intended blocks.
Changing the layout requires updating the compiler contract and its independent
fixtures together; terminal input constraints remain unsupported by this
state-only terminal representation.
