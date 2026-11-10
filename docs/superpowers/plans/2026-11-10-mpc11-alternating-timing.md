# MPC-11 alternating timing capture

Authorized scope: two existing synthetic NI1 scenarios, actual full-joint affine
QP with positive uniform objective multiplier 1000, and nominal shrinking-tail
NMPC. Reuse the locked optional environment and existing native bridges. These
policy/model restrictions differ; elapsed differences do not establish solver
parity, relative mathematical quality or a universally better controller.

Capture one separate warmup per arm, then five measured repetitions. Alternate
arm order A/B, B/A, A/B, B/A, A/B. Each affine arm includes the actual joint QP
and nonlinear CVODES execution plus independent native RK4 replay at both
existing tolerances. Each NMPC arm includes all 30/40 solves, held-control
CVODES execution and independent RK4 replay. Preserve all exceptions, process
outcomes, raw streams and incomplete trajectories. Use existing per-worker
300-second CPU/wall and 8GiB address-space limits, one requested library thread,
and one arm at a time. Save outer process CPU, maximum RSS and host load.

Implement a resumable capture tool with exclusive ownership, immutable per-unit
receipts and input/source/binary bindings. Never overwrite partial attempts;
a resumed interrupted unit gets a new attempt directory. Completed units,
including failures, are not silently retried. Check current saved transcripts
and associated programs with existing independent checkers outside timed arms.
Keep configuration/native setup, optimization, execution, replay and checker
clocks distinct, and report medians/ranges with counts/failures per case.

The decision is whether this bounded configured workload has stable descriptive
cost observations worth a follow-up. A ranking requires both a demonstrated
limiter and a difference larger than run spread. Existing profiler availability
and concurrent host load are recorded. A separate Python profile may locate
controller construction/native calls, but cannot be promoted to a native QP
limiter profile. Without sufficient limiter evidence the comparative verdict
is inconclusive. No package installation, native build, deployment or issue
closure is part of this unit. Optional scripts use existing dependencies, so no
library release is needed.
