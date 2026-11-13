# Reproduce a new native tracking capture

The supervisor requires a configured build directory and an installed CSL prefix. The installed prefix must have a sibling `SHA256SUMS` inventory. Inventory rows may use either prefix-relative paths or the absolute paths emitted by `sha256sum`; every listed file is verified before capture. Keep captures in a new output parent to preserve previous attempts.

```sh
cmake -S examples -B build/native-tracking \
  -DCSL_DIR=/path/to/csl-prefix/lib/cmake/CSL \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/native-tracking --target native_model_tracking native_discrete_models quadcopter_mpc -j1
python -B scripts/reports/native_model_tracking_first_pass.py \
  --build build/native-tracking \
  --sdk-snapshot /path/to/csl-prefix \
  --output-parent reports/algorithm-results/native-model-tracking-first-pass-v1
```

Add `--component-qualification /path/to/component-receipt.json` only when that receipt's named installed archive exists in the supplied prefix and its bytes match the recorded SHA-256. Without it, the capture records no component qualification. `--cmake /path/to/cmake` is optional when the executable is discoverable from the CMake cache or `PATH`. Set `TMPDIR` to a filesystem with enough space before the command if needed.

The fixed attempt policy is 60 seconds per authored case, 120 seconds for literal source21, and one thread for numerical libraries. All 35 are attempted; failures and timeouts remain in the capture. The source21 task is literal. Other 34 task profiles are authored nominal quadratic educational tracking profiles, with fixed three-stage receding horizon. No performance comparison or physical nonlinear stability claim is made.

After capture, independently check one explicit capture path:

```sh
python -B scripts/reports/verify_native_model_tracking_first_pass.py \
  reports/algorithm-results/native-model-tracking-first-pass-v1/capture-YYYYMMDDTHHMMSSZ
```

The checker rejects altered model identities/statuses and verifies all attempt stdout/stderr digests before evaluating completed trajectories. It writes a new sibling checks directory rather than changing the capture.
