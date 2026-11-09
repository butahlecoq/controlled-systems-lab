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
