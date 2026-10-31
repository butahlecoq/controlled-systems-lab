# REVIEW-05 ownership and ThreadSanitizer evidence

Source commit: `fd7641e6f106202eae4b5ebdf9ecc874ade0f63e` (clean committed source)
Capture date: 2026-10-31

This bundle records a focused dynamic race check for execution, batch, timing,
LP/convex HiGHS, H/V conversion, and Qhull paths, plus a source ownership
inventory. It supplements the earlier executor/batch audit; it is not proof of
race freedom for untested paths or arbitrary concurrent use.

## Build

- Host: Linux 7.2.8-9-omarchy x86_64; AMD Ryzen 5 3550H, 8 logical CPUs;
  8,108,216,320 bytes RAM.
- Compiler: GCC 16.2.1 (`/usr/bin/c++`); Ninja 1.13.2; CMake 3.31.6.
- Configuration: `RelWithDebInfo`, `BUILD_TESTING=ON`, HiGHS and Qhull enabled,
  dependency probes disabled. C and C++ flags include
  `-fsanitize=thread -fno-omit-frame-pointer`; linker flags include
  `-fsanitize=thread`.
- The first build attempt exhausted the 3.8 GiB `/tmp` tmpfs while GCC wrote
  temporary assembly. The successful retry set `TMPDIR` to a task-specific
  directory on `/home`; this did not change source or compiler flags.
- CMake's pinned HiGHS and Qhull dependencies were built into the same
  instrumented build. The Qhull-enabled configuration and native adapter build
  logs are retained separately.

## Run

Command: `TSAN_OPTIONS=halt_on_error=1 ctest --output-on-failure -R '^(execution_tests|batch_runner_tests|timing_collector_tests|highs_lp_tests|highs_convex_tests|hv_conversion_tests|quickhull_2d_lp_test)$'`

All 7 selected tests passed in 1.58 seconds, with no ThreadSanitizer report:

| Test | Result |
| --- | --- |
| `execution_tests` | Passed |
| `batch_runner_tests` | Passed |
| `timing_collector_tests` | Passed |
| `highs_lp_tests` | Passed |
| `highs_convex_tests` | Passed |
| `hv_conversion_tests` | Passed |
| `quickhull_2d_lp_test` | Passed |

The LP suite exercises two separate HiGHS workspaces concurrently behind a
barrier. The Qhull conversion suite includes concurrent Qhull calls. The tests
exercise selected paths only; ThreadSanitizer is dynamic and cannot establish
absence of races in paths they do not run.

## Files

- `ownership-inventory.md`: source-level state and lifetime audit.
- `build-configuration.txt`: relevant CSL CMake cache selections, compiler,
  host, build path, and sanitizer flags.
- `highs-dependency-configure.log`: configure output for the pinned HiGHS
  dependency.
- `tsan-build.log`: complete core build transcript, including failed `/tmp`
  attempt and successful retry.
- `tsan-native-adapters-build.log`: HiGHS/Qhull adapter build transcript.
- `tsan-ctest.log`: exact seven-test CTest result.
- `SHA256SUMS`: hashes for all bundle files except this hash list.
