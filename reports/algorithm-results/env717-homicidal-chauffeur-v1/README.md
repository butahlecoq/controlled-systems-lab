# HomicidalChauffeur finite reachability/minimax pilot

This source-attributed report applies CSL finite-feedback reachability and causal minimax to a bounded finite action catalogue and four 0.1-second stages. It does not reproduce the continuous-action RL outcome. The source, scenario, executable, complete reachable graph and independent replay are identified in the saved records.

Reproduce with `cmake -S . -B build/report -DCSL_BUILD_ENV717_REPORT=ON -DCMAKE_BUILD_TYPE=Release`, `cmake --build build/report --target csl_env717_homicidal_chauffeur`, then `python scripts/reports/env717/capture_homicidal_chauffeur.py build/report/csl_env717_homicidal_chauffeur --output reports/algorithm-results/env717-homicidal-chauffeur-v1`.

The independent checker reconstructs all quantized RK4 transitions, forward reachable states, backward capture sets, finite minimax values and the selected worst-case path. The zero-sum signs are an analysis assumption because the source returns positive separation without assigning separate payoffs. The plotted polygons are convex envelopes of projected graph states and are visual guides, not exact projected reachable sets. Capture records five fresh-process runtime observations for this adapter, including process startup and graph construction but excluding build, replay, and rendering. It makes no performance comparison or speedup claim.
