# Verify or reproduce the saved publication

This bundle is a location-free rendering of committed capture, independent-check,
and figure inputs. Verifying it does not run a solver or repeat the 35 model
attempts. The exact historical producer for the captures is commit
`635ac5ba59d230e2b09062690adc943ea6451568`; the portable publication renderer
is separately pinned in `source-binding.json`. The renderer pin authenticates
the packaging code, not the earlier native run.

Use a full-history checkout because the bundle verifies both its historical
producer source and the portable renderer pin with `git show`:

```sh
git clone https://github.com/butahlecoq/controlled-systems-lab.git
cd controlled-systems-lab
```

Compare the working renderer with its published source pin, then regenerate the
location-free files in memory and compare every staged output, including the
versioned ZIP:

```sh
TOOL_COMMIT=$(python3 -c 'import json; print(json.load(open("reports/algorithm-results/native-model-tracking-first-pass-v1/source-binding.json"))["portable_renderer_commit"])')
git show "$TOOL_COMMIT:scripts/reports/stage_native_model_tracking_first_pass.py" > /tmp/stage-native-model-tracking-pinned.py
cmp /tmp/stage-native-model-tracking-pinned.py scripts/reports/stage_native_model_tracking_first_pass.py
python3 -B scripts/reports/stage_native_model_tracking_first_pass.py --check
```

The check needs only Python's standard library and the committed repository
inputs. `--check` is read-only. Its ZIP uses sorted member names and fixed file
metadata, and the committed publication lock authenticates the exact archive
bytes. `SHA256SUMS.json` inventories the bundle members other than itself and
the enclosing ZIP; `native-model-tracking-first-pass-v1.zip.sha256` authenticates
the ZIP.

## Make a new native capture

This creates new evidence; it does not reproduce the historical capture by
overwriting it. It requires a configured C++ toolchain and an installed CSL
prefix whose `lib/cmake/CSL` exports the native targets. Set `CSL_PREFIX` to
that installed prefix:

```sh
cmake -S examples -B build/native-tracking \
  -DCSL_DIR="$CSL_PREFIX/lib/cmake/CSL" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build/native-tracking --parallel 1 \
  --target native_model_tracking native_discrete_models quadcopter_mpc
python3 -B scripts/reports/native_model_tracking_first_pass.py \
  --build build/native-tracking \
  --sdk-snapshot "$CSL_PREFIX" \
  --output-parent reports/algorithm-results/native-model-tracking-first-pass-v1
```

The supervisor verifies the installed prefix's `SHA256SUMS` inventory and
creates a timestamped capture. All 35 records are attempted. Model21 follows
the literal source task; the other 34 use authored educational profiles. The
fixed attempt limits are 60 seconds per authored case and 120 seconds for
source21. Failures and timeouts stay in the new capture. To independently
verify one generated capture, pass its explicit path:

```sh
python3 -B scripts/reports/verify_native_model_tracking_first_pass.py \
  reports/algorithm-results/native-model-tracking-first-pass-v1/capture-YYYYMMDDTHHMMSSZ
```

The verifier writes a new sibling check directory and leaves the capture
unchanged. This workflow makes no performance-ranking or physical nonlinear
stability claim.
