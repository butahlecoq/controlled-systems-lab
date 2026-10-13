# Measurement interpretation and limits

This saved record covers one fixed implementation and four deliberately small analytic fixtures. It is not a before/after comparison and supports no speedup or regression verdict. The 28 measured attempts (seven per fixture) and four excluded warmups all passed their numerical literal-sample checks and reported work. These checks do not establish exact set equality, completeness, validated arithmetic, or relation support; H/predecessor support remains Unestablished.

## What each timing includes

- `preparation_ns` includes authored fixture construction and the public provider/request preparation path. For H predecessor cases this includes provider registration and preparation of the nominal predecessor, including joint-row construction. It is not a projection-kernel-only timing.
- `workspace_ns` is available only for the V projection provider workspace; it has seven observations (one per measured V trial). The public predecessor `run()` creates its workspace internally, so its 21 workspace values are null and those costs remain inside predecessor `run_ns`.
- `run_ns` includes the public execution path. For predecessor cases it contains internal workspace creation, projection and H materialization, including Fourier–Motzkin elimination where selected. For V it is the provider operation run after separately timed workspace creation.
- `verification_ns` includes independent literal sample or generator checks and the handle/representation access those checks use. These checks intentionally establish only selected samples, not a set certificate.
- `end_to_end_ns` starts immediately before fixture construction and is stamped after the scenario runner returns. It includes preparation, execution, independent checks, and destruction of the runner's local fixtures, results, providers, and workspaces. A thrown operation also includes stack unwinding before failure is recorded. It excludes process startup, JSON serialization, persistence, and rendering. This GEO-05 scope is not directly comparable with LP/convex end-to-end spans that stop before owner destruction.

The fixtures contain only a few rows/generators. At this scale fixed API, fixture-construction, handle-access and timer/scheduling costs can be material relative to numerical work; these timings should be read as bounded end-to-end API costs, not algorithm throughput or capacity evidence. A separate Windows Performance Recorder CPU profile was attempted but could not enable system profiling (error `0xc5585011`), so machine-level CPU-versus-overhead attribution is unavailable. The pre-run host snapshot was 1% total CPU on a 6-core/12-logical-processor Windows host; no intentional competing benchmark workload was started, while desktop processes remained open.

## Observed end-to-end distributions

Seven measured attempts per scenario, median and observed min–max in microseconds:

| Scenario | Median | Min–max |
|---|---:|---:|
| `singular_a` | 19.4 µs | 18.6–26.4 µs |
| `unreachable_equality_target` | 17.1 µs | 16.6–19.1 µs |
| `integrator_predecessor` | 22.6 µs | 21.6–25.9 µs |
| `v_projection_preserves_ray` | 7.6 µs | 6.7–8.8 µs |

These distributions describe this build and fixture scale only. They are not comparisons between algorithms or configurations.

The per-call H provider option `max_rows=128` is experimental headroom for these small cases, not demonstrated capacity or a global threshold. The integrator's six-row Fourier–Motzkin peak is an analytic expected count; the public API exposes no runtime intermediate-row counter.

## Validation context

The local full Release baseline for the fixed GEO-05 source passed 61/61 CTest cases (`ctest --test-dir build/geo05-full -C Release --output-on-failure`). The harness Python suite passed 18/18 on validator commit `20838c6f3db1040cd0c82bcc601bc282f40ded6f`. GitHub CI checks for PR #170 were still queued at collection/validation time; no accepted measurement depended on those queued jobs.
