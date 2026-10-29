# MPC-08 nonunique optimizer-fiber pilot

This is a finite, exact two-step double-integrator case for [issue #604](https://github.com/butahlecoq/controlled-systems-lab/issues/604). It complements the separate unique one-step explicit-MPC report. It does not complete #604.

The dynamics are `p_next=p+v`, `v_next=v+u`, with each control in `[-1,1]`. The initial domain is `[-3,3] × [-2,2]`; the terminal objective is the square of terminal velocity. The exact optimal value is zero throughout that domain. The complete optimizer family is

```text
u0 ∈ [-1,1] ∩ [-v0-1, -v0+1]
u1 = -v0-u0
```

The analytic reference separately selects the minimum-norm history `u0=u1=-v0/2`. The figure's left panel shows the full initial rectangle, with fill color encoding that selected first action. The right panel shows the full optimal control fiber at `(p0,v0)=(0,0)` and marks the tie-broken selector.

The saved sample uses 15 initial states and 45 histories (each optimal fiber's endpoints and midpoint). Strategy A candidate relations contain all 270 sampled histories across their 45 warmups and 225 measured calls, but all calls stop with an operation rejection because HiGHS reports a nonzero quadratic coefficient at or below its `1e-12` native-removal threshold. Strategy B contains all sampled histories; 252 calls complete and 18 are noncompleted, and every mathematical outcome remains undetermined. The online two-control QP returns a feasible optimal point with value zero on all 270 calls. These checks do not establish equality between either strategy candidate and the analytic full family. The raw observations preserve every status.

Timing rows are descriptive only. Calls are interleaved with five measured repetitions per query and one warmup per method; no load or limiter profile was captured, so there is no performance-winner claim. See `build-provenance.json` for compiler, dependency, binary, source, input, and result hashes.

Reproduce from the source commit named in `build-provenance.json`:

```sh
python3 benchmarks/reporting/mpc08_explicit/explicit_nonunique_double_integrator.py
cmake -S . -B build/mpc08-nonunique -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=ON -DCSL_BUILD_MPC08_REPORT=ON
cmake --build build/mpc08-nonunique --target csl_mpc08_explicit_compare --parallel 4
build/mpc08-nonunique/csl_mpc08_explicit_compare benchmarks/reporting/mpc08_explicit/generated/explicit-nonunique-queries.csv > benchmarks/reporting/mpc08_explicit/generated/csl-nonunique-observations.jsonl
```

The experiment adds no public API or installed dependency. It uses the existing optional report target and existing HiGHS/Qhull pins. Exact solver outcomes and timing interpretation remain as recorded rather than being repaired or promoted into a full-family or speed claim.
