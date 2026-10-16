# B08 displayed-data exact report harness

This is the report harness for the exact-rational research checker in [PR #329](https://github.com/butahlecoq/controlled-systems-lab/pull/329), source commit `78212b21d42ec3f136f0e1c72b2b0861d306792c`. It does not change that checker or its saved numerical record. The separate harness commit must pass independent review before an accepted timing run. This phase adds no catalogue entry or published URL.

## Scope

The finite B08 reference treats the printed L04 decimals as exact rationals. Its result is the exact squared worst-case value `112730080707/25000000` with three tied plans. The historical `67.12` is retained as a separate reported value. The original unrounded arrays, MATLAB generator, nonlinear trajectory, historical 37-second runtime and complete optimal-control family remain unresolved. Issue #6 stays open.

One trial launches a **fresh child CPython process** with `-B -O` and executes the fixed checker with `--verify-record`. The parent `perf_counter_ns` interval starts immediately before spawn and ends after process exit and stdout/stderr capture. It includes interpreter startup, exact enumeration of 625 plans and 256 disturbance-history corners per plan, literal checks and saved-record comparison. It excludes parent validation, persistence, HTML rendering and ZIP creation. The child is freshly started each time; operating-system caches may already be warm. One warmup is excluded, followed by at least seven measured trials. No comparator or speedup is claimed. Without a source-mapped limiter profile, performance interpretation is inconclusive.

The collector requires a clean harness commit descended from the fixed source commit and permits only the three reviewed harness paths in that delta. It compares the checker and reference bytes with their source-commit blobs and pinned SHA-256 digests. The command uses the current CPython executable, whose version, executable digest and optimization flags are recorded. Native Release/CMake flags do not apply to this Python checker. OS, processor, logical core count and a point-in-time host activity note are retained. Child CPU time, observed thread count, peak memory and internal phases are explicitly unavailable.

Each child attempt records exit status, timeout, wall-clock interval, exact stdout/stderr bytes as base64, and hashes of those bytes. Child launch or capture errors also become failed attempt rows. Raw JSONL is flushed after **every** attempt. Failed attempts are retained along with CSV and saved JSON and block HTML/ZIP publication. A successful collection produces a content-bound ID, standalone HTML, saved JSON, raw JSONL/CSV, file manifest and deterministic offline ZIP with fixed cross-platform entry metadata. The `check` command reconstructs summary and HTML from saved rows and verifies byte equality for CSV, JSONL, manifest and ZIP. Rendering and checking never rerun numerical work.

## Functional checks before independent harness review

From the repository root:

```powershell
python -B -O scripts/reports/b08_exact_report.py smoke
python -B -O -m unittest tests.reporting.test_b08_exact_report
python -B -O docs/research/tools/check_b08_displayed_exact.py --verify-record docs/research/evidence/b08-displayed-exact.json
```

Smoke output is functional evidence only; its elapsed time is discarded. No accepted report measurement should run before an independent review of the **exact harness commit**.

## Collection after review and host coordination

Create a point-in-time UTF-8 concurrent-work note outside the clean source tree. Use a new output directory outside the repository checkout. Ask the coordinator to defer other heavy local work for the short measurement window, then run:

```powershell
$harnessCommit = git rev-parse HEAD
python -B -O scripts/reports/b08_exact_report.py collect `
  --harness-commit $harnessCommit `
  --concurrent-work D:/work/PhD/b08-concurrent-work.txt `
  --repetitions 7 --timeout 60 `
  --out D:/work/PhD/b08-exact-collection
python -B -O scripts/reports/b08_exact_report.py check `
  --bundle D:/work/PhD/b08-exact-collection
```

The note paths and output directory are examples, not reserved destinations. Review the raw attempts, summary, environment, failures, HTML, ZIP, and source identity before committing any bundle. Publication requires a separate site adapter, schema-3 catalogue registration, deployed immutable Pages URL and live verification after GEO-06 and EXT-01 report integrations. No staged file path alone is a published URL. Raw artifacts and public page must preserve the printed-data reference scope and measured source commit.
