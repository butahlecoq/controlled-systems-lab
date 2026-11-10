# Joint block-diagonal-filter specialization

Follow-up to the immutable0e821c2a fixed-filter capture. Independent derivation
from Chen et al. arXiv2203.11375v3, section4.1 diagonal-filter cases, change of
variables(24), affine response identity(26), uncertainty constraints(36) and
row tightenings(37)-(39). No author source is adopted. The paper's full filter
also has subdiagonal blocks; setting them zero is an explicit restriction, not
the full author implementation or its published example.

Use the same physical two-state uncertain-A model and controls as the first
unit: p_next=p+q+u/2, q_next=(1+delta)q+u+w; |delta|<=1/64, |w|<=1, full-state
observations, x0=0,u0=0, |p|<=64,|q|<=16, |u|<=1. The physical p forcing is
zero. To keep the two-state filter invertible as required by the response
change of variables, use a positive position-filter floor rho=1/1024. It
adds only conservative virtual position forcing; actual reconstructed position
forcing remains exactly zero. This regularization is declared and bounded.

The optimized diagonal filter has entries s[t,p]>=rho and s[t,q]>=1. Let zeta_t
be a two-component unit box, x_t=sum(j<t)R[t,j]zeta_j, and
u_t=sum(j<t)H[t,j]zeta_j; there are no feedforward offsets in this homogeneous
SLS specialization. The affine equalities are
R[t+1,j]=A R[t,j]+B H[t,j]+diag(s[t])*1[j=t].
Causality fixes future columns to zero. At each transition, reconstruct
zeta_t=diag(s[t])^-1*(x_next-A*x-B*u). Only past zeta enters each action;
unknown delta and physical w are never assumed separately observed.

Specializing the paper's vertex uncertainty condition to delta=+/-epsilon and
zero filter subdiagonals gives exactly
s[t,q]>=1+epsilon*sum(j<t,k)|R[t,q,j,k]|.
For position, the sufficient condition is s[t,p]>=0, strengthened by rho>0.
State/control box counterparts are exact unit-box row1-norm bounds. Thus all
filter, response and absolute-value auxiliary constraints are linear. Their
joint optimization retains dependence of the uncertainty enclosure on the
controller response, unlike the previous uniform fixed5/4 envelope. Induction
constructs |zeta_t|<=1 for every admitted physical history, so the returned
virtual worst terminal q^2 is a physical worst-cost upper bound.

This authored terminal-only norm objective uses zero state/control stage
weights; finite-horizon feasibility and the explicit bound proof apply, while
strict-positive-weight stability/recursive-feasibility theorems are not invoked.
It is not the paper's default nominal quadratic objective. Nominal/full-horizon
MPC, unrestricted uncertainB, full nondiagonal filters and generic capabilities
remain outside this profile.

Independent physical lower bounds for this particular loose-constraint toy:
with all w=+1,delta=+epsilon and u>=-1 after u0=0, qT>=(1+epsilon)^(T-1).
The feasible canonical virtual law H[t,t-1,q]=-1, s[0,q]=1,
s[t,q]=1+epsilon*(1+epsilon)^(t-1), H position columns zero, attains that bound.
Every q support is (1+epsilon)^(t-1), and the stated state bounds hold up toT8.
Therefore equality to this lower bound is an independent exact tiny-profile
certificate, not a general consequence of minimizing an SLS upper bound.
For M0, the symmetric optimum is sum(k=0..T-1)(1+epsilon)^k; prescribed gain
-alpha*q has support sum(k=0..T-1)(1-alpha+epsilon)^k, alpha=1/16.
All values are squared only after the nonnegative LP terminal-absolute optimum.


Native response coordinates are numerical auxiliaries. Reconstruct filter and
control coefficients as new rationals, then derive all response coordinates
from the exact affine recurrence. The maximum change from native response
coordinates must be <=1e-10 and is recorded separately; raw arrays are retained.
This does not assert exact equality of binary64 state variables. The candidate
filter/control and all robust supports are still checked exactly, and any
nonzero upper/lower gap remains explicit. An actual T8 prescribed-gain pilot
had a3.5e-18 position-response artifact; its original rejected diagnostic is
retained and the saved-native regression distinguishes repair from a real
coordinate mutation. This changes checking/reconstruction, not the native solve.


The fixed-plan comparison fixes H=0 and has no affine offsets in this homogeneous
specialization. This zero-input plan is symmetry-optimal among fixed actual
plans for the stated centered boxes: for each fixed uncertainty history, the
terminal velocity is affine in the plan, so its squared worst cost is convex;
negating plan and physical disturbances preserves cost and feasibility. Thus
the feasible average zero plan is optimal. The gain comparison is the declared
pure prescribed full-state gain, not an unmeasured optimized nominal trajectory.

The stored response omits the zero initial-state column. It extends to the
paper's full block identity by adding Sigma[0,0]=I and choosing the corresponding
initial-state response consistently with the observer controller. The physical
initial state is fixed at zero, so those added columns do not change this OCP.
Positive diagonal filter blocks make the past state/disturbance map invertible;
the observer implementation is therefore a causal LTV state-history feedback.
It reconstructs lumped eta, not the unobserved physical w or delta separately.

Timing scope is batch policy synthesis on a fixed initial state, with Python
assembly, native public-port setup/run and exact checking separate. It is not
an executed receding-horizon MPC update-latency claim. The paper's terminal and
shrinking-horizon/backup conditions, full nondiagonal filter, uncertainB and
additional dimensions remain explicit future profiles, not hidden in these
measurements. No library API, required dependency or standalone release changes.


## Bound-field distinction

virtual_profile_oracle_squared is the optimum of the declared policy/filter LP
class. physical_unrestricted_lower_squared is the independent causal physical
lower bound, always (65/64)^(2(T-1)) for this toy. Their gaps are separate. The
fixed-filter optimum9/4 atT2 is not a physical lower bound. An initial0075400d
capture used the misleading physical_lower_oracle_squared field name for the
class/virtual oracle; its native inputs/results are retained with that metadata
erratum, and it is not the corrected reading layer. No numeric values or LPs
changed with this field correction.


## Per-policy attainment reporting

Exact feasibility of a repaired policy does not by itself prove attainment.
The renderer computes each joint policy's physical upper-minus-lower gap using
exact rationals. Zero-gap policies can inherit the explicit toy lower-bound
certificate. A positive gap remains a valid robust worst-cost upper bound and
is retained as such, without a minimax-attainment statement. The report records
the minimum/maximum exact gaps and the range of policy bounds across repetitions.
A saved T2 native-witness mutation exercises this distinction without native
execution. The original04369201 policies have zero gaps; their frozen artifacts
remain unchanged while the post-capture renderer handles both cases honestly.
