# Run a scenario

Use `scenario_cli` to validate a scenario or run the guarded reach-back and
direct-joint comparison on a supported T-S01 or T-S02 profile.

## Build the installed CLI

Configure and build the library, then install it to a local prefix:

```sh
cmake --preset dev
cmake --build --preset dev
cmake --install build/dev --config Release --prefix "$PWD/build/install"
```

Configure the examples as an installed-package consumer and build the CLI:

```sh
cmake -S examples -B build/examples \
  -DCMAKE_PREFIX_PATH="$PWD/build/install" -DCMAKE_BUILD_TYPE=Release
cmake --build build/examples --target scenario_cli
```

For a multi-configuration generator, add `--config Release` to the build
command. The executable is under `build/examples/Release` on Visual Studio and
`build/examples` on single-configuration generators.

## Validate a scenario

Pass a scenario path to `--validate-only`:

```sh
build/examples/scenario_cli --validate-only examples/scenarios/two-stage-integrator.json
```

The command prints the resolved problem identity, source digest, horizon,
dimensions and requested run mode. It does not create providers or invoke a
solver. Invalid and unsupported input prints a field-specific diagnostic and
exits with status 2.

## Run the paired comparison

Run the template with the default profile:

```sh
build/examples/scenario_cli --run examples/scenarios/two-stage-integrator.json
```

The default profile is `ts01_exact_integrator`. Choose
`ts02_constant_integrator` with `--profile` when the scenario supports that
profile. Set registered backend IDs, the witness seed, or thread count with
`--lp`, `--convex`, `--seed`, or `--threads`:

```sh
build/examples/scenario_cli --run examples/scenarios/two-stage-integrator.json \
  --profile ts01_exact_integrator --lp csl.lp.highs --convex csl.convex.highs \
  --seed 42 --threads 2
```

You can also put backend, witness, numerical and resource settings in the
scenario's `run` object. `--threads` overrides its thread allocation. Resource
settings are admission and accounting requests; they do not impose an operating
system memory cap or a process-wide concurrency limit. See the
[scenario input contract](../contracts/scenario-input.md) for accepted fields.

The CLI runs both strategies on the same resolved problem, selects requested
witnesses, and checks them against the original problem. These numerical checks
do not prove a complete optimal family or establish which strategy is faster.
The CLI supports only the two named profiles and registered providers available
to this executable. Unsupported combinations remain explicit outcomes.

## Save the strategy records

Pass a new output directory to save both attempts through the artifact API:

```sh
build/examples/scenario_cli --run examples/scenarios/two-stage-integrator.json \
  --output-dir build/results/two-stage-integrator-01
```

The CLI writes `reach-back.run.json` and `strategy-b.run.json` as
`csl.run-statistics/5` recorded artifacts only after both strategies return
completed optimal outcomes and every selected witness passes numerical checks.
If a strategy or witness check fails, the command returns before publication.
Use a fresh directory because the CLI refuses to replace existing result
files. The records preserve family claims as `unverified_recorded_data`;
decoding does not make those claims trusted evidence. The two records are not a
paired-comparison artifact.
