# Whole-history source-cost optimizer

`optimization::HistoryOptimizerPort` optimizes a `HistoryCostProgram` over the supplied complete feasible relation in canonical
`[x0, …, xT, u0, …, u(T−1)]` coordinates. It does not restrict candidates to a terminal-optimal fiber. The request carries one initial full history for numerical initialization; the optimized variables remain every state and control coordinate.

The port recompiles the authored terminal and running formulas at admission, then checks that their quadratic and separate residual-norm representation matches the request. After a backend call it checks the actual primal initialization readback, agreement between the backend's supplied zero dual vector and its readback, the returned history shape and finiteness, full-relation feasibility, and the backend objective against `evaluate_history_cost`. Dual-coordinate dimension belongs to the selected backend's actual solver layout. A successful result is a numerically checked feasible candidate. It is not a global-optimality proof, a validated inclusion result, or a nonlinear physical-safety certificate.

The optional `CSL_ENABLE_CASADI` build registers `csl.nlp.casadi-ipopt.history-cost@1`. It gives IPOPT all canonical history variables and uses a separate epigraph for every source residual norm. The core API and tests build without CasADi; a build without the optional library cannot select this provider. The existing `csl.nlp.casadi-ipopt.fixed-tail@1` provider and its fixed-tail request checks are unchanged.

The public CMake target is `CSL::history_optimizer`. With the optional backend enabled, `CSL::casadi_history_optimizer` also exports the registration factory. The `history_optimizer_2d_example` executable writes an actual solver result to `history.csv` and `history.svg`; its source objective is
`||x2 − (1,1)||₂ + 0.5(|u0| + |u1|)` for a two-step planar integrator with `u0,u1 ∈ [0,1]`.
