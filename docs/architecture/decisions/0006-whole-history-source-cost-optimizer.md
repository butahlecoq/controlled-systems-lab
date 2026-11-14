# ADR 0006: Whole-history source-cost optimization

Date: 2026-11-14. Status: accepted for the incremental #1050 implementation.

## Context

The native comparison program needs an optimizer that searches the complete
state-and-control history under the original feasible relation. It must retain
the authored objective and preserve optional solver integrations without
turning a feasible numerical result into a claim of global optimality.

## Decision

`optimization::HistoryOptimizerPort` optimizes a `HistoryCostProgram` over the supplied complete feasible relation in canonical
`[x0, …, xT, u0, …, u(T−1)]` coordinates. It does not restrict candidates to a terminal-optimal fiber. Requests may use a supplied full-history start or an explicit backend cold start; in either case, the optimized variables remain every state and control coordinate.

The port recompiles the authored terminal and running formulas at admission, then checks that their quadratic and separate residual-norm representation matches the request. When a backend accepts a supplied start, the core checks the primal initialization readback and the backend's supplied zero-dual vector against its readback. A cold-start backend records its actual initialization policy and why readbacks are unavailable. For every backend call, the core checks the returned history shape and finiteness, full-relation feasibility, and backend objective against `evaluate_history_cost`. Dual-coordinate dimension belongs to the selected backend's actual solver layout. A successful result is a numerically checked feasible candidate. It is not a global-optimality proof, a validated inclusion result, or a nonlinear physical-safety certificate.

The optional `CSL_ENABLE_CASADI` build registers `csl.nlp.casadi-ipopt.history-cost@1` and `csl.conic.superscs.history-cost@1`. IPOPT accepts a validated supplied primal and zero-dual start. SuperSCS accepts only an explicit backend cold start; its fresh conic function receives no primal or dual warm-start values, and its interface does not expose internal start readbacks. The SuperSCS v1 provider handles affine-plus-norm source objectives and encodes every residual norm as an exact second-order cone. Both providers optimize all canonical history variables and the core independently checks the full H relation and authored source objective. The core API and tests build without CasADi; a build without the optional library cannot select these providers. The existing `csl.nlp.casadi-ipopt.fixed-tail@1` provider and its fixed-tail request checks are unchanged.

The public CMake target is `CSL::history_optimizer`. With the optional backend enabled, `CSL::casadi_history_optimizer` and `CSL::casadi_superscs_history_optimizer` export their registration factories. The `history_optimizer_2d_example` executable uses SuperSCS and writes an actual solver result to `history.csv` and `history.svg`; its source objective is
`||x2 − (1,1)||₂ + 0.5(|u0| + |u1|)` for a two-step planar integrator with `u0,u1 ∈ [0,1]`.

## Consequences

The selected result is checked for feasibility and source-objective agreement,
but these checks do not establish global optimality, validated set inclusion,
or nonlinear physical safety. Optional backend availability is a build-time
capability. Strategies A/B and the complete three-task × two-strategy ×
five-family comparison matrix remain required under #1050.
