# ADR 0022: Preserve MPC compiled coordinate and row layout

Date: 2026-11-22
Status: Accepted

## Context

The receding-horizon compiler maps authored state, control, stage, and terminal
constraints into one quadratic program. Tests inspect specific rows and
columns, so the layout must remain explicit when remaining-horizon compilation
shifts the local stage origin.

## Decision

- Order the base decision coordinates as the full state history followed by
  the control history. Append optional positive-part witness coordinates after
  those base blocks. A terminal constraint addresses only `x[T]`; there is no
  terminal control column.
- Preserve the compiled row groups: initial and dynamics equations, state and
  control bounds, temporal rows, then optional positive-part witness and budget
  rows. The temporal block contains authored stage rows followed by
  terminal-state rows; stage rows precede terminal rows.
- Compile a remaining horizon against its local stage sequence while retaining
  the source constraint at each corresponding absolute stage.

## Consequences

Source-model regression tests may pin selected row/column positions to verify
that coupling coefficients and terminal sections land in the intended blocks.
Positive-part budgets add auxiliary variables and rows after the base history
and temporal blocks. Changing this layout requires updating the compiler
contract and its independent fixtures together; terminal input constraints
remain unsupported by this state-only terminal representation.
