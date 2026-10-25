# B09 A08 source-reference bundle

An independent finite-action minimax reference derived from local A08 MATLAB source hashes and owner-selected objective variants. It is not a historical reproduction and does not restore a paper table-row mapping. See [benchmark notes](../../../benchmarks/reporting/issue6/README.md#b09-a08-source-revision-fuel-reference) and [scenario inputs](scenario.json).

Each figure projects the 4D terminal reachable set to flows `(x1,x3)` and stocks `(x2,x4)`. The fixed open-loop replay and receding-horizon nonlinear replay are plotted separately; neither is the set boundary. Replanning is a trajectory example, not a globally optimal feedback policy.

An independent Python oracle enumerates every action plan and disturbance-corner history, checking stage constraints and terminal objective. Both lambda cases agree on every minimizing open-loop plan. Raw measurements retain one excluded warmup and seven alternating calls per objective. They support descriptive single-adapter latency only.
