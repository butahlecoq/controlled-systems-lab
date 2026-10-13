# Measurement interpretation and limits

This record measures one fixed GEO-05 implementation on four deliberately small analytic fixtures. It is a descriptive baseline only: there is no comparator, speedup or regression verdict, application-scale result, or scalability claim. Seven measured trials per fixture and one excluded warmup per fixture all passed their literal numeric-sample checks and reported work. Those checks do not establish exact set equality, completeness, validated arithmetic, or relation support; H/predecessor support remains Unestablished.

## Timing scopes

- `preparation_ns` includes fixture construction and public provider/request preparation. For H predecessor cases this includes provider registration and construction of the nominal predecessor, including joint rows; it is not a projection-kernel-only timing.
- `workspace_ns` is available only for V projection (seven observations). The public predecessor `run()` creates its workspace internally, so its workspace duration is unavailable and that cost remains within `run_ns`.
- `run_ns` measures the public execution path. For predecessor cases it includes internal workspace creation, projection, and H materialization, including Fourier–Motzkin elimination where selected.
- `verification_ns` measures independent literal sample or generator checks and the handle/representation access they use. These are sample checks, not a set certificate.
- `end_to_end_ns` begins before fixture construction and ends after the scenario runner returns. It includes preparation, execution, checks, and destruction of local fixtures, results, providers, and workspaces; exception paths also include stack unwinding. It excludes process startup, JSON serialization, persistence, and rendering. This scope is not directly comparable with LP/convex end-to-end timings that stop before owner destruction.

## Observed end-to-end timings

Seven measured attempts per fixture; median and observed range in microseconds:

| Scenario | Median | Min–max |
|---|---:|---:|
| `singular_a` | 20.3 | 19.5–26.6 |
| `unreachable_equality_target` | 18.4 | 17.3–20.8 |
| `integrator_predecessor` | 23.3 | 21.0–29.4 |
| `v_projection_preserves_ray` | 7.2 | 6.6–9.5 |

These values describe this build and fixture scale. At this size, fixed API, fixture-construction, access, timer, and scheduling costs may be material relative to numerical work. Profiling was not collected, so no bottleneck attribution is made. The H provider's per-call `max_rows=128` is experimental headroom for these fixtures, not a demonstrated capacity or global threshold. The integrator's six-row Fourier–Motzkin peak is an analytic expectation; the public API does not expose a runtime intermediate-row counter.

The host snapshot recorded Windows 11, 6 physical cores and 12 logical processors; total CPU utilization samples were 0%, 0%, 0%, 3%, and 0%. No deliberate concurrent benchmark workload was started, while the desktop, browser, and terminal remained open. These observations do not establish an isolated or representative production environment.
