# SYN-06 original-data verifier report

Fixed verifier source: `edf2b200209f4312b0d00a522a7a0b2e26a96d65`. Collector source: `5008509d004245db58975c173b4334c223036dfe`.

This saved report times two literal witnesses of a two-stage scalar integrator. The original terminal objective is linear `x[2]`, so its value is 1. One witness passes numerical checks; the other deliberately violates a control bound and transition. Neither establishes optimal-family completeness or validated proof.

`records.json` and `raw-events.jsonl` contain the accepted measurements. `pilot.json` and `profile.json` are separate, non-report observations. Run `python scripts/reports/stage_syn06.py --source reports/algorithm-results/syn06-verifier-20261012-edf2b200` to regenerate the catalogue entry from saved files.
