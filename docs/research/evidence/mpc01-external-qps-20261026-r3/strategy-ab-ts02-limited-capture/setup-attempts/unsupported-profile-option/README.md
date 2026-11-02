# Retained T-S02 setup failure

This command never reached a Strategy A/B trial. The selected pre-existing executable did not support `--measure-profile` and exited with status 2 after printing usage. No event file was created, so this is retained as a failed harness setup attempt, not counted among comparison attempts or as a solver outcome.

The process was inside the requested 2 GiB, no-swap cgroup scope. The exact command, supervisor source, stdout, stderr, and observed resource profile are retained here. The subsequent T-S02 capture uses a different retained Release executable whose source supports the requested profile.
