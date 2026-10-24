# EXT-03 temporal-memory Strategy A measurement

This harness measures one narrowly declared path: constructing the two-step
integrator problem, applying the one-step slew-memory lift, resolving and
registering the lifted problem with Strategy A's represented-dyadic exact
profile, executing it through the public `StrategyPort`, checking its
registry-verified complete optimal relation, mapping one analytic lifted
optimizer back to the original controls, and independently checking original
dynamics, absolute bounds, slew bounds, and objective value.

Expected analytic result: the minimum terminal state is `-1/4`. The unique
minimizing control history is `(u0,u1)=(0,-1/4)` from initial memory `p0=1/4`
with both slew increments in `[-1/4,1/4]`. The transformed joint history is
`(z0,z1,z2,v0,v1)=((0,1/4),(0,0),(-1/4,-1/4),(-1/4,-1/4))`.
Each timed call checks the compiled completeness verifier and recovers the
literal optimizer to the original coordinates. This does not establish
validated arithmetic or general coverage outside the exact nominal linear
profile.

## Measurement claim

The planned report claim is the median and range of end-to-end elapsed time per
checked call for this one fixed fixture, with seven measured batches after one
excluded warmup. There is no competing method, speedup, application-scale, or
scalability claim. The interval includes source problem construction, memory
lift, resolution, provider registration and preparation, Strategy A execution,
the compiled exact-family verifier, original-history recovery, and the
independent checks above. It excludes process startup, build, JSONL output, and
report rendering. Source-mapped limiter profiling is not part of this harness;
the report must say the limiter is unavailable rather than infer one from wall
time.

The raw event stream is retained before interpretation. A call fails the
collection if the lift is rejected, the Strategy A result is stopped or
nonoptimal, the complete family is not registry-verified, objective bounds or
coordinates differ, the relation omits the analytic optimum, or independent
original-history checks fail.

## Reproduction

The measurement must use a clean, reviewed source commit and a fresh Release
build directory. Configure the runner with the repository root as
`CSL_SOURCE_ROOT`, build `csl_ext03_temporal_lift_report` in Release, then run
the executable with `10 1 7` to emit one excluded warmup and seven measured
10-call batches. Save stdout as raw JSONL and stderr separately. Preserve
configure/build logs and the CMake compiler/configuration identity with the
collection. Rendering consumes only those saved files and must not rerun the
solver.
