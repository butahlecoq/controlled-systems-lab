# GEO-02 affine-sum numerical report harness

This tooling measures four tiny deterministic analytic fixtures through the public `csl.geometry.affine-sum` implementation:

1. Scalar interval affine image: `[-1, 1]` under `x -> -2x`, giving `[-2, 2]`.
2. Rectangular projection of the unit box: `(x,y) -> x+y`, giving `[0,2]`.
3. Singular map of the unit box: `(x,y) -> (x+y, 2x+2y)`, giving the segment from `(0,0)` to `(2,4)`.
4. Minkowski sum `[-1,1] + [2,3] = [1,4]`.

The C++ report-only target is `csl_geo02_affine_sum_report`. Example Release configuration and build:

```powershell
cmake -S . -B build-geo02 -DCMAKE_BUILD_TYPE=Release -DCSL_BUILD_GEO02_REPORT=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build-geo02 --config Release --target csl_geo02_affine_sum_report --parallel 4
```

The target links the public `CSL::affine_sum`, `CSL::hull`, `CSL::highs_lp`, `CSL::qhull_conversion`, and `CSL::phase_one` targets. `--smoke` runs one non-accepted functional repetition. It does not create or imply accepted benchmark data.

Do not collect accepted timings until the measured algorithm source commit and the report harness commit have both been independently reviewed and fixed. After review, supply the exact SHA values, actual build provenance, and short operator notes:

```powershell
python reports/algorithm-results/tooling/geo02/collect.py `
  --exe build-geo02/Release/csl_geo02_affine_sum_report.exe `
  --source-commit <fixed-algorithm-sha> --harness-commit <reviewed-harness-sha> `
  --build-provenance build-provenance.txt --concurrent-work concurrent-work.txt `
  --profile-evidence profile-evidence.txt --reviewed --out reports/algorithm-results/geo02-<new-id>
python reports/algorithm-results/tooling/geo02/render.py --collection reports/algorithm-results/geo02-<new-id> --out build/geo02-report
```

Use fresh output paths. The collector requires at least seven measured repetitions and one warmup. The output includes raw driver CSV and JSONL records, the hashed canonical payload, per-phase summary CSV, environment and build notes, explicit failure/status files, and the deterministic offline bundle ZIP. `manifest.json` hashes every bundle file except itself.

The reports use IEEE binary64 arithmetic, small analytic point/support oracles, and descriptive wall-clock measurements only. They do not establish exact or validated geometry, competitor performance, speedups, application-scale behavior, or scalability. The GEO-02 reducer currently validates candidate outputs but retains the full candidate cloud rather than applying deletions. Per-trial CPU, native-thread observations, peak memory, internal LP timings, and OS limiter profiling are not available in this harness.
