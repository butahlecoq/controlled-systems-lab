# Paired registered synthesis T-S01 report

This report preserves one exact T-S01 paired experiment on the two-stage scalar integrator. It records one excluded A/B warmup and seven measured alternating pairs. Both strategies use the same resolved problem, family request, selector request, provider registrations, and requested resource policy.

The conclusion is **inconclusive; no winner is claimed**. The timing medians are descriptive for this tiny fixture. No separate limiter profile was performed, so the latency limiter is unknown. The report does not support a general performance ranking, speedup, application-scale, or scalability claim.

The event file is the exact binary JSONL sidecar. The original Windows stdout bytes and stderr bytes are retained. The collector wrapper exited 1 because it compared CRLF stdout with the LF JSONL sidecar byte-for-byte. Algorithm exit code was 0, and both streams match after CRLF-to-LF normalization. The failed wrapper attempt is explicitly retained in process and validation metadata.

The selector request parameters are copied from source commit `b7f1ac0a9800326c825b6d8e35a8f23656496682`, pinned by the measurement source file SHA-256 in `records.json`. Each event retains its actual family/objective identity and module provenance. The live complete-family proof payload is not serialized.

Rebuild and regeneration commands are in `commands.json`. Regenerating this bundle uses saved measurement outputs only; it does not rerun the algorithm. Live GitHub Pages publication remains pending review and main-branch deployment. This partial report does not close OBS-04/#83.
