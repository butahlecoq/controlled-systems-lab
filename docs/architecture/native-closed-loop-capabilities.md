# Native closed-loop capability profiles

The immutable continuous-NMPC pilot catalogue remains
[`closed-loop-pilot-capabilities-v1.json`](../catalogue/closed-loop-pilot-capabilities-v1.json).
Native finite-action profiles use a separate source-bound manifest and seal:
[`closed-loop-native-capabilities-v1.json`](../catalogue/closed-loop-native-capabilities-v1.json)
and its adjacent `.sha256` file. The native manifest contains five backward-graph
profiles and five fixed-plan MPC profiles for each of the three source-bound task
contracts. Every graph binds the full task hash, the task's finite-action profile,
the controller factory options, native implementation sources and the common
physical execution source. The current seal is provisional while the native
fixed-plan source is being finalized; regenerate it after that source freeze
before running registered episodes.

Run a profile through the same resolver, prepare stage, worker, episode runner and
independent postchecks as the baseline pilot. For example:

```sh
python benchmarks/reporting/closed_loop/run_closed_loop.py \
  --task syn-nl-lv-01 \
  --controller-id native-exact-polytope-backward-graph/1 \
  --bridge /path/to/nonlinear_replay_bridge
```

Set `CSL_NATIVE_POLICY_BRIDGE` to the executable built from the native policy
target. Preparation records that executable's hash and reported build/backend
profile separately from the common plant bridge. A missing executable or
incompatible provider is a preparation failure, not evidence that the mathematical
task or controller profile is unsupported.
At query time, a provider or optimizer that cannot be resolved is recorded as
`unavailable`; a resolved method that rejects a profile or dimension is
`incompatible`. Both leave mathematical support `not_evaluated` and do not count as
a task infeasibility result.

The graph profiles identify the selected reachable-set, hull, vertex-LP,
representation and finite-action control-optimizer roles. Fixed-plan profiles
record geometry, hull, vertex-LP and conversion roles as `not_used`; their selected
representation and bounded candidate-coverage result remain explicit. Runtime
receipts retain the adapter's actual invocation and geometry traces alongside the
declared role labels. The control-optimizer role is distinct from vertex LP,
Bellman and terminal-solver roles.

Rebuild the native source-bound manifest and seal after source/profile changes with
`python benchmarks/reporting/closed_loop/capabilities.py --write-native`. This
does not rewrite the published v1 manifest, report, ZIP or historical run records.
