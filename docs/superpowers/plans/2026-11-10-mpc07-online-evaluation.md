# MPC07 bounded online policy evaluation

Claim: initial Python binary64 causal-policy evaluation costs on the same saved
2D physical models, not optimization/MPC-replanning latency, a speed ranking,
a hard-real-time bound, or new robust/global mathematical capability. Existing
exactly checked policies and all historical archives remain unchanged.

Namespace: benchmarks/reporting/mpc07/online/{controller,capture,check,figures}.py
and tests/reporting/test_mpc07_online.py. No shared publication edits.

Select measured repetition0 from each of the24 fixed-unit and12 joint-unit
profiles, authenticating the four original/corrected evidence folders using the
existing strict source/process/exact policy checks. Store the selected complete
rational policies, source-record hashes and original inventories separately.
Use horizons2/4/8; additive delta0 or uncertain-A delta=±1/64, w=±1.
Two deterministic physical traces per profile: positive and alternating signs.
Each has one excluded warmup and five measured episodes, reversed profile/trace
order on alternate repetitions. Derive inventory from selected profiles.

Types: immutable CompiledPolicy (binary64 v/M or diagonal-filter/H coefficients)
and stateful CausalController. observe(state) reconstructs only the previous
transition's residual from observed state, previous observed state and its own
past control. action() consumes only stored past residuals/innovations. Neither
method receives plant disturbance/model uncertainty. Capture calls plant.step
with the action only after action() returns. Preparation, residual update,
action query, complete episode and process scopes use integer nanoseconds;
record clock resolution, CPU/RSS/load and POSIX admission limits.

An independent Fraction reader replays original physical dynamics and the
rational causal policy, verifies the selected policy's original exact robust
certificate, and compares every binary64 observation/action/residual/innovation
to its exact counterpart with recorded absolute/relative tolerance. Bound/tie
proofs are source evidence, never inferred from the two traces. Preserve failed
processes/episodes and never report them as completed latency samples. Bind
actual clean Git commit/source/input bytes before capture and check snapshots
against that commit. No optimizer/native/build/install work is performed.

Tests cover unseen-disturbance independence, delayed reconstruction, two-state
normalization, action use by the plant, mutation rejection and full inventory.
A separate excluded diagnostic profile can identify interpreter work; no tuning
or winner claim. Native online evaluation costs are not claimed. Render saved
N8 joint four-class phase/time/control traces with shared Matplotlib3.11.2,
physical labels, initial/final markers and explicit zero-cost q=0 explanation.
Commit the measurement tool and inputs before measuring; recheck the frozen
capture, preserve all raw/failure artifacts and request independent review.
