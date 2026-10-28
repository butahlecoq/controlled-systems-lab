# MPC-02 direct versus exact slew-memory formulation pilot

Status: exploratory measurement; timing conclusion is inconclusive.

This bundle compares one authored two-stage slew-constrained scenario using two joint formulations and the same Release HiGHS convex adapter. The direct program keeps the full-history slew row. The lifted program removes that row and models the same slew bound with exact one-step input-memory augmentation. It is a formulation-size and solver-call pilot, not a comparison of different optimization algorithms or a general performance result.

## Mathematical check

Both runs solve scenario `mpc02-slew-2d-v1`, SHA-256 `a965a25bbd87792dc2721739c7ed1b6505edc6e83de3cb08322eeed05da0f348`. Its physical objective is

```text
J(u0,u1) = (u0 - 1/2)^2 + u1^2
```

subject to `u0,u1 ∈ [-1,1]` and `|u1-u0| ≤ 1/4`. The exact rational optimum is uniquely attained at `(u0,u1)=(3/8,1/8)` with `J=1/32`: this is the projection of `(1/2,0)` onto the active boundary `u0-u1=1/4`. Each successful attempt checks the primal through the numerical program checker and independently checks the recovered physical controls, slew row, and objective against those rational values. All successful attempts returned the same witness and objective with zero reported residual.

## Formulation and timing results

The authoritative run is `events-r3.jsonl`, captured from source commit `f32d11b2c19b680086ed324136323f231e5ed8f9`. It has one warmup per side and seven measured alternating pairs. Values below are medians and full ranges across the seven measured attempts; times are nanoseconds.

| Formulation | QP variables | QP rows | Assembly | Provider preparation and workspace | Solver call |
|---|---:|---:|---:|---:|---:|
| Direct full history | 8 | 11 | 15,086 (14,877–15,854) | 4,749 (3,352–4,819) | 781,739 (751,567–808,559) |
| Exact slew-memory lift | 11 | 18 | 18,089 (17,530–25,422) | 4,749 (4,260–4,819) | 814,915 (798,920–849,975) |

The two formulations preserve the same checked physical witness and value. The lifted program has more variables and rows in this case. Its observed solver-call median is also higher in this run, but no speed winner is claimed: the problem is tiny, the sample is short, and no hardware-counter profiler was available. `perf` and GNU `time` are absent; the process had no cgroup CPU or memory quota. The run was pinned to CPU 0, used a 30-second timeout, and passed a one-worker/one-native-thread resource policy. Timing differences remain inconclusive without a usable limiter/profile and larger matched workloads.

Machine-readable medians, ranges, sample shape, and the inconclusive classification are in `summary.json`; environment and limiter availability are in `environment.txt`.

## Attempt retention

- `events.jsonl`: first driver attempt, retained with all 16 failed calls. The builder rejected a non-admitted profile string before timing; no values from these calls are included in the timing table.
- `events-r2.jsonl`: 16 successful calls from the corrected driver before the measurement code was committed. Retained as a pre-capture run.
- `events-r3.jsonl`: authoritative 16-call run from the committed source. It contains two warmups and fourteen successful measured attempts; its header records source commit, scenario digest, adapter version, resource settings, and exact oracle.

## Reproduction

From a clean checkout at `f32d11b2c19b680086ed324136323f231e5ed8f9` with GCC 16.2.1 and CMake 3.31.6:

```sh
cmake -S benchmarks/reporting/mpc02/runner -B build/mpc02-slew-release \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++
cmake --build build/mpc02-slew-release --target csl_mpc02_slew_measure -j2
taskset -c 0 timeout 30s build/mpc02-slew-release/csl_mpc02_slew_measure \
  examples/scenarios/mpc02-slew-2d.json /path/to/new-events.jsonl
```

The executable refuses to overwrite an event file. Use a fresh output path for each run. `SHA256SUMS` covers the retained event files and this README.
