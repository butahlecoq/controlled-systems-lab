# APP-04 saved directional ellipsoid report

The frozen numerical source is commit `5c11288e436f41ae832ab6ac89e180f6cf00a43d` with tree `f6d932bb4e4494f393095449bcf0ecc82b5bdd5a`. Its public `run_registered` driver covers a square with axis and diagonal orientation and a horizontal segment with one zero radius. Every call checks the literal center, orientation, projected bounds, radii, all source vertices, structural basis, relation and missing error bound after the timed interval. The independent policy also checks exact stored-binary64 vertex inclusion.

From a separate clean checkout at that commit, create a fresh capture outside the source tree:

```sh
python scripts/reports/app04/capture.py --source <clean-frozen-checkout> --capture <fresh-capture-directory> --commit 5c11288e436f41ae832ab6ac89e180f6cf00a43d --cmake <cmake-executable>
python scripts/reports/app04/collect.py --capture <capture-directory> --source <clean-frozen-checkout> --out reports/algorithm-results
python scripts/reports/app04/render_saved.py --bundle reports/algorithm-results/app04-ellipsoid-fd302c34092f8b19 --check
python scripts/reports/stage_app04.py --source reports/algorithm-results/app04-ellipsoid-fd302c34092f8b19
```

The committed report ID is `app04-ellipsoid-fd302c34092f8b19`. The preserved capture is outside the repository at `D:\work\PhD\captures\app04-capture-20261019-v2`; it is an audit input, not an installed dependency. The collector checks clean prebuild and postrun source receipts, executable hash, Release CMake configuration, every raw driver row and exact source bytes. The renderer reconstructs the HTML, 2D SVG, summary, manifest and offline ZIP from saved bytes alone. The publication catalog binds renderer and stager hashes, and the main-only workflow stages only the reviewed inventory.

One excluded 100-call warmup per case preceded seven rotated three-case rounds of 100 calls each: 2,100 verified measured calls, zero observed failures. Each timed interval covers one public `run_registered` call, including registry selection, construction and independent native containment admission. It excludes the post-call literal oracle, fixture setup, CSV serialization and rendering. Median batch durations for axis square, diagonal square and horizontal segment were respectively 921,200 ns, 1,114,800 ns and 607,900 ns; their saved ranges appear in the report. These are descriptive single-adapter durations. There is no competitor, speedup, source-mapped limiter, global error bound, validated prior rounding guarantee, MATLAB or ET result.
