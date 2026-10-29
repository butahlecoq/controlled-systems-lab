# EXT-04 joint H-domain policy report

This driver measures `evaluate_h_continuous_policy` on one scalar system with a
caller-authored correlated H-domain. It checks six exact support maxima, every
returned dual witness residual, the domain correlation and a separate primal
counterexample smoke case. The timing contains one domain feasibility solve,
six dual support solves and literal evidence checks per call.

Build the Release driver with the pinned HiGHS LP provider:

```sh
cmake -S . -B build/ext04-h-policy-report -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCSL_ENABLE_HIGHS=ON \
  -DCSL_ENABLE_QHULL=OFF -DBUILD_TESTING=OFF \
  -DCSL_BUILD_EXT04_H_POLICY_REPORT=ON
cmake --build build/ext04-h-policy-report \
  --target csl_ext04_h_policy_report --parallel 4
build/ext04-h-policy-report/csl_ext04_h_policy_report smoke
build/ext04-h-policy-report/csl_ext04_h_policy_report measure
```

The measurement emits one JSONL row for an excluded 100-call warmup and seven
measured batches of 100 calls. Save stdout as `trials.jsonl`; collect the host and
compiler details in `environment.json`, and retain the clean Release build log.
The quantitative figure uses the pinned report environment and is rendered
outside the measured solver interval:

```sh
python3 -m venv /tmp/csl-report-venv
/tmp/csl-report-venv/bin/pip install -r scripts/reports/requirements.txt
/tmp/csl-report-venv/bin/python scripts/reports/ext04/h_policy_report.py \
  --trials /path/to/trials.jsonl \
  --build-log /path/to/release-build-log.txt \
  --environment /path/to/environment.json \
  --out reports/algorithm-results/ext04-h-policy-0c0a95116ce4642b \
  --source-commit 0c0a95116ce4642bd560d8f285b244e104aaa266 \
  --collected-utc '2026-10-29 14:20:52 UTC'
```

Rendering uses Matplotlib 3.11.2, the shared `csl-report-quantitative-v1`
numeric tick/grid policy, and the shared SVG validator. The saved renderer and
its helper sources are included so the report can be regenerated offline.
The report records floating-point LP evidence as numerical, and makes no
validated-arithmetic, synthesis, universal disturbance or comparative
performance claim. The build currently requires HiGHS; the controller API
itself keeps the workspace injected by the caller.
