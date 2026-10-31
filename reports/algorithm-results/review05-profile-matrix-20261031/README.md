# REVIEW-05 exact-profile matrix capture

## Measurement claim

This run checks whether Strategy A and Strategy B both complete the exact
T-S01, T-S02, and T-S03 profiles, pass each profile's registered complete-family
verifier, and return two distinct witnesses that pass original-problem
feasibility/objective checks. It also records paired phase timings and
model/profile metadata. It does not claim a performance winner or general
scaling law.

All three cases have one state, one control, and a two-step scalar integrator.
They vary the objective and optimal-family shape: T-S01 has a one-dimensional
optimal segment, T-S02 has a constant objective over the full feasible control
square, and T-S03 has a singular objective with an optimal terminal edge. This
is a matched profile matrix, not a controlled horizon or dimension ladder.

The existing driver excludes one warmup pair and alternates Strategy A/B order.
It runs seven measured pairs for T-S01 and five each for T-S02 and T-S03. Each
pair uses the same resolved problem, representation, numerical policy, provider
registries, and one-thread resource policy for both methods. The timed strategy
scope includes preparation, workspace creation, public strategy execution and
registered complete-family acceptance, selection of two distinct histories,
and their original-problem witness verification. It excludes process startup,
shared setup, JSON serialization, file I/O, and report rendering.

Each recorded trial must report a completed optimal result, a registered
complete family, two distinct witnesses, and numerical feasibility/objective
checks for both witnesses. Registry family verification is numerical evidence;
the witness checks do not establish completeness or formal optimality by
themselves.

## Limits and interpretation

The driver does not expose per-call memory, CPU time, or internal LP/convex,
projection, conversion, or membership call counts. A source-level limiter
profile is not part of the timed capture. Timings are descriptive for this
host/build and are not a speedup, strategy ranking, or scalability result.
General dimension/horizon workload matching, representation/output growth, and
source-attributed limiter evidence remain open under #95.

## Results

All measured attempts completed successfully, passed the registered complete
family check, selected two distinct histories, and passed original-problem
binding, feasibility, and objective checks. The offline event checker reports
7/7 verified attempts per side for T-S01, and 5/5 per side for T-S02 and T-S03.
One warmup pair per profile is excluded below.

| Profile | Reach-back end-to-end median (range) | Strategy B end-to-end median (range) | Verified pairs |
| --- | ---: | ---: | ---: |
| T-S01 exact integrator | 5.644 ms (5.360–5.842) | 1.343 ms (1.277–2.249) | 7/7 |
| T-S02 constant objective | 5.104 ms (5.029–5.217) | 0.538 ms (0.515–0.603) | 5/5 |
| T-S03 singular objective | 4.792 ms (4.712–5.307) | 1.265 ms (1.217–1.287) | 5/5 |

The medians are lower for Strategy B in these three tiny exact profiles. The
performance conclusion is **inconclusive**: the run has only five to seven
measured pairs per profile and no source-attributed limiter profile, and the
three profiles are not controlled size variations. Do not generalize these
timings to other problems or claim a scalability advantage.

The registered profile verifiers require the canonical H relations. Their
source-declared shape provides a small representation-size baseline:

| Profile | Joint H coordinates | Inequality rows | Equality rows | Stored nonzeros | Optimal family shape |
| --- | ---: | ---: | ---: | ---: | --- |
| T-S01 | 5 | 4 | 4 | 10 | Segment |
| T-S02 | 5 | 4 | 3 | 11 | Full control square |
| T-S03 | 5 | 2 | 4 | 7 | Terminal edge |

These are counts from the canonical relation constructors in
`src/synthesis/strategy_ts01/analytic_profile.cpp` and
`src/synthesis/strategy_a/strategy.cpp`, bound by the registered verifiers.
The driver does not export or measure per-run matrix bytes, allocation, or
peak memory. State and control dimensions and horizon are identical in all
three cases, so this table is not a representation-growth sweep.

The capture host was Linux x86_64 on an AMD Ryzen 5 3550H with 8 logical CPUs
and 8,108,216,320 bytes RAM. The recorded load averages were 3.225, 4.437, and
3.140 before each process; the three short processes observed those same values
afterward. Sides alternate within each profile. Each profile process requested
one backend thread, a 300-second CPU limit, an 8 GiB address-space limit, and a
300-second wall timeout. The run completed in under 0.1 seconds per process.

## Reproduction and retained files

The rendered report is `index.html`; its standalone figures are `optimal-control-histories.svg` and `paired-timings.svg`. An offline ZIP is provided as `../review05-profile-matrix-20261031.zip`.


The `csl_review05_profile_matrix` target reuses the existing public paired
comparison driver, adding it to the isolated REVIEW-05 benchmark project. From
the repository root:

```sh
cmake -S benchmarks/reporting/review05 \
  -B /home/butahlecoq/.local/share/codex/build/review05-profile-matrix-driver-20261031 \
  -DCSL_SOURCE_ROOT="$PWD" -DCMAKE_BUILD_TYPE=Release -G Ninja
ninja -C /home/butahlecoq/.local/share/codex/build/review05-profile-matrix-driver-20261031 \
  csl_review05_profile_matrix
python3 benchmarks/reporting/review05/capture_profile_matrix.py \
  --executable /home/butahlecoq/.local/share/codex/build/review05-profile-matrix-driver-20261031/csl_review05_profile_matrix \
  --raw /tmp/review05-profile-matrix-rerun/raw
python3 benchmarks/reporting/review05/check_profile_matrix.py \
  --raw /tmp/review05-profile-matrix-rerun/raw \
  --out /tmp/review05-profile-matrix-rerun/checks.json
```

The Release build used GCC 16.2.1, CMake 3.31.6, Ninja 1.13.2, HiGHS 1.11.0,
and Qhull 8.0.2. The driver binary SHA-256 is
`75b1e4a58352d5ec26c70dc3ff2eb1627222b97e113426728d40a67046b412f4`.
Algorithm source was `809c83d6f7d353e54b354dd7af4381a95534bf26`; the isolated
benchmark CMake target and capture/check scripts are included with the
resulting source change.

The committed `inputs/` copies and `raw/` directory retain source scenarios,
event JSONL, stdout/stderr, per-process limits,
load observations, source/scenario/executable hashes, and exit status. Build
and configure logs preserve the initial failed target/configuration attempts
and the successful retry; they are not omitted from the evidence bundle.
`checks.json` contains the attempt counts, AB/BA ordering, verification totals,
medians and ranges. `SHA256SUMS` covers all bundle files except itself.

The multi-axis matched workload, actual representation/output growth, and
source-level limiter profile remain open under #95.
