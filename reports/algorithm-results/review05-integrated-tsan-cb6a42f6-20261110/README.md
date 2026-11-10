# REVIEW-05 integrated ownership stress evidence

Source `cb6a42f645af940b8529c616e403ff9cd7c9f791` combines main
`83b01b7f`, clock capture `cd63548a`, and exact-family/selector `ea7d89b5`
on a local integration branch. It is not a claim that these changes had merged
to main at capture time. The later MSVC identifier-only fix and later assembly
phase instrumentation are outside this capture.

Eight selected suites passed under GCC 16.2.1 ThreadSanitizer, with HiGHS and
Qhull enabled and `CSL_HIGHS_INTERNAL_CLOCKS=1` fixed in the environment.
They exercise execution, timing, batch isolation, LP/convex workspaces,
concurrent conversion and witness selection. No race was reported in those
executions. This does not prove whole-library race freedom or cover every
provider, schedule, native runtime or allocation failure.

The ZIP retains configure/build/CTest logs, mixed native output, CMake settings,
source-discovery lists and a limited allocation-failure probe. The 983 native
clock prefixes show the diagnostic path executed; mixed CTest output is not a
validated per-call timing dataset. Test durations are not performance evidence.
The source keyword scan is an inventory aid, not the final ownership audit.

Reproduce from the recorded source in a dedicated build directory:

```sh
cmake -S . -B <BUILD_DIR> -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DCMAKE_CXX_FLAGS='-fsanitize=thread -fno-omit-frame-pointer' \
  -DCMAKE_C_FLAGS='-fsanitize=thread -fno-omit-frame-pointer' \
  -DCMAKE_EXE_LINKER_FLAGS=-fsanitize=thread \
  -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DCSL_DEPENDENCY_PROBES=OFF
cmake --build <BUILD_DIR> --parallel 2 --target execution_tests \
  batch_runner_tests timing_collector_tests highs_lp_tests highs_convex_tests \
  hv_conversion_tests quickhull_2d_lp_test witness_selector_tests
CSL_HIGHS_INTERNAL_CLOCKS=1 TSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir <BUILD_DIR> --output-on-failure --no-tests=error \
  -R '^(execution_tests|batch_runner_tests|timing_collector_tests|highs_lp_tests|highs_convex_tests|hv_conversion_tests|quickhull_2d_lp_test|witness_selector_tests)$'
```

Check the outer SHA256SUMS, extract the ZIP into an empty directory, then check
its inner SHA256SUMS. Source paths in raw logs describe the capture host.
Final source integration, ownership review and remaining phase/resource
assessment still gate #95 closure. This diagnostic report changes no public API
or dependency and requires no library release or 2D algorithm illustration.
