# T-S01 result bundle

Source commit: `28f305387f66caf8f72f057e16a39050cc5dbdba`. Timings are exploratory single-strategy observations, not a performance verdict or speedup comparison.

Rebuild the native sidecars into a fresh scratch directory and validate the committed report and site with:

```powershell
python reports/algorithm-results/tooling/ts01/build_bundle.py --measurement-dir build/ts01-measure-001 --out-dir build/ts01-rebuilt
python reports/algorithm-results/tooling/ts01/report.py --check reports/algorithm-results/syn07-ts01-20261013-28f305387f66/records.json
python -m unittest tests.reporting.test_ts01_report -v
python scripts/reports/site.py --catalog reports/algorithm-results/catalog.json --check --out build/ts01-report-site
```

See `index.html` for the full assumptions, exact relation, membership examples, timing scope and assurance limits. `raw-events.jsonl` and `trials.csv` project exact membership results; `measurement-events.jsonl`, `measurement.json` and `timings.csv` retain raw trial timings and provenance.
