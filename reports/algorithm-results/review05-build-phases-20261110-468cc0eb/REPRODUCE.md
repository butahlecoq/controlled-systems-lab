# Reproduce actual build-phase observations

The clean algorithm source is `468cc0eb2d3d8e3f7f3ade632db8a2e88cf2cd85`.
All original raw attempts, clocks, receipts and source files are retained.
A later name-only MSVC shadow-warning fix does not change these captured
numerical semantics; its independent review is recorded on PRs #894/#898.

Use `source/BUILD-PHASES.md` to build the full repository at the captured commit
with the private probe hook. The optional observer does not change the public
builder signature or mathematical program. A new capture must use a clean
checkout and a new output directory. Historical absolute paths in receipts and
CMakeCache describe the capture host; pass your newly built binary explicitly.

To verify the existing bytes, run `sha256sum -c SHA256SUMS`. From an extracted
copy, `python3 source/check_family_query.py .` reruns the exact family/query
checks, then import `source/run_build_phases.py` and call `summarize(Path('.'))`
to validate actual interval order, nesting, sparse/program sizes and regenerate
the phase reading layer. These operations update derived checker-duration
fields; retain regenerated output separately and verify the original manifest
first. No native solve is needed to check or render saved data.

There are six measured repetitions plus an excluded warmup per fixture and
collector mode, across scalar T=2/4/8 zero-optimum and constant-zero cases.
Eighty-four attempts verify; two deliberate row-materialization stops remain
inconclusive mathematically while retaining already completed build phases.
The phase medians are independent summaries and need not add to the median
parent. The residual is calculated per attempt and includes admission, map and
observer overhead; it is not silently attributed to sparse assembly or snapshot
construction. These are initial descriptive observations, not a performance
ranking or a unique-limiter claim. Isolated verifier timing, native-clock
overhead and issue-wide audit remain separate #95 work.
