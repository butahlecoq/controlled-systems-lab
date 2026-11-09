# Compare saved controller trajectories

`figures.py` consumes the accepted directories extracted from the three pilot
archives. It runs the affine, nonlinear and NMPC saved checkers before creating
output, requires complete execution/replay records and matches the scenario and
affine witness across bundles. It performs no optimization or integration.
Use the locked optional environment documented in `environment/README.md`:

```sh
python benchmarks/reporting/mpc11/figures.py \
  --affine <AFFINE_EXTRACT>/accepted \
  --nonlinear <NONLINEAR_EXTRACT>/accepted \
  --nmpc <NMPC_EXTRACT>/accepted --output <NEW_OUTPUT_DIRECTORY>
```

The three overlays are affine prediction, affine controls executed on the
nonlinear plant, and shrinking-horizon nominal NMPC execution. Fuel uses
oxidizer mass/flow and fuel mass/flow panels (selected by state names,
not assumed storage order); LV uses P/R. State and held-control traces
are exported alongside phase plots, in SVG and PNG. Circle/square markers show
initial/final states; stars show terminal targets. Intermediate labels are
physical times. The affine trace has values at hold boundaries; connecting
segments do not add independently integrated samples.

Plotted arrays, canonical scenarios, input record hashes, bundle inventory
hashes, checker output and renderer/style identities accompany each export.
These are individual numerical trajectories with local solver diagnostics,
not reachable-set boundaries, backward sets, global optima, minimax results or
continuous-time safety certificates. Pilot timings do not rank controllers.
No library API, required dependency or library release changes.
