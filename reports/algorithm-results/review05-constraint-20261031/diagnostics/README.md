# Excluded diagnostic attempts

`invalid-json-preflight/` retains the first 42-process capture. Its 8-row
fixture was malformed JSON, so the input loader rejected those 14 calls before
solver execution and the independent checker refused the bundle. None of those
rows contribute to the reported measurements. The corrected fixture was then
captured afresh in the parent report bundle; all 42 corrected attempts passed
its exact checker.

`profile-diagnostic.stderr` records that Linux `perf` was not installed on the
capture host. No hardware-counter or source-attributed profile was obtained;
this report makes no limiter or winner claim.
