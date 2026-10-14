# SYN-03 Strategy A T-S02 report reproduction

This report measures exact solver source `272fb9a51c40dedeb20dfcb1ea11dfc6b694edd7` from PR #239 through the public `StrategyRegistry` and production Strategy A provider registrations. It is a separate source and result identity from Strategy B T-S02 issue #238.

The fixture is the two-step scalar integrator with `x0=0`, `A=B=1`, independent controls in `[0,1]`, universal state constraints, no external channels, observations or temporal constraints, and `LinearTerminal` coefficient zero with offset 3. One excluded warmup precedes seven recorded observations. Every event retains completion and verifier status, canonical five-coordinate H-relation checks, objective bounds `[3,3]`, all four control-box corners, and distinct histories sharing terminal state 1.

Run from a clean harness checkout with a new output path and the pinned dependency source cache:

```powershell
python reports/algorithm-results/tooling/syn03_ts02/collect.py `
  --cmake $cmakeExe `
  --dependency-cache $dependencyRoot `
  --build-root $measurementRoot `
  --out $collectionRoot
python reports/algorithm-results/tooling/syn03_ts02/build_bundle.py `
  --collection $collectionRoot `
  --out reports/algorithm-results/syn03-strategy-a-ts02-20261014-272fb9a5
python reports/algorithm-results/tooling/syn03_ts02/report.py --check `
  reports/algorithm-results/syn03-strategy-a-ts02-20261014-272fb9a5/records.json
python tests/reporting/test_syn03_ts02_report.py
python -m unittest discover -s tests/reporting -p 'test_*.py'
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json `
  --check --out $siteOutput
```

The collector builds a clean Release executable from the pinned source worktree. It retains exact event JSONL, derived CSV, a separate diagnostic process/profile, host/compiler/build/input provenance, and names unavailable submodule call counters and timings. The public bundle replaces private root paths with stable placeholders and retains original evidence hashes separately. It makes no comparison or speedup claim; a source-mapped latency limiter is not established. Strategy A includes forward reachability, terminal optimization and history recovery before the exact relation verifier accepts the full feasible relation.

The schema-3 candidate and offline ZIP are staged locally. Main-only Pages deployment and live immutable URL verification remain pending. This report does not close SYN-03 #66.
