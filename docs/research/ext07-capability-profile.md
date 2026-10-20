# EXT-07 capability profile and fixture report

This profile records the declared finite-hybrid adapter domains and the
dimension and mode counts exercised by current tests and saved reports. A
declared input domain is not a runtime guarantee: path counts, Fourier-Motzkin
intermediates, exact integer sizes, and provider row growth can make a request
unsupported within configured resource limits.

## Named fixture evidence

Here `n` is the state dimension, `m` is the continuous control dimension per
stage, and `joint variables` counts the coordinates retained by the full
branch relation. Report measurements are separate from unit-test oracle
fixtures.

| Fixture | `n` | `m` | Horizon | Modes | Edges | Allowed paths | Joint variables | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| One-step scalar interval | 1 | 1 | 1 | 2 | 1 | 1 | 4 | [Saved measured report](../../reports/algorithm-results/ext07-hybrid-2cba9c13b79afd2b/index.html), [unit oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| Two-stage scalar polygon | 1 | 1 | 2 | 3 | 3 | 2 | 7 per path | [Saved measured report](../../reports/algorithm-results/ext07-hybrid-two-parameter-00ac6fb75d7cab95/index.html), [unit oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| One-step 2D box | 2 | 2 | 1 | 2 | 1 | 1 | 8 | [Independent literal H oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| One-step 3D control box | 3 | 3 | 1 | 2 | 1 | 1 | 12 | [Independent literal H oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| One-step three-control simplex with existential reset | 1 | 3 | 1 | 2 | 1 | 1 | 6 | [Independent three-dimensional optimal-family oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| One-step truncated three-control box with existential reset | 1 | 3 | 1 | 2 | 1 | 1 | 6 | [Independent non-simplex optimal-family oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| One-step four-control simplex with existential reset | 1 | 4 | 1 | 2 | 1 | 1 | 7 | [Independent four-dimensional optimal-family oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| Two-stage tied four-control branches with set-valued reset | 1→2→2 | 2→2→0 | 2 | 3 | 3 | 2 | 12 per path | [Independent continuous branch-family oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| Three-branch heterogeneous terminal preflight inventory | 1→{1,2,3} | 0 | 1 | 4 | 3 | 3 | 3, 4, and 5 per path | [Full-inventory preflight and relation-dimension test](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| Two-stage scalar projected interval | 1 | 1 | 2 | 3 | 2 | 1 | 7 | [Independent projected-set contract oracle](../../tests/contract/synthesis/hybrid_reachability_contract.cpp) |
| Two-stage existential 1→2→1 reset projection | 1→2→1 | 1→0 | 2 | 3 | 2 | 1 | 8 | [Set-valued reset contract oracle](../../tests/contract/synthesis/hybrid_reachability_contract.cpp) |
| Two successive existential 1→2→1 reset projection | 1→2→1 | 1→0 | 2 | 3 | 2 | 1 | 8 | [Two-reset contract oracle](../../tests/contract/synthesis/hybrid_reachability_contract.cpp) |
| One-step existential reset optimal face | 1 | 1 | 1 | 2 | 1 | 1 | 4 | [Independent continuous-family verifier oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| One-step coupled 2-control polytope with existential reset | 1 | 2 | 1 | 2 | 1 | 1 | 5 | [Independent slanted optimal-face oracle](../../tests/unit/synthesis/hybrid_path_program_tests.cpp) |
| Four-mode branching resource-bound check | 1 | 0 | 2 | 4 | 4 | 2 | 5 per path | [Capability, raw-graph, and row-limit test](../../tests/unit/model/hybrid_system_test.cpp) |
| Eight-stage path-enumeration cap | 1 | 0 | 8 | 17 | 30 | 256 at cap | 17 planned per path; not composed | [Independent raw-graph and exact-cap test](../../tests/unit/model/hybrid_system_test.cpp) |

The scalar two-stage report is the largest saved measurement by horizon and
path count. The eight-stage graph is the largest named capability-count
fixture by mode, edge, horizon, and path count: its independent raw-graph
oracle enumerates all 256 histories, the production enumerator agrees at a
256-path cap, and the capability report rejects a 255-path cap without a
partial count. This exercises enumeration admission only; it does not compose
256 relations or measure scaling. The four-mode graph remains the largest
composed-resource check: its 5-variable relations fit the configured 3-row,
15-matrix-element budget and reject a 2-row budget. The 3D control-box case
remains the largest named independent continuous oracle by state dimension;
the four-control simplex now has the largest control dimension. The coupled
2-control reset case adds a non-axis-aligned control polytope and a
proper-subset rejection. A two-stage case now checks two distinct tied
four-control optimal faces through an existential set-valued reset; the raw
graph oracle independently enumerates both parallel-edge histories, and a
feasible narrowed face is refuted on the wide branch. This raises the named
multi-path continuous-family evidence to four controls, three modes, three
edges, horizon two, and 12 joint variables per branch. The reports measure
their own fixtures;
the unit-test cases are correctness evidence and are not timing samples.

## Declared adapter and verifier domains

| Component | Declared domain | Resource boundary | Current evidence limit |
| --- | --- | --- | --- |
| Joint-H path construction and direct-trajectory adapter | Admitted finite hybrid profiles whose mode flows, controls, invariants, guards, and resets can be represented in the joint H relation; terminal objectives are supplied separately and must be admitted by the selected adapter | Configured maximum variables, rows, and matrix elements; complete path inventory is preflighted before branch construction | Named reports cover at most 3 modes, 3 edges, 2 paths, and horizon 2 |
| General projected-state reachability adapter and portfolio wrapper | Finite-horizon, any-dimension paths admitted by the joint-H composer and selected geometry provider; portfolio retains every allowed path as a separate result | Complete path preflight plus relation limits and provider row caps; portfolio reports operation maxima, provider input/output row totals/maxima, and optional provider-reported peak rows/elements plus generated-row and charged-operation totals/maxima | Public contract cases cover one-step scalar, two-stage scalar projection `[0, 2]`, two-stage 1→2→1 deterministic and existential set-valued resets, and two parallel projected branches with resource aggregation |
| Exact linear-H family verifier | Finite-horizon H relations with linear terminal objectives and supported exactly representable binary64 inputs | Exact row, integer-bit, cancellation, and Fourier-Motzkin intermediate limits; branch reports expose configured caps and measured peak rows, generated rows, charged elimination operations, and maximum observed integer bits | Literal continuous oracles cover joint dimensions 4, 5, 6, 7, 8, and 12; set-valued-reset cases verify complete 1D, slanted 1D, 3D simplex, 3D truncated-cube, 4D simplex, and two distinct multi-stage four-control branch faces, and reject narrowed candidates; the named 3D box oracle has one path |
| One-step and single-parameter scalar interval verifiers | One-step: horizon 1, scalar states/control, scalar interval, singleton, empty, or universal set representations; feasible branches require a bounded control interval; deterministic exactly representable scalar affine reset; scalar linear terminal objective. Single-parameter: finite horizon, scalar stage-indexed interval controls/invariants/guards, exactly one bounded non-singleton control and singleton controls elsewhere, deterministic exactly representable scalar affine resets, scalar linear terminal objective | Exact arithmetic and interval row limits | One-step and finite-horizon cases; no higher-dimensional state claim |
| Two-parameter scalar polygon verifier | Scalar state, scalar interval controls, invariants and guards, deterministic exactly representable scalar affine resets; exactly two bounded non-singleton interval controls at distinct stages, all other controls singleton, finite horizon, scalar linear terminal objective | Exact representability, bounded polygon geometry and row/vertex limits | The saved fixture has horizon 2; tests also place the two free controls at separated stages in a horizon-3 case |

All family verifiers provide numerical assurance only. Validated objective
assurance and validated family coverage remain unsupported. Solver, trajectory,
reachability, and family-verification boundaries preflight their declared
inventories. This does not establish model-wide admission for every requested
operation across the complete mode/edge structure, or complete terminal-policy
semantics beyond the declared objective-class/assurance/tolerance checks; those
gaps remain tracked in EXT-07.

Exact-verifier resource counters cover Fourier-Motzkin elimination in both
minimization and inclusion checks. Charged operations use the verifier's
existing per-call budget accounting; generated rows and peak rows are observed
across branch elimination calls. These values exclude relation parsing,
rational comparisons, wall time, and memory use, and do not establish scaling.
The polyhedral H projection provider separately reports logical coefficient
rows/elements, successive elimination-output rows, and charged row-pair
operations to projected-state reachability; other geometry providers may omit
these observations. They exclude allocator overhead, wall time, and memory use.

## Interpretation

These finite fixtures establish behavior at the listed dimensions and graph
sizes only. They do not establish a maximum supported dimension or mode count,
resource scaling, asymptotic runtime, or general scalability. Mode and edge
count limits bound enumeration, but a finite mode graph can still produce
exponentially many paths as the horizon grows. Keep larger capability and
resource claims open until separate evidence measures and validates them.
