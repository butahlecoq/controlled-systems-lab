# REVIEW-05 current integrated ownership stress evidence

Nine selected suites pass against source `7243ed353cbfdde3c897572c58cc6d6a244194ea`, including the new Strategy B build phases. This local integration contains the reviewed exact-family/selector and assembly work; its source identity does not claim those branches had merged to main when tested. The older `review05-integrated-tsan-cb6a42f6-20261110` bundle remains unchanged.

The archive preserves current incremental-build and CTest logs, full native test output, initial configure/build context, CMake cache, build rules, source hashes, test-binary hashes, dynamic-link receipts and toolchain/host metadata. Every retained test binary links libtsan. The reported launch uses `CSL_HIGHS_INTERNAL_CLOCKS=1` and `TSAN_OPTIONS=halt_on_error=1`. No launch-time environment dump exists; the receipt states this limit. Native clock prefixes corroborate enabled capture. Mixed native output is not a per-call timing dataset, and test durations are not algorithm benchmarks.

The [independent ownership inventory](ownership-inventory.md) extends the earlier audit over 85 changed product paths. No actionable ownership finding remained. Passing these selected runs proves neither whole-library race freedom nor correctness of every numerical algorithm. Bounded noninterruptible calls, declaration-only native widths and unsupported hard heap limits remain explicit.

Verify the outer SHA256SUMS, extract `capture.zip` into an empty directory, and verify its inner SHA256SUMS. `receipt.json` records the source, settings and observed outcomes. Initial configure/build logs predate the final integration; `current-incremental-build.log` and `current-ctest.log` record this update. Absolute paths describe the capture host.

Reproduce from the recorded source using the configuration in the cache: RelWithDebInfo, C/C++ `-fsanitize=thread -fno-omit-frame-pointer`, executable link flag `-fsanitize=thread`, HiGHS and Qhull enabled. Build the nine targets listed in the receipt. Run CTest with the reported launch environment and `--output-on-failure --no-tests=error`, selecting exactly those names. Retain a fresh source/build/environment receipt for any rerun.

This evidence package changes no public API, algorithm, dependency or release. It supplies no new numerical algorithm requiring a 2D example. Consolidated independent review, integration and required publication remain separate #95 delivery work; this bundle does not close the issue.
