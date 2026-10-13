# T-S01 result bundle

Source commit: `fe5095ce27ab4872cb31df32fab6f3b1b073f4f6`. This is a correctness and analytic-result record, not a performance measurement.

Rebuild the native sidecars into a fresh scratch directory and validate the committed report and site with:

```powershell
python reports/algorithm-results/tooling/ts01/build_bundle.py --out-dir build/ts01-rebuilt
python reports/algorithm-results/tooling/ts01/report.py --check reports/algorithm-results/syn07-ts01-20261013-fe5095ce27ab/records.json
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json --check --out build/ts01-report-site
```

See `index.html` for the full assumptions, exact relation, membership examples and assurance limits. `raw-events.jsonl` and `trials.csv` are deterministic membership-result projections.
