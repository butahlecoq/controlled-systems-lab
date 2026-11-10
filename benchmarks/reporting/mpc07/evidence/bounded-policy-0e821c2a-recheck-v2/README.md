# Bounded causal-policy intersection (experimental MPC-07)

This authored benchmark advances issue603; it is not an adoption or port of
unlicensed author code and adds no public CSL feedback capability. The primary
sources are Goulart/Kerrigan/Maciejowski (2006), DOI10.1016/j.automatica.2005.08.023,
and Chen et al. arXiv2203.11375v3 (2023-09-26). The latter's actual method jointly
optimizes a filter and state responses and optimizes a worst-cost upper bound;
this unit only implements a fixed-filter intersection. The author repository
ShaoruChen/Polytopic-SLSMPC is still at3f6873299ec5d0d2d87630a66486f723788390a4,
pushed2024-05-03, license metadata null (rechecked2026-11-10). Its MATLAB/YALMIP/
MPT3/MOSEK stack is not adopted. No source/paper text is redistributed. See the
existing docs/research/mpc07-source-audit.md for qualifications.

## Model, information and policy class

The state x=(p,q) has dimension2. Use p_next=p+q+u/2 and q_next=q+u+eta,
x0=(0,0), u0=0, T in{2,4,8}, |u|<=1, |p|<=64 and |q|<=16 at every step.
For known A/B, independent eta_t in[-1,1] arrives AFTER action u_t. Full states
are observed exactly after each transition. The controller reconstructs
eta_t=q_next-q-u from that transition; it never observes current/future eta.
The physical model must also satisfy the p transition; no estimator/noisy or
partial observation profile is admitted.

The causal ADF law is u_t=v_t+sum(j<t)M_tj*eta_j. M is strictly lower triangular.
The response formulation introduces xbar_t and R_tj, with xbar0=0 and R0j=0,
then enforces xbar_next=A*xbar+B*v and R_next,j=A*R_tj+B*M_tj+E*1[j=t],
where A=[[1,1],[0,1]], B=(1/2,1), E=(0,1). Future response columns are zero.
This is the finite-horizon response identity for a scalar forcing embedding E;
it is not the full model-uncertain SLS-MPC implementation. Eliminating these
response variables gives the same ADF feasible policy class. Nominal offsets
allow affine policies, and the initial state is fixed, rather than an uncertain
initial-state column. Fixed-plan M=0 and prescribed gain u=-alpha*q are explicit
restrictions: alpha=1 for the additive case and alpha=1/16 for the filtered case.
Different fixed gains across those profiles are declared, not paired as one
unchanged controller. No terminal invariant set or recursive feasibility claim.

## Robust constraints and objective

For any affine scalar a+b*eta over independent |eta_j|<=sigma, its exact maximum
absolute value is |a|+sigma*sum|b_j|. Every state/control box row uses this support,
with LP auxiliaries s>=+/-coefficient. The terminal epigraph minimizes t>=max|qT|.
The original toy objective is max qT^2=t^2, not a nominal surrogate; squaring is
monotone for t>=0 and is reported separately from the native LINEAR objective.
No sum-of-quadratics controller-study objective is silently substituted.

For fixed plans, symmetry gives t*=T*sigma. For arbitrary causal policies with
u0=0 and |u|<=1, the all-positive virtual disturbance forces
qT>=T*sigma-(T-1). The affine law u_t=-eta_(t-1)/sigma attains that bound for
sigma>=1. Its exact supports satisfy the loose stated state bounds. Thus ADF
and response optima are [T*sigma-(T-1)]^2 for THIS toy. For prescribed gain,
t*=sigma*sum(k=0..T-1)(1-alpha)^k. These elementary exact lower/upper bounds are
the independent literal oracle, not native dual certificates. They do not prove
unrestricted minimax optimality for other costs, bounds or disturbance models.

Native output remains binary64 numerical evidence. A separate reconstruction
uses Fraction(value).limit_denominator(2^32) to propose a NEW rational policy.
An independent exact recurrence rechecks every robust state/control support,
causal coefficient, policy-class restriction and original objective; response
coordinates are checked against that recurrence. A failed repair is retained as
unverified, never accepted by tolerance. Raw native numbers are unchanged.

## Fixed uncertain-A enclosure and limits

The separate physical profile changes q_next=(1+delta_t)*q+u+w_t,
|delta_t|<=1/64 and |w_t|<=1; B is known. Under |q|<=16 the lumped eta=delta*q+w
lies in[-5/4,5/4]. Induction is sound: q0 is in the bound, each admitted lumped
eta keeps the planned q in the bound, so the next physical lumped disturbance
is admitted. Eta is reconstructed from observed states without knowing delta
or w separately. Its independent box intentionally forgets their dependence.
The response LP therefore provides a robust feasible policy and an upper bound
on the true physical worst cost, not that problem's minimax value.

At T2, the original physical unrestricted causal optimum is (1+1/64)^2: w0=+/-1
and unseen delta1,w1 force at least that magnitude; u1=-w0 attains it. The
fixed-filter optimum instead returns u1=-4/5*eta0. Its physical worst cost is
(1+1/5+1/64)^2, below its virtual-box bound(3/2)^2 and above the physical optimum.
The exact8-vertex T2 check is justified by separate convex maxima in each
multiaffine uncertainty coordinate for this fixed affine policy. It is not
transferred to arbitrary replanning or larger model-uncertain policies.
Jointly optimized filters, uncertain B, dense uncertain A, higher-dimensional
uncertainty, richer objectives and general causal minimax remain residual603
criteria. The figure distinguishes the physical uncertainty strip, fixed filter
rectangle, exact virtual terminal parallelogram and physical vertex samples.

