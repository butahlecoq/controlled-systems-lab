# T-S03 Strategy A/B capture provenance

## Defined fixture

This is a new synthetic comparison fixture, ID `mpc01-ts03-singular-integrator-v1`. It follows the exact analytic T-S03 profile already documented in `docs/architecture/framework-composition.md`: `x0=0`, `x[t+1]=u[t]`, independent `u0,u1 in [0,1]`, horizon two, no stage cost, and terminal cost `(x2-1)^2`. The exact minimizer relation is `u0 in [0,1], u1=1`; this follows from `x2=u1` and is not a reconstruction of #421 or the article-derived B04 case.

## Build and run

The worktree was clean at source commit `0f407af581c3a5b536d5d76f6e889fef542c4597`. The Release build used GNU C++ 16.2.1, CMake 3.31.6, Ninja, HiGHS 1.11.0 and Qhull 8.0.2. The registered example was built through the repository's installed-consumer path. `CMakeCache.txt` preserves the configuration; the install and installed-example configure/build logs are retained beside this note. The project library build completed successfully. The executable SHA-256 is `f87118d2114992fea92625e60599ff6937de694a189389cc3e173187f2d4f73e`.

To rebuild from the pinned source commit, use the repository's CMake 3.31.6,
Ninja, GNU 16.2.1, and network access for pinned dependencies:

```sh
PR_CHECKOUT="$PWD" # Keep this PR checkout: it contains the scenario and capture/report tools.
SOURCE_WORKTREE=/tmp/csl-mpc01-ts03-source
git worktree add --detach "$SOURCE_WORKTREE" 0f407af581c3a5b536d5d76f6e889fef542c4597
mise exec cmake@3.31.6 -- cmake -S "$SOURCE_WORKTREE" -B /tmp/mpc01-ts03/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DCSL_DEPENDENCY_PROBES=OFF
mise exec cmake@3.31.6 -- cmake --build /tmp/mpc01-ts03/build --parallel 4
mise exec cmake@3.31.6 -- cmake --install /tmp/mpc01-ts03/build \
  --prefix /tmp/mpc01-ts03/install
mise exec cmake@3.31.6 -- cmake -S "$SOURCE_WORKTREE/examples" -B /tmp/mpc01-ts03/examples-build \
  -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=/tmp/mpc01-ts03/install
mise exec cmake@3.31.6 -- cmake --build /tmp/mpc01-ts03/examples-build \
  --target registered_synthesis_comparison --parallel 4
```

The run command was:

```sh
systemd-run --user --scope --quiet -p MemoryMax=2147483648 -p MemorySwapMax=0 \
  python3 "$PR_CHECKOUT/scripts/reports/mpc01/capture_strategy_ab_limited.py" \
  --executable /tmp/mpc01-ts03/examples-build/registered_synthesis_comparison \
  --scenario "$PR_CHECKOUT/docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/scenario.json" \
  --events /tmp/mpc01-ts03-run/strategy-ab-ts03-events.jsonl \
  --resource-profile /tmp/mpc01-ts03-run/resource-profile.json \
  --workdir "$SOURCE_WORKTREE"
```

The separate pinned worktree contains only source/build files at commit `0f407`;
the PR checkout supplies the scenario and portable supervisor. The event output
directory must be fresh because the capture refuses to overwrite results.

To rebuild the retained comparison record and HTML/SVG reading layer from the
saved inputs, run the record builder and renderer from the repository root:

```sh
python3 scripts/reports/mpc01/build_strategy_ab_records.py \
  --events docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/strategy-ab-ts03-events.jsonl \
  --scenario docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/scenario.json \
  --environment docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/capture-environment.json \
  --codec-environment docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/codec-environment.json \
  --output docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1/comparison-record.json
python3 scripts/reports/mpc01/summarize_strategy_ab_ts03.py \
  docs/research/evidence/mpc01-strategy-ab-ts03-20261103-r1
```

One excluded warmup pair and five measured pairs alternated A/B then B/A. One process ran at a time. A systemd user scope enforced a 2 GiB cgroup-v2 memory cap, swap disabled, and the supervisor applied a 300-second process-group watchdog to the complete invocation. This is a suite-level constrained capture, not the comparison contract's per-attempt limiter profile. Raw stdout is retained separately and byte-identically to the event JSONL.

## Capture correction

The first algorithm process emitted all twelve successful trial rows, but the initial supervisor mistakenly expected ten. Its nonzero validation exit and all generated outputs are retained under `setup-attempts/supervisor-row-count-mismatch/`. After correcting that check and exercising the parameterized supervisor, the canonical record and timings were captured by the final portable-supervisor run from a clean worktree at the pinned source commit. Earlier successful recaptures were superseded; only the final run and the initial failed supervisor check are retained here.

## Evidence limits

The application reports complete-family verification for this compiled T-S03 profile and independently replays two selected histories against the original scenario. The trajectory verifier's separate optimality and completeness fields remain `unsupported`. The analytic optimal-family statement is independently derived above. Timings exclude process startup, shared scenario/provider setup, serialization, build and rendering. The fixture is deliberately tiny; these measurements support no general performance ranking. The broader #597 matrix, external comparison and Pages catalogue deployment are still pending.
