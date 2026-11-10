# Strategy B actual joint-build phase observations

This follow-up keeps the original family-query report and capture immutable.
It separates actual sparse H-row assembly from public program construction in
the Strategy B execution path. The public `build_joint_program(problem,request)`
signature and untimed behavior remain unchanged. A private helper receives an
optional execution context only from the actual strategy run.

The existing `strategy-b/program-build` span remains the enclosing interval:

- `strategy-b/joint-h-assembly`: construction of sparse rows/bounds/lineage from
  the initial point, all state/control constraints, transitions and temporal rows.
- `strategy-b/objective-lift`: lifting the original terminal objective into the
  canonical full-history coordinate space, including dense quadratic storage.
- `strategy-b/program-freeze`: the actual `make_linear_program` or
  `make_convex_program` call, including creation/copying of its input values,
  validation and immutable snapshot construction. It is not an isolated native
  solver or isolated `numeric::snapshot` microtimer.

These spans describe the ordinary joint-program builder, not the separate exact-H proof reconstruction or compiled verifier.

The nonnegative enclosing-minus-children residual covers admission/capacity
checks, identity/map/result construction, operation lookup/closure overhead and
other gaps. It is not labelled sparse assembly or program snapshot work. An
unplanned/disabled collector cannot change mathematical results or failures.
Input/output sizes mean width→nonzeros for assembly, terminal-state dimension→
joint dimension for objective lift, and nonzeros→program variables for freezing.

Configure the repository itself once to share a build between the existing
Strategy B tests and this benchmark probe:

```sh
cmake -S . -B build/review05-build-phases -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCMAKE_PROJECT_CSL_INCLUDE="$PWD/benchmarks/reporting/review05/build_phase_probe.cmake"
cmake --build build/review05-build-phases \
  --target direct_joint_strategy_tests csl_review05_family_query -j2
ctest --test-dir build/review05-build-phases -R '^direct_joint_strategy_tests$' \
  --output-on-failure --no-tests=error
```

The hook is private benchmark tooling. It adds no installed target, public
library API or required dependency. The ordinary standalone review05 benchmark
CMake entry point also builds the same source.

The bounded follow-up uses the already authored scalar T=2/4/8 HORIZON01 and
constant-zero fixtures. It observes all three actual child intervals, their
nesting/order and sparse/program sizes, and independently checks original
families, direction minima and histories. Collector off/on groups are separate;
materialization-limit stops remain retained and cannot become mathematical
counterexamples merely because output is partial. Any timing figures are
initial descriptive observations, with no strategy ranking or universal scaling
claim. Isolated verifier timing, native-clock overhead and issue-wide ownership
review remain separate #95 gates. The report-only scalar 2D illustration in the
preceding family-query report remains applicable to these unchanged plants.
