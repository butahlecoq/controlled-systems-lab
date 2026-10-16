# APP-01 registered inner state-plan check

Clean fixed Release harness source: `22d406fd9ea92315ef2a4f6b5703eec74e710d47`. The original scalar model has initial state 2, transition x[1] = u[0], singleton control 3, terminal objective x[1], and analytic value 3. The valid witness returns numerical achievable value 3 only after original-problem verification. The altered witness with control 5 and state 3 fails original feasibility. A zero-vertex V inner set fails membership. Both retain no value. Supplied binary64 membership is not a validated real-model inclusion proof. No optimal-family or completeness claim.

`records.json` and `raw-events.jsonl` retain seven accepted Release observations per fixture. `pilot.json` and `profile.json` are separate unreported observations. The limiter is not established. Build graph/logs use SOURCE_ROOT and BUILD_ROOT placeholders. Regenerate from saved records with `stage_app01.py --source`; staging requires a typed catalogue.
