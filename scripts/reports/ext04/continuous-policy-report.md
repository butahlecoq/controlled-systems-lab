# EXT-04 continuous policy report

The saved bundle
`reports/algorithm-results/ext04-continuous-27d4ad2e12958609/` measures the
public `evaluate_continuous_policy` evaluator at source commit
`27d4ad2e12958609bca976786b7568adc6fe74fa`. It uses a one-step, two-state
system with four supplied initial-state generators, a partial observation and
one affine policy. The driver checks each generator's full initial and
terminal state, action, safety margin, and numerical feasibility status on
every call.

This is a single-adapter observation. It does not compare policy evaluators,
search for a policy, establish a universal initial/disturbance guarantee, or
claim validated arithmetic. It does not measure a realistic end-to-end control
workflow. Host load was not controlled, and there is no separate limiter
profile; the timing should not be used to select an implementation or claim a
speedup.

From a clean checkout of the source commit, regenerate the Release build and
measurement with:

```sh
cmake -S . -B build/ext04-continuous-report \
  -DCMAKE_BUILD_TYPE=Release -DCSL_ENABLE_HIGHS=ON \
  -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_EXT04_CONTINUOUS_REPORT=ON \
  -DBUILD_TESTING=OFF
cmake --build build/ext04-continuous-report --config Release \
  --target csl_ext04_continuous_policy_report --parallel 4
build/ext04-continuous-report/csl_ext04_continuous_policy_report smoke
build/ext04-continuous-report/csl_ext04_continuous_policy_report measure \
  > build/ext04-continuous-report/trials.jsonl
```

Render only from the retained raw rows and build log. Use a new output
directory and the original collection timestamp to reproduce the bundle byte
for byte:

```sh
python3 scripts/reports/ext04/continuous_report.py \
  --trials build/ext04-continuous-report/trials.jsonl \
  --build-log build/ext04-continuous-report/build.log \
  --example docs/examples/continuous-policy-2d.svg \
  --out reports/algorithm-results/<report-id> \
  --source-commit <frozen-source-commit> \
  --collected-utc <original-collection-time> \
  --load-observation '<recorded host-load snapshot>'
```

The renderer rejects incomplete batches, non-passing statuses, wrong fixture
identity, or batches shorter than 20 ms. The bundle retains the raw JSONL rows,
derived CSV and records, the exact C++ driver and saved-data renderer, a
standalone HTML report and figure, the sanitized Release build log, a SHA-256
manifest, and an offline ZIP. The publication adapter validates the raw rows
and summary and regenerates the report byte for byte before staging. Publication
to GitHub Pages remains pending review and deployment. Generate and stage its
immutable publication route with:

```sh
python scripts/reports/stage_ext04_continuous.py \
  --source reports/algorithm-results/ext04-continuous-ebcf879d07ee9157 \
  > reports/algorithm-results/ext04-continuous-publications.json
python scripts/reports/stage_ext04_continuous.py \
  --catalog reports/algorithm-results/ext04-continuous-publications.json \
  --site build/report-site
python scripts/reports/visual_examples.py \
  --catalog reports/algorithm-results/catalog.json --site build/report-site
```
