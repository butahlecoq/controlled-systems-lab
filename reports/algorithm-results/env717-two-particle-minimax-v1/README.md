# TwoParticleGame finite reachability/minimax pilot

This is a source-derived finite-game example, not a continuous-action RL replay. The source commit, scenario, driver, executable, state graph, and independent replay are identified in the adjacent JSON records.

Reproduce with `cmake -S . -B build/report -DCSL_BUILD_ENV717_REPORT=ON -DCMAKE_BUILD_TYPE=Release`, `cmake --build build/report --target csl_env717_two_particle_minimax`, then run `python scripts/reports/env717/check_two_particle_minimax.py build/report/csl_env717_two_particle_minimax`.

The independent checker rebuilds the quantized RK4 graph, verifies every reachable state and transition, recomputes backward capture sets and dynamic minimax values, and replays the selected worst-case path. The report makes no timing or speedup claim.
