# MPC-06 online propagated-anchor study

This study extends the immutable nilpotent-tube pilot with an actual public
CSL convex-port nominal QP. It is a bounded synthetic fixture, not a generic MPC
controller. The existing plant, disturbance, fixed gain and invariant plot are
specified in `benchmarks/scenarios/mpc06-nilpotent-tube-v1.json`.

The actual controller uses `u=v+K(x-z)`, exact full-state measurement, `K=(-1,-2)`
and an internally propagated nominal anchor. It initializes `z=x`, then retains
`z_next=A z+B v`; disturbed measured states never reset that anchor. At every
step it solves an N=3 nominal problem with stage cost `z^T z+v²` and `z3=0`.
For `z=(p,q)`, terminal elimination gives
`v=(a,-p-3q-2a,p+2q+a)`. Every tightened constraint is affine in `a`; its feasible
set is an exact rational interval, and the positive quadratic coefficient gives
an independently checkable unique nominal optimum.

The reference optimizes the **same** deterministic nominal sequence and fixed
ancillary feedback with exact stage-specific disturbance supports. At global
stage zero the error is zero, stage one has `E W`, and subsequent stages have
exactly `Z`. Reoptimization does not restart this global error clock. The tube
version instead uses an invariant error set throughout, so its feasible interval
must lie inside the matched reference interval. The saved finite initial grid
reports feasibility loss and nominal objective gaps. It is not a complete
feedback-winning set, fixed-open-loop minimax solution or general causal optimum.

The actual three-step cost `sum(x_t^T x_t+u_t²)+x3^T x3` is reported separately.
The retained anchor and reoptimized nominal sequence are deterministic, so the
actual state/input is affine in the entire disturbance vector. The convex
quadratic cost attains a continuous-box maximum at a vertex; all eight vertices
are checked with rational arithmetic using the actual stored native controls.
This argument would fail for a measured-state-reset policy; that policy refuses.
No unsafe path is clipped. The nominal terminal set `{0}` is invariant under
`v=0`; each admitted error set is independently RPI and respects original state
and input constraints. Shifting a feasible plan and appending zero preserves the
terminal condition. Three executed receding steps need not themselves end at
nominal zero; the final feasible plan retains its terminal continuation.

## Representations and independent evidence

The exact polytope, two-generator zonotope and parallelotope are equivalent
representations of `|e1|<=1/8, |e1+e2|<=1/8`. In coordinates `s=e1,t=e1+e2`,
error dynamics are `(s_next,t_next)=(t,w)`. Scaling the square by 3/2 gives a
sound outer invariant zonotope. The coordinate box enclosing Z is outer but
fails RPI and is rejected with an exact successor witness.

The native driver calls existing APP-04 with orientation `(s,t)`. Its emitted
stored radii/center are checked independently against every exact Z vertex.
That outer circle also fails RPI; a rational witness inside the actual emitted
ellipse maps outside it. This demonstrates why approximation enclosure evidence
alone cannot justify recursive tube tightening. A separate proposed outer
ellipsoid `s²/(1/2)²+t²/(1/4)²<=1` passes the exact RPI bound
`(1/4)²/(1/2)²+(1/8)²/(1/4)²=1/2`. Rational outward support pads are checked by
squared inequalities. It is explicitly distinct from the rejected APP-04 member;
no new generic approximation producer is added or attributed to APP-04.
Neither volume nor numerical solver status establishes these claims.

## Build and checks

```sh
cmake -S benchmarks/reporting/mpc06_online -B build/mpc06-online \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release \
  -DCSL_DEPENDENCY_PROBES=OFF -DCSL_ENABLE_QHULL=OFF
cmake --build build/mpc06-online --target csl_mpc06_online -j2
python3 -m unittest discover -s tests/reporting -p test_mpc06_online.py
python3 scripts/reports/mpc06_online/study.py \
  --driver build/mpc06-online/csl_mpc06_online --repetitions 5 \
  --output /absolute/new/capture-directory
python3 scripts/reports/mpc06_online/check.py /absolute/new/capture-directory \
  --receipt-output /absolute/new/evidence/verification-v2.json
python3 scripts/reports/mpc06_online/render.py /absolute/new/capture-directory \
  --receipt /absolute/new/evidence/verification-v2.json \
  --output /absolute/new/rendered-directory
```

The native runner consumes one line per scalar QP:
`quadratic linear offset lower upper`, with objective
`quadratic*a²+linear*a+offset`. It uses existing public `ConvexProgram` construction,
registry admission and exclusive workspace execution, retains the actual program
identity and evaluates original objective through CSL. Each QP has a fresh
workspace and one requested backend thread. A process is reused per repetition;
method order alternates. Reported native prepare/setup/solve, exact construction,
independent checks and process roundtrip intervals are separate. Initial offline
APP-04 cost and finite-grid reference construction are separate from online
costs. No timing ranking or source-level limiter claim is made.

## Optional dependency, platform and delivery plan

HiGHS 1.11.0 is the existing optional numerical QP integration, under MIT and its
pinned bundled notices. APP-04 uses existing core approximation code. This adds
no required solver, parser or plotting dependency; acados, OSQP and HPIPM are not
installed. Native QP evidence remains numerical; its original objective and safe
first control are independently checked. No external controller-equivalence,
hard real-time, prompt in-call QP cancellation, or native heap/RSS cap is claimed.

The standalone CMake target uses the public headers/targets and standard C++20.
Validate Release GCC/Clang and MSVC, sanitizer builds and installed-client linking
before claiming those platforms. The local capture records the actually exercised
compiler/platform; other platform and publication gates remain explicit until
hosted evidence exists. Project binary-distribution licensing remains the owner's
separate gate. This research tool has no public API/install-layout change and
needs no standalone library release. Never overwrite either previous MPC-06
report or its versioned URL; a new captured report requires independent review,
immutable staging, route inventory and live publication verification.

The prior required 2D invariant/tightening figure is already published at
https://butahlecoq.github.io/controlled-systems-lab/mpc06-tube-405a8ac4eb2bea7ebec8/index.html .
It remains authoritative for that immutable pilot. New rendering reads saved
online records only; issue #602 stays open until its full remaining evidence
and publication gates pass.

The timing verdict is inconclusive: this capture checks phase accounting and executed work, not an adoption or performance choice. No source-level limiter profile has been established. It excludes no warmup calls; the first native call in each reused process may initialize backend state, and every QP still creates a fresh workspace. Host load and active compiler counts are recorded.

## Versioned checked-source boundary

The original `mpc06-online-anchor-v1` archive remains immutable. Its first
verification receipt is historical and does not authorize current rendering.
The shared `evidence.py` boundary verifies the complete prior checksum inventory,
base scenario and capture-source snapshots, then parses each completed native
response stream. APP-04 output and every ordered QP response must exactly equal
the structured process/step records, including program identity and timing.
Native preparation/setup/solve sums must also fit their observed response
interval. Checksums alone do not prove this extraction correspondence.

The version-2 receipt binds every source-archive file and the exact checker,
model, study, boundary helper and renderer source bytes. Rendering validates
those bindings before reading quantitative values, requires a new output
directory and preserves the original archive under `checked-inputs/`. A changed
raw response, result/timing, capture source, receipt or reviewing script requires
a fresh successful check; rendering cannot renew a manifest around stale checked
evidence. New manifests describe generated outputs only after this boundary
passes. The final reading layer retains `review-tools/` for offline rechecking.
These fixes require no new native optimization or mathematical experiment.
