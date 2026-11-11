# First common checker attempt: captured error, raw streams unavailable

The first common replay checker attempt used the report-validation Python 3.14 environment. It failed before returning a checker result because that environment has no SciPy. The first attempt's stdout/stderr files were overwritten during the successful retry, so the original raw streams and exact process return code are no longer available. The error below is transcribed from the captured tool response; it is not a raw logfile.

Command:

```text
/home/butahlecoq/.local/share/codex/tmp/report-validation-venv-20261104/bin/python3.14 /home/butahlecoq/.local/share/codex/worktrees/closed-loop-pilot-945-20261111/benchmarks/reporting/closed_loop/check_episode.py --input reports/closed-loop-native-feedback/attempts/lv-stage0-full-replanning-20261111/full-replay-common-check-input.json --output reports/closed-loop-native-feedback/attempts/lv-stage0-full-replanning-20261111/full-replay-common-check.json
```

Captured exception:

```text
ModuleNotFoundError: No module named 'scipy'
```

The successful common and tight retries used the qualified controller Python environment. Their outputs are in `full-replay-common-check.json` and `full-replay-tight-check.json`; the raw successful replay streams are retained separately.
