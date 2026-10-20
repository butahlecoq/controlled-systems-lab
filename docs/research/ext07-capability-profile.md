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

The scalar two-stage report is the largest saved measurement by horizon and
path count. The 3D control-box case is the largest named independent continuous
oracle by state and control dimension. The reports measure their own fixtures;
the unit-test cases are correctness evidence and are not timing samples.

## Declared adapter and verifier domains

| Component | Declared domain | Resource boundary | Current evidence limit |
| --- | --- | --- | --- |
| Joint-H path construction and direct-trajectory adapter | Admitted finite hybrid profiles whose mode flows, controls, invariants, guards, and resets can be represented in the joint H relation; terminal objectives are supplied separately and must be admitted by the selected adapter | Configured maximum variables, rows, and matrix elements; complete path inventory is preflighted before branch construction | Named reports cover at most 3 modes, 3 edges, 2 paths, and horizon 2 |
| General projected-state reachability adapter | Finite-horizon, any-dimension paths admitted by the joint-H composer and selected geometry provider | Relation limits plus provider admission against the complete terminal projection request and its row cap | Public contract cases cover one-step scalar and two-stage 1→2→1 state dimensions |
| Exact linear-H family verifier | Finite-horizon H relations with linear terminal objectives and supported exactly representable binary64 inputs | Exact row, integer-bit, cancellation, and Fourier-Motzkin intermediate limits | Literal continuous oracles cover joint dimensions 4, 7, 8, and 12; the named 3D oracle has one path |
| One-step and single-parameter scalar interval verifiers | One-step: horizon 1, scalar states/control, scalar interval, singleton, empty, or universal set representations; feasible branches require a bounded control interval; deterministic exactly representable scalar affine reset; scalar linear terminal objective. Single-parameter: finite horizon, scalar stage-indexed interval controls/invariants/guards, exactly one bounded non-singleton control and singleton controls elsewhere, deterministic exactly representable scalar affine resets, scalar linear terminal objective | Exact arithmetic and interval row limits | One-step and finite-horizon cases; no higher-dimensional state claim |
| Two-parameter scalar polygon verifier | Scalar state, scalar interval controls, invariants and guards, deterministic exactly representable scalar affine resets; exactly two bounded non-singleton interval controls at distinct stages, all other controls singleton, finite horizon, scalar linear terminal objective | Exact representability, bounded polygon geometry and row/vertex limits | The saved fixture has horizon 2; tests also place the two free controls at separated stages in a horizon-3 case |

All family verifiers provide numerical assurance only. Validated objective
assurance and validated family coverage remain unsupported. Adapter preflight
does not imply that every possible provider operation or objective policy is
admitted; those gaps remain tracked in EXT-07.

## Interpretation

These finite fixtures establish behavior at the listed dimensions and graph
sizes only. They do not establish a maximum supported dimension or mode count,
resource scaling, asymptotic runtime, or general scalability. Mode and edge
count limits bound enumeration, but a finite mode graph can still produce
exponentially many paths as the horizon grows. Keep larger capability and
resource claims open until separate evidence measures and validates them.