## Native source, timing and delivery

No new build is needed. Reuse the original Release public-CSL ConvexPort bridge
from affine-pilot-b3978a98, SHA256
266e1cda61b064b4603ff6499d76dc4db59106e4e673905f585c54caafa9c533.
Its existing schema is intentionally retained and its source/build provenance
remains b3978a98; this generator supplies zero Hessians, so HiGHS executes LPs.
The new policy/generator source identity is separate. Existing optional HiGHS
1.11.0 keeps its MIT/bundled-notice qualifications. No new core API, required
library dependency, installed package, binary redistribution or library release.
Figures use the existing optional Matplotlib report environment.

Capture requires clean committed source and a new output directory. A retained
warmup plus five alternating repetitions cover every profile/class/horizon;
every native/process/check outcome remains a row. One worker requests one
solver thread. POSIX per-process CPU/address-space limits and a process-group
wall stop are explicit; no aggregate cgroup cap is claimed. Linux wait4 records
direct-child peak RSS in KiB and CPU seconds. Python preparation, native setup (parse/program/registry), native
ConvexPort run (including adapter checks), whole process and independent checker
costs stay distinct. None is an isolated HiGHS-only solve/verifier measurement.
The separate Python profile diagnoses only authored preparation/checking. No
native limiter or tuning study is supplied: performance verdict INCONCLUSIVE.
Do not claim a winner, asymptotic runtime, MPC update latency or hard real-time.

```sh
python -m unittest tests.reporting.test_mpc07_policy
python benchmarks/reporting/mpc07/capture.py --bridge <REVIEWED_BINARY> \
  --output <NEW_CAPTURE> --repetitions 5
```

Root-owned publication wiring and independent source/math/results review remain
required. Local raw data/figures do not count as deployed publication or603closure.

## Frozen capture and portable checking

This first capture uses clean new-generator source0e821c2a and the separately
identified reused native bridge. The outer HTML only changes raw-download/README
links; offline.zip preserves the original complete report and its manifest,
including all144 native attempts (24warmups,120measured), two separate probes,
source snapshots, the old native build receipt/cache and CPU/RSS records.

Run `sha256sum -c SHA256SUMS` here, extract offline.zip into a fresh directory,
enter mpc07-report and run `sha256sum -c SHA256SUMS`. For independent saved-data
checking with Python standard library only, from that extracted directory:

```sh
python -B - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0,'<EXTRACT_CORRECTED_CHECKER>/post-capture-checker')
from report import checked_records,metrics
environment,records,policies,hashes=checked_records(Path('<EXTRACT_ORIGINAL>/mpc07-report/RAW'), repository=Path('<FULL_SOURCE_CHECKOUT>'))
print('Checked rows:',len(records))
print(metrics(records))
PY
```

The -B flag prevents Python from creating __pycache__ inside the immutable raw
source snapshot. This does not invoke the native binary or modify frozen records. For plotting,
use the pinned report environment and the recorded source checkout0e821c2a:
`python benchmarks/reporting/mpc07/report.py --capture <EXTRACT>/RAW --output <NEW>`.
Historical absolute command/cache paths are provenance, not portable commands.
The separate Python profile identifies authored rational-form construction as
its main measured Python work; it does not diagnose the native LP limiter.
No performance winner is inferred. The complete issue603 SLS joint-filter
criterion remains pending beyond this fixed-filter first unit.

Policy-size accounting: the common stored ADF coefficient vector has
T(T+1)/2 entries including fixed u0; free optimized ADF coefficients are
(T-1)+T(T-1)/2, namely2/9/35 atT2/4/8. M0 has1/3/7 free offsets, and the
prescribed-gain controller has no free policy parameters. The common baseline
LPs deliberately retain constrained coefficient variables and support auxiliaries;
their LP dimensions are not minimal implementations. The explicit response adds
2T+T(T+1) state-response variables:10/28/88. Actual optimized ADF LP sizes are
20/54/170 variables and39/99/291 rows; response sizes30/82/258 variables and
49/127/379 rows. These exact formulation counts are not measured asymptotic
runtime or evidence that an untuned baseline is slower.


## Post-capture provenance correction v2

The original reading layer, offline ZIP, raw captures, native inputs/results and
saved checks remain unchanged in bounded-policy-0e821c2a. This NEW v2 directory
adds post-capture-rechecks.json and post-capture-checker.zip from checker source
e04cb7add5a34fb56530fdf2d737fade9a238f32. No native algorithm was rerun. Both the original ZIP and
exploration ZIP are byte-identical to v1. Mandatory copied-source keys now
match their recorded Git commits; native bridge sources additionally match the
pinned b3978a98 commit/build receipt. Completed process receipts must have
return0, no timeout, valid integer durations and the recorded limits. Native
inclusive spans cannot exceed the supervised process duration.

For the command above, separately extract post-capture-checker.zip and use an
existing FULL_SOURCE_CHECKOUT containing commits0e821c2a and b3978a98. The archive
alone cannot authenticate a Git commit without its repository objects. This
saved-data recheck is offline once those objects are present and needs no native
binary or Matplotlib. -B prevents bytecode writes. Fifteen focused/inventory
regressions pass, including rehashed copied-source and timeout-receipt attacks.
Missing history or a provenance mismatch refuses the report; it never falls
back to the original weaker cached check.
