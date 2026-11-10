# MPC06 offline construction cost supplement

This is a new canonical exact offline build, not a retrospective timing of the old180 native QPs. Prescribed K is copied, never optimized. Construction derives F, the exact nilpotent two-generator Z, its H certificate, state/input supports and nominal terminal{0}. These returned bounds feed the existing scripts.reports.mpc06_online.model.problem, with whole coefficients and native input bytes equal to three actual saved first-polytope QP requests. No solver or old feedback trajectory is rerun.

One excluded warmup plus five actual fresh constructions, a separately profiled arm, and1000 raw empty-counter controls per arm are retained. Construction includes Fraction conversion and artifact formation. Independent checking includes exact RPI vertex images/supports/terminal proof and the existing nominal-QP consumer/input-byte comparisons. Artifact JSON serialization is separately timed; JSON work inside the independent checker is part of that checker, not this serialization span. Episode includes these phases plus bookkeeping; worker wall additionally includes imports/input load/startup/stdout/polling. The environment/source/Git/input ledgers, wait4 CPU/RSS and POSIX CPU/address-space/wall limits stay distinct. No native heap cap, intrinsic-call timing, speed ranking or full MPC latency claim.

Run from the repository root with Python3.11+ and Git, no extra packages:

```
python -B -m scripts.reports.mpc06_offline.study --output <NEW_CAPTURE>
python -B -m scripts.reports.mpc06_offline.check --capture <CAPTURE> --output <NEW_RECEIPT>
```

Capture requires Linux POSIX resource/wait4 and clean committed source. Checking needs authentic source objects and the immutable original native record, never self hashes alone. Failed/spawn/resource/partial outcomes remain retained and inconclusive; no substitution by cached successful receipts. Publication is a separate optional extension; current-main review/CI/live delivery remain required. No public API, required dependency, native build/solver installation or standalone library release.
