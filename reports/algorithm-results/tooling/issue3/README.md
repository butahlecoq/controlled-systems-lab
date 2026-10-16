# Issue #3 saved finite-action minimax report

This report uses algorithm source `994f3ee4310b4087d289e2eb02adbdb9dfd97827`
and independently reviewed harness `2f915110ba42515fdc448a0c226dc1290b80f82d`.
The accepted collection's raw JSONL SHA-256 is
`b4632ce76510aa4f2bb136baa193bc78da66506336a90d048cd8495c2d7926de`.
The later report commit changes neither measured code identity. Rendering and
staging read saved bytes only; they never run `--measure`.

The native source bundle is
`reports/algorithm-results/issue3-finite-catalogue-b4632ce76510aa4f/`.
Its `evidence/accepted-001/` directory retains the exact 64 raw rows, eight
smoke rows, stdout/stderr and process status for configure, fresh Release build,
smoke, smoke checker and accepted capture, the sanitized build log and CMake
File API graph, preflight and collection status, exact executable and fixture
source. There was one accepted measured attempt. Separate functional regression
and preflight directories in the harness worktree were not measurement attempts.

Run from the repository root with Python 3.11 or newer:

```sh
python scripts/reports/issue3/render_saved.py --bundle reports/algorithm-results/issue3-finite-catalogue-b4632ce76510aa4f --check
python -m unittest tests.reporting.test_issue3_saved_report -v
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json --check --out build/issue3-report-site
```

The validator pins the raw, binary and fixture hashes; checks distinct source
and harness trees, Release/C++20/NDEBUG build graph, process success and empty
stderr; verifies all ordered fixture rounds, work counts, canonical input
hashes and literal scientific outcomes; and reconstructs the record, CSV, SVG
and HTML byte for byte. The schema-3 site stage verifies the committed offline
ZIP against the generated publication and its catalogue SHA-256. The immutable
public route binds every native file digest and the LF-normalized SHA-256 of
the publisher module; changing publication code creates a new route.

Each figure/table duration is a **batch** interval. L19 uses 10,000 checked
calls, each small status fixture uses 5,000, and B08 uses one whole 625-plan,
256-corner-per-plan catalogue. The interval includes fixture construction,
public calls, literal checks and result construction, and excludes process
startup, serialization, persistence, plotting and rendering. One warmup per
fixture was excluded; seven measured batches per fixture passed. Caches may be
warm. Other worktrees had active local builds/tests during collection, so host
contention may affect durations. There is no comparator or source-mapped
limiter: the performance conclusion is **inconclusive**, with no speedup or
per-call latency inference.

Scientific scope is limited to the supplied binary64 fixtures and numerical
assurance. The displayed rounded B08 model is a fixed open-loop linear
catalogue; the historical 67.12, unrounded/nonlinear plant, feedback optimum
and validated arithmetic enclosure remain outside this evidence. The report
does not close issue #3 until independent saved-result review, main-only Pages
deployment and verification of the actual immutable URL are complete.
