# EXT-04 affine synthesis example

The optional C++ driver `csl_ext04_affine_synthesis_report` synthesizes a
one-transition affine observation policy for a two-state noisy integrator. Its
joint V-domain contains four initial states crossed with two measurement-error
vertices. Every call checks the returned policy against all eight rows using
the plant equations and safety limits independently of the controller
evaluator.

Configure and build it from a clean checkout:

```sh
cmake -S . -B build/ext04-affine-synthesis \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCSL_BUILD_EXT04_AFFINE_SYNTHESIS_REPORT=ON \
  -DCSL_ENABLE_HIGHS=OFF -DCSL_ENABLE_QHULL=OFF
python3 scripts/reports/ext04/capture_environment.py before \
  > build/ext04-affine-synthesis/environment-before.json
cmake --build build/ext04-affine-synthesis --config Release \
  --target csl_ext04_affine_synthesis_report --parallel 2
ctest --test-dir build/ext04-affine-synthesis -C Release \
  -R '^ext04_affine_synthesis_report_smoke$' --output-on-failure
build/ext04-affine-synthesis/csl_ext04_affine_synthesis_report smoke \
  > build/ext04-affine-synthesis/smoke.txt
build/ext04-affine-synthesis/csl_ext04_affine_synthesis_report measure \
  > build/ext04-affine-synthesis/trials.jsonl
python3 scripts/reports/ext04/capture_environment.py after \
  --before build/ext04-affine-synthesis/environment-before.json \
  > build/ext04-affine-synthesis/environment.json
python3 scripts/reports/ext04/affine_synthesis_report.py \
  --trials build/ext04-affine-synthesis/trials.jsonl \
  --smoke build/ext04-affine-synthesis/smoke.txt \
  --build-log build/ext04-affine-synthesis/build.log \
  --environment build/ext04-affine-synthesis/environment.json \
  --driver benchmarks/reporting/ext04/affine_synthesis_driver.cpp \
  --source-commit "$(git rev-parse HEAD)" \
  --collected-utc "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --out "reports/algorithm-results/ext04-affine-synthesis-$(git rev-parse --short=16 HEAD)"
```

The `measure` command records one excluded warmup and seven 100-call batches.
The phase-one LP workspace and immutable fixture are reused. The timed scope
includes generated-LP construction/solve, full-joint policy replay and literal
plant/safety checks; process startup, fixture creation, serialization and
rendering are excluded. One provider and one analytic fixture support no
comparative performance claim.

The environment helper records the toolchain, processor, configured providers,
and load averages immediately before and after the run. Keep the before capture
with the raw run directory; the report bundles the final environment record.

The saved-data renderer validates every generator outcome and creates the
two-dimensional state-plane figure, records, CSV, HTML and offline archive. A
published bundle must be collected from a clean Release build of a committed
source revision, then staged and verified through the report publication
workflow. The result remains numerical, one-stage, feasibility-only evidence;
solver infeasibility is inconclusive.
