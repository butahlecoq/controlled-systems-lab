# GEO-02 affine-sum numerical report harness

This tooling measures four tiny deterministic analytic fixtures through the public `csl.geometry.affine-sum` implementation:

1. Scalar interval affine image: `[-1, 1]` under `x -> -2x`, giving `[-2, 2]`.
2. Rectangular projection of the unit box: `(x,y) -> x+y`, giving `[0,2]`.
3. Singular map of the unit box: `(x,y) -> (x+y, 2x+2y)`, giving the segment from `(0,0)` to `(2,4)`.
4. Minkowski sum `[-1,1] + [2,3] = [1,4]`.

The C++ report-only target is `csl_geo02_affine_sum_report`. Accepted collection requires the reviewed harness commit checked out, no tracked changes, and an actual configured Release target. Query the CMake File API before configuring:

```powershell
$apiQuery = 'build-geo02/.cmake/api/v1/query'
New-Item -ItemType Directory -Force $apiQuery | Out-Null
Set-Content -NoNewline "$apiQuery/codemodel-v2" ''
Set-Content -NoNewline "$apiQuery/toolchains-v1" ''
cmake -S . -B build-geo02 -G 'Visual Studio 17 2022' -A x64 -DCSL_BUILD_GEO02_REPORT=ON
cmake --build build-geo02 --config Release --target csl_geo02_affine_sum_report --parallel 4
```

The target links the public `CSL::affine_sum`, `CSL::hull`, `CSL::highs_lp`, `CSL::qhull_conversion`, and `CSL::phase_one` targets. `--smoke` runs one non-accepted functional repetition. It does not create or imply accepted benchmark data.

Timing scopes are pinned in the saved record. `setup_ns` measures provider/registry construction, operation selection and preparation, and workspace creation after fixture construction. `operation_ns` measures the prepared workspace call. `oracle_ns` measures literal point and support checks, excluding output extraction and serialization. `total_ns` is end-to-end driver time from fixture construction through result extraction, serialization, and oracle checks; it includes the named phases plus intervening harness work. The report validates that total covers all named phases and describes their scopes in the HTML.

Do not collect accepted timings until the algorithm source and report harness commits have both been independently reviewed and fixed. The collector verifies the checked-out harness SHA, a clean tracked tree, the source-to-harness allowlist, the exact CMake merge-resolution/report-target delta, CMake File API Release/C++20/NDEBUG configuration, dependency graph and executable identity. It performs a final verbose Release build and saves its provenance. Warmup output and oracle outcomes are retained; any failed/missing warmup blocks a complete report. Supply nonempty operator notes:

```powershell
python reports/algorithm-results/tooling/geo02/collect.py `
  --exe build-geo02/Release/csl_geo02_affine_sum_report.exe `
  --build-dir build-geo02 `
  --source-commit <fixed-algorithm-sha> --harness-commit <reviewed-harness-sha> `
  --concurrent-work concurrent-work.txt --profile-evidence profile-evidence.txt `
  --reviewed --out build-geo02/collection-001
python reports/algorithm-results/tooling/geo02/render.py --collection build-geo02/collection-001 --out build-geo02/report-bundle
```

Use fresh output paths. The collector requires at least seven measured repetitions and one warmup. The output includes raw driver CSV and JSONL records, the hashed canonical payload, per-phase summary CSV, environment and build notes, explicit failure/status files, and the deterministic offline bundle ZIP. `manifest.json` hashes every bundle file except itself.

The reports use IEEE binary64 arithmetic, small analytic point/support oracles, and descriptive wall-clock measurements only. They do not establish exact or validated geometry, competitor performance, speedups, application-scale behavior, or scalability. The GEO-02 reducer currently validates candidate outputs but retains the full candidate cloud rather than applying deletions. Per-trial CPU, native-thread observations, peak memory, internal LP timings, and OS limiter profiling are not available in this harness.
