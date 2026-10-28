# TwoPoints finite-feedback pilot v1

This immutable report bundle extends the existing source-attributed three-stage TwoPoints pilot with CSL's `reachability::finite_feedback` solver. It retains the original fixed-plan minimax result and adds a finite feedback threshold/policy result on an exact scale-2000 integer graph. See the HTML report for scope, assumptions, and limitations.

The feedback result is exact for the stated finite action and disturbance vertex game only. It does not establish continuous-state feedback, cover disturbance values between the vertices, claim cost-optimal admissible actions, or reproduce the upstream continuous-action RL task.

The C++ report driver is `benchmarks/reporting/env717/two_points.cpp`; the independent graph, transition, policy, threshold, witness, and figure checker is `scripts/reports/env717/check_two_points.py`. Publication staging is performed by `scripts/reports/stage_env717_two_points.py`.
