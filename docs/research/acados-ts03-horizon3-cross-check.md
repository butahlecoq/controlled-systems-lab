# T-S03 horizon-3 acados cross-check

Status: one research-only solve completed on 2026-10-20. This is a single-witness cross-check, not a benchmark, paired comparison, or reproduction claim.

## Case and method

The canonical case is `T-S03-horizon3-double-integrator`: zero initial state; three unit-duration steps; dynamics `p' = p + v + u/2`, `v' = v + u`; `u ∈ [-1,1]`; intermediate bound `|p1| ≤ 2`; and terminal objective `1/2*((p3-4)^2+v3^2)`. The canonical JSON was the input to the harness generator. It supplied the horizon, row-major dynamics matrix, control and state bounds, initial state and terminal quadratic. The generator converted the row-major dynamics matrix to the column-major layout required by acados' C API.

The generated C program exercised the pinned acados v0.6.0 OCP-QP API with `FULL_CONDENSING_HPIPM`. It was compiled with the existing native MSVC Release libraries and `/MT`. The solver executable was invoked exactly once. No source, build configuration, repository dependency, or project code was changed for this run.

The independent checker reads the same canonical JSON, validates its frozen inputs, reconstructs each printed IEEE-754 number as an exact binary rational, checks the dynamics and bounds, evaluates the objective, and computes the exact optimum by rational active-set enumeration. The intermediate position bound is redundant for these inputs because `p1=u0/2 ∈ [-1/2,1/2]`. The reduced objective is convex; at the reported exact optimum `(1,12/13,-1)`, its gradient `(-8/13,0,8/13)` satisfies the box KKT signs, certifying global optimality.

## Result

- acados status: `0`; executable exit code: `0`.
- Exact global optimum: `8/13` (`0.61538461538461542`), attained at controls `(1,12/13,-1)` and terminal state `(44/13,12/13)`.
- Witness objective, including the canonical offset: `0.61538461554122592`.
- Exact objective gap above the optimum: `1.566105492798635e-10`.
- Largest exact constraint violation reconstructed from the printed witness: `5.0568204359707952e-14`.
- acados infinity-norm residuals: stationarity `6.482370196181364e-12`; dynamics `0`; inequality `5.3801540030581483e-14`; complementarity `4.1125843696191492e-09`.
- acados variable-only objective: `-7.3846153844587743`; adding the canonical offset `8` gives the witness objective above.

The objective gap and solver residuals are reported separately. Their numerical magnitudes are consistent with the solver's reported accuracy; the objective gap is not treated as a residual or as a substitute for the exact feasibility and optimal-value checks. The witness is floating-point output, so its reconstructed rational constraints are not exactly zero.

## Evidence and limits

The canonical inputs, generator, generated C source, compiled object and executable, compile output, raw solver output and exit code, exact checker and JSON report are retained in the local smoke directory. `bundle-manifest.json` records each artifact's size and SHA-256. The canonical input SHA-256 is `BE157736B4448C7AE15A7473D437D146151D65BF92558620D9C40462E68B0CBB`.

This result covers only this frozen synthetic case, the recorded Windows/MSVC environment, acados v0.6.0, and one OCP-QP solve. It establishes no timing, performance, general platform support, or alignment with the later fixture in #421.
