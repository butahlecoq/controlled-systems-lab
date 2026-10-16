# Issue #5: exact finite policy-class reference

This [research checker](tools/check_finite_policy_classes.py) independently evaluates the authored two-step counterexample in the [reviewed adaptive-policy proof audit](adaptive-policy-proof-audit.md#causal-game-value-and-strict-counterexample). It compares four **different** objects: an initial fixed-plan minimax value, first actions of optimal remaining fixed plans, the worst cost of one executed replanning selector over complete disturbance histories, and a globally optimal exact-state causal value. It is a finite mathematical reference, not a product solver, a new measurement, or a reproduction of a historical run. Run it and its [literal tests](tools/test_finite_policy_classes.py) with:

```text
python -B -O docs/research/tools/check_finite_policy_classes.py
python -B -O docs/research/tools/test_finite_policy_classes.py
```

## Source and information boundary

Registered L13 (original PDF SHA-256 `4556046bb893a9a7a8c7b8489673dc95315d8ea49bf37e787a59d897c8a7a70e`) pp.6–10, Eqs.(17)–(20), Algorithms 2–3 defines a remaining-horizon **fixed-plan** minimax solve followed by first-action selection, state observation and another solve. Registered A08/A09 (hashes and line anchors in the [proof provenance](proof-audit-provenance.json)) evidence that loop's simulated-state and fixed-program decision structure. The [source matrix](adaptive-policy-proof-audit.md#source-by-source-theorem-and-policy-matrix) and [implementation audit](adaptive-policy-proof-audit.md#recovered-implementation-evidence-a08a09) own those historical interpretations. The coefficients below are an **authored counterexample**, not L13's rocket coefficients or A08/A09 inputs.

The initial state is `(0,0)`, with `A=((1,0),(1,1))`, `B=(1,0)`, `E=(1,-1)`, stage actions `U0=(0,1)` and `U1=(-1,1)`, and `x[t+1]=A*x[t]+B*u[t]+E*w[t]`. The reference enumerates `W0=(-1,0,1)` and `W1=(0)`, with safe box `[-4,4]^2` at each stage and terminal squared Euclidean cost `x2[0]^2+x2[1]^2`. The authored state coordinates are integers; the checker converts their squared costs to `Fraction`. Squaring preserves the order of the nonnegative Euclidean norm. The complete continuous-domain example instead has `W0=[-1,1]`; the three-point catalogue here cannot certify its `forall w` quantifier or continuum maximum. Those bounds are proved analytically in the [audit](adaptive-policy-proof-audit.md#causal-game-value-and-strict-counterexample).

For a fixed remaining plan, the checker enumerates **all** future disturbance tuples and rejects the whole plan if any reached state is unsafe. It chooses the least worst terminal cost among feasible plans. At each observed next state, replanning repeats that fixed-plan calculation; it retains all tied first actions and executes the first in authored action order. It then enumerates every disturbance history under that selector to obtain its initial whole-history worst cost. Separately, finite Bellman recursion uses `min_u max_w V_next` at each state with control chosen **before** the current disturbance. Its first tied action is used for a separate whole-history execution check. Neither rule lets the current action depend on the current disturbance.

## Literal results

| Quantity | Exact squared cost or actions |
|---|---:|
| Fixed plans `(0,-1)`, `(0,+1)`, `(1,-1)`, `(1,+1)` | `4`, `4`, `2`, `10` |
| Initial fixed-plan optimum and its first action | `2`, action `1` |
| Replanning at observed states after `w0=-1,0,+1` | tied `(-1,+1)`, then `(-1)`, `(-1)` |
| Executed replanning costs at `w0=-1,0,+1` | `2`, `1`, `2`; worst `2` |
| Globally causal first action | `0` |
| Executed causal costs at `w0=-1,0,+1` | `0`, `1`, `0`; worst `1` |

Thus the finite catalogue exhibits the strict policy-class gap `V_causal=1 < J_replan=2` in **squared** cost, corresponding to norms `1 < sqrt(2)`. The causal continuation's worst cost is at the catalogue's interior disturbance `w0=0`, while both endpoint costs are zero. The separate one-step timing test uses actions and disturbances `(-1,+1)` and confirms worst cost `2`; an action allowed to see the current disturbance could obtain zero, which is a different information order. A whole-successor safety test rejects a plan whose two successors are outside a singleton target even though their enclosing interval intersects it. A nominal zero-disturbance test gives equal values for all three policy classes.

The older [nine-check proof utility](tools/check_proof_counterexamples.py) evaluates formulas and selected witnesses directly. This separate finite-game enumeration checks the decision order and executed selector behavior through a different calculation; agreement does not certify the continuous model. It does not enclose physical model error, validate sensors or actuator accumulation, run A08/A09, establish a source monograph theorem, or claim L13's published numbers. The installed [finite-feedback predecessor](../contracts/finite-feedback.md) remains a safety-only finite-table contract without terminal cost optimization. There is no Release timing or standalone algorithm-performance report for this research checker; any later product algorithm would require the repository's [reviewed report and publication gate](../architecture/published-algorithm-results.md).
