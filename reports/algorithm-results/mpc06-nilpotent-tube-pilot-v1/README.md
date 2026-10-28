# Exact nilpotent tube-MPC feasibility pilot

A two-state affine double integrator with continuous inputs and compact stagewise additive disturbance. Full-state feedback makes the error matrix nilpotent of index 2, giving an exact finite RPI tube. The solver checks exact H-relation inclusion; an independent rational checker enumerates the matched eight disturbance-vertex paths for the fixed zero nominal plan.

The saved result contains exact support tightenings, initial tube membership, a feasible nominal plan, an empty-tightening edge case, and an exact unsafe-input witness. Objective values and approximation comparisons are not claimed. This is a new synthetic exact study, not a historical reproduction.

Rebuild with `cmake -S . -B build/mpc06 -DCSL_BUILD_MPC06_REPORT=ON -DCMAKE_BUILD_TYPE=Release`, then `cmake --build build/mpc06 --target csl_mpc06_tube_pilot`; validate with `python3 scripts/reports/mpc06/check_tube.py build/mpc06/csl_mpc06_tube_pilot`.
