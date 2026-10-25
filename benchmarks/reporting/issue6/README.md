# B06 finite-action reference

This reference combines the L09 displayed model with the owner's 2026-10-25
confirmation that each disturbance component ranges independently over
`[-1,1]` at each of five discrete stages. The article does not print this
numerical disturbance set, so this case is not a historical reproduction.
`B06-historical` remains unchanged and non-executable.

The project runner calls the existing `finite_action_minimax` implementation.
The separate integer-scaled exhaustive oracle enumerates every action sequence
and every disturbance-corner history. It uses exact integer state coordinates
scaled by 1500 and an objective-squared denominator of 9,000,000. Together,
these give an exact reference for the explicitly stated rational case. The
solver measurement itself uses the project's binary64 numerical assurance.

## Reproduce

Configure and build a clean Release driver:

```sh
cmake -S . -B build/issue6-b06 -DBUILD_TESTING=OFF \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF \
  -DCSL_BUILD_ISSUE6_B06_REPORT=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/issue6-b06 --target csl_issue6_b06_report csl_issue6_b06_exact_oracle --parallel 4
```

Capture the oracle, one geometry record, and one excluded warmup plus seven
measured single-call observations:

```sh
build/issue6-b06/csl_issue6_b06_exact_oracle > exact-oracle.json
build/issue6-b06/csl_issue6_b06_report --geometry > geometry.json
build/issue6-b06/csl_issue6_b06_report --measure 7 > raw-runs.jsonl
python3 scripts/reports/issue6/check_capture.py <result-directory>
python3 scripts/reports/issue6/render.py <result-directory>
```

The measurement interval includes construction of the immutable solver request
and the public solver call. It excludes process startup, serialization, exact
oracle execution, figure generation, and HTML rendering. The runner verifies
all 3,125 plans and records 3,200,000 terminal-vertex evaluations per call.
Seven observations describe this one case; they do not support a comparison,
speedup, or general scalability claim. The `[-1,1]^2` disturbance set and the
interpretation of `-10/T` with discrete `T=5` are explicit reference-case
inputs, not recovered historical run details.
