# MPC-11 five alternating NI1 timing repetitions

Comparative performance is inconclusive. These are descriptive costs for two
configured workflows with different model/policy restrictions, on one shared
Linux host. No native solver limiter profile or solver-parity ranking is
established. Actual repeated executions are retained rather than inferred from
prior pilot timings.

One separate warmup and five measured repetitions completed for each arm on
both scenarios. All 18 outer capture units completed without process failures.
Measured NMPC covers 350 updates; warmup adds 70. Affine capture covers the
two model QPs plus the analytic joint-QP fixture on each repetition. Both
arms retain actual nonlinear execution and independent CSL RK4 replay at both
contract tolerances. The NI1 configuration is explicit. Original objectives,
physical violations and replay sensitivity remain in each bound case record;
a numerical local NLP solution is not global nonlinear optimality or safety.

All times below are seconds, median [minimum, maximum] across five measured
repetitions. Warmup and fresh saved-data checks are excluded. These scopes are
nested/different and must not be summed into an invented common solver time.

| Configured arm/case | Configuration or controller setup | Optimization | CVODES execution/integration |
| --- | ---: | ---: | ---: |
| affine / syn-nl-lv-01 | 0.00192723 [0.0010704, 0.00218207] | 0.00610652 [0.00350762, 0.00691281] | 0.0193671 [0.0192983, 0.0228097] |
| affine / syn-nl-fuel-01 | 0.0100917 [0.0048671, 0.0162511] | 0.00597651 [0.00584685, 0.0138483] | 0.0312871 [0.0298993, 0.0332048] |
| nmpc / syn-nl-lv-01 | 5.31512 [5.18718, 6.16782] | 0.22253 [0.216248, 0.251399] | 0.0234572 [0.022933, 0.0264426] |
| nmpc / syn-nl-fuel-01 | 10.4013 [9.99507, 11.9147] | 0.368571 [0.359689, 0.43119] | 0.0380145 [0.0376156, 0.0412569] |

Affine setup is the native joint-QP setup; separate Python configuration
construction and complete process costs are in the JSON summary. NMPC setup
and solve are sums over its 30 LV or 40 fuel receding updates. Affine CVODES
includes integrator setup, while NMPC's execution sum covers held calls only;
its integrator construction remains in the process envelope. The JSON also
retains independent RK4 integration and startup-inclusive replay clocks for
both tolerances. The ranges alone exclude a precise timing ratio claim.

The separate instrumented fuel worker completed 40 holds, with the same
controls, physical trajectory, objective and selected numerical NLP fields as
measured repetition 0. Its cProfile shows repeated controller construction,
do-mpc NLP preparation and CasADi structured indexing as follow-up targets.
Instrumentation substantially inflated runtime and changed clock accounting;
its clocks are not benchmark samples. No native profiler was installed. CPU,
RSS, host load, raw pstats and human-readable profile remain in the archive.
Its 300-second wall timeout was enforced; no separate profile CPU/address-space
limit was applied. Measured algorithm workers retain their original limits.

Capture source is clean `68515dcb8e7d80a76914a81e08524648f6b57e79`.
Later measured child manifests also record the clean test-only commit
`39bf4f27`; their scientific source bytes are identical. The original source
snapshot, later saved-data checker, dependency/provider hashes, prior Release
build recipes and actual binary identities are bound separately. Native
binaries were reused and no package installation or native build occurred.
Every warmup and measured native stream/process receipt is retained. A
completed capture rerun preserved every file byte; source-snapshot mutation
with a renewed local inventory is rejected by the checker.

Verify outer SHA256SUMS, extract `capture.zip` into a new directory, then verify
its inner SHA256SUMS. With the locked optional MPC-11 environment and this
reviewed source checkout:

```sh
python benchmarks/reporting/mpc11/check_timing.py \
  --bundle <EXTRACT>/capture --source-snapshot <EXTRACT>/source-68515dcb \
  --output <NEW_SUMMARY_JSON>
```

The summary binds every consumed capture input and current reviewing tool.
A new checker run records a fresh offline checker duration; the measured
algorithm clocks remain saved values. Inspect TIMING.md for the rerunnable
capture command, resume semantics, clock scopes and POSIX restrictions.
No API/dependency/install/package/publication workflow change or release is
needed. Independent review and any later publication remain separate; this
archive does not close #607.
