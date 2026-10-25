# B09 A08 source-reference bundle

An independent finite-action minimax reference derived from local A08 MATLAB source hashes and owner-selected objective variants. It is not a historical reproduction and does not restore a paper table-row mapping. See [benchmark notes](../../../benchmarks/reporting/issue6/README.md#b09-a08-source-revision-fuel-reference) and [scenario inputs](scenario.json).

The figures project the four-dimensional terminal reachable set into the flow plane `(x1,x3)` and stock plane `(x2,x4)` for each objective. They also show fixed open-loop and receding-horizon nonlinear replay trajectories, plus the stage-by-stage fuel and oxidizer stocks. Shaded boundaries come from the uncertain linear model; replay paths are separate deterministic examples. The plotted dots are stored V-representation rows; duplicate points can overlap.

The independent Python oracle enumerates all 6,561 action plans and disturbance-corner histories for each objective. It confirms 76 feasible plans, four minimizers for lambda 0 and six for lambda 1. Both replays use the same nonlinear terminal criterion: open-loop replay J values are 16.627024 and 25.297590; receding-horizon values are 16.624465 and 25.295908. These differ from the robust predicted minimax objectives 50.179931 and 115.794115.

Each terminal V representation stores 256 rows, with 256 distinct coordinates for lambda 0 and 240 for lambda 1. The rows are not asserted to be only exposed extreme points.

Seven alternating measurement rounds per objective each use one excluded warmup in a fresh process. Median call time was 242.333 ms (range 234.719–251.626) for lambda 0 and 240.476 ms (range 234.693–242.919) for lambda 1. Peak process RSS observations were 16340 KiB and 16340 KiB, respectively. The Linux high-water mark includes the full process and is not per-stage memory.
