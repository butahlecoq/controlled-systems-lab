# MPC10 post-capture source-authentication qualification

The original sibling `comparison-525871ea` directory, archive, raw records, figures and verification receipt remain unchanged. This separate receipt rechecks the same 26 fixtures and submitted SCIP formulations without optimization. Its mathematical reports and complete input map equal the original receipt. Capture source remains `525871ea658c3147f30c96e9cb7824b91ed410f2`; corrected checking source is `7373bd97192f83a3b0e03d6a073256ca230f3217`. These revisions describe different operations and are not substituted for one another.

The corrected boundary requires the complete capture source inventory copied by the recorded run module, checks every file against its recorded full Git revision, requires the complete checker inventory, and authenticates checker bytes against its separate full Git revision. Empty, subset, unknown, self-rehashed and option-like revision inputs are rejected. Original historical receipts lack the new checker revision field and remain historical evidence; they must be rechecked before use by the corrected renderer.

For reproduction, use a full Git checkout containing both revisions and the existing qualified PySCIPOpt6.3.0/SCIP10.0.2 optional environment. Extract the original capture.zip into scratch, checkout the corrected checking revision, and run from repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 <SCIP_PYTHON> -m benchmarks.reporting.mpc10.check --bundle <SCRATCH>/capture --output <NEW_CHECK_JSON>
```

The checker reconstructs models but never calls optimize. The source ZIP is an auditable snapshot, not a standalone substitute for Git-object authentication or a solver distribution. No native binary, dependency install, algorithm timing, library release, or deployment is supplied. Frozen original figures remain bound to their original historical receipt; any newly generated figure requires this corrected receipt and its matching checker source. Keep #606 open for independent review, CI and live checked delivery.
