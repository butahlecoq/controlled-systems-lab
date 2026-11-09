# MPC-11 nonlinear execution correctness pilot

`capture.zip` preserves nonlinear execution of the two accepted affine control
histories from source `b3978a98`. The new execution/replay source is
`0092081b4d94b533c8811245c7309e50a434de9f`; saved checker revision is
`2dc16170c9df4cd8ba022b2752f6d788934e7ca7`. No affine optimization was rerun.
The affine source model/program/native result subset and verified physical
witness are retained for both cases.

The `accepted` directory contains all eight completed correctness executions:
CVODES and independent CSL adaptive RK4 at nominal and tighter tolerances for
both canonical synthetic cases. Each has raw stdout/stderr, process outcome,
request, scaled and physical states, original controls, timing and numerical
settings. Inner SHA256SUMS binds every archived payload. The outer checksum
binds the ZIP. `summary.json` repeats checked comparisons for reading.

The separate `diagnostic-report-restarts` directory retains the earlier pilot
that restarted CVODES at every report point. Its greater accumulated restart
error motivated integration once per original hold with intermediate output.
This diagnostic source was dirty; its manifest identifies source file hashes,
but it is not a clean-source reproducibility capture. It is retained as a
superseded attempt, not mixed with accepted results. The controls never changed.

Extract into an empty directory and check the outer and inner SHA256SUMS.
From the repository in the locked optional environment run:

```sh
python benchmarks/reporting/mpc11/check_nonlinear_saved.py --bundle <EXTRACTED>/accepted
CSL_MPC11_NONLINEAR_BUNDLE=<EXTRACTED>/accepted \
  CSL_MPC11_REPLAY_BRIDGE=<BUILD_DIR>/csl_mpc11_nonlinear_replay \
  python -m unittest tests.reporting.test_mpc11_nonlinear
```

See [execution instructions and limits](../../NONLINEAR.md) for rebuilding and
rerunning into a new output directory. The build receipt records the direct
C++20 consumer compilation; it compiles the existing CSL replay implementation,
without a copied or alternative RK algorithm. Build/source snapshots contain
no local absolute paths. The optional CMake target links `CSL::simulation`.

All observed physical constraint violations at the declared report grid are
zero. The LV and fuel nonlinear objectives differ from affine predictions.
Integrator and tolerance differences are reported, not certified error bounds.
RK4 nominal/tight rows are identical because short reporting steps already meet
both local tolerances. This does not imply zero numerical error. There is no
performance comparison, nonlinear global guarantee, robustness, continuous-time
safety, reachable-set figure, or NMPC result. Issue #607 remains open.

Delivery: optional example/report consumer only. No core public API, required
runtime dependency, package installation or release change is needed. Figures,
NMPC and final publication remain later reviewed steps.
