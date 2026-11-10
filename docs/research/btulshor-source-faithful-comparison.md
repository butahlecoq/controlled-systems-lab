# Faithful BTULSHOR modules and hull comparison

The first measured comparison uses capture commit `9979bec7`, ten explicit point clouds and five fresh processes per cloud, alternating provider order. It compares the unoptimized legacy port with QuickHull 2D, generic LP membership reduction, ITIS17 A43 (two pivot rules) and A44. The [native report](../../reports/algorithm-results/btulshor-source-faithful-20261110-v1/index.html), [raw summary](../../reports/algorithm-results/btulshor-source-faithful-20261110-v1/raw/summary.json) and [offline ZIP](../../reports/algorithm-results/btulshor-source-faithful-20261110-v1/btulshor-source-faithful-20261110-v1.zip) retain all outcomes. The report is also registered in the catalogue and visual gallery.

The minimal 2D input is `[[0,0],[2,0],[2,2],[0,2],[1,1],[1,0],[0,0]]`. Its exact hull is the square with corners `(0,0),(2,0),(2,2),(0,2)`: original IDs 0–3 are vertices, ID 4 is interior, ID 5 lies on an edge and ID 6 duplicates ID 0. The plot labels every original ID. The legacy routine returns corner IDs 3,0,1,2; another method may retain duplicate ID 6 instead of ID 0. Hull equality and irredundancy are checked independently of ordering and duplicate representative.

Of 300 method outcomes, 285 pass the exact check. The five legacy near-tolerance outcomes omit the small true extreme, as the original Pascal routine does; these are recorded as rejected without repairing the algorithm. Ten higher-dimensional QuickHull 2D outcomes are unsupported and have no measured call time. Timings describe these calls on an uncontrolled host; there is no performance ranking or universal correctness claim.

## Reproduce

Use the recorded commit and the pinned plotting requirements. The original Pascal source and FPC are not required for the public 45-case regression check.

```sh
python -m venv build/btulshor-env
build/btulshor-env/bin/python -m pip install -r scripts/reports/requirements.txt
cmake -S . -B build/btulshor -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCSL_ENABLE_HIGHS=ON -DCSL_ENABLE_QHULL=OFF -DCSL_BUILD_BTULSHOR_REPORT=ON -DPython3_EXECUTABLE="$PWD/build/btulshor-env/bin/python"
cmake --build build/btulshor --target csl_btulshor_compare --parallel 2
ctest --test-dir build/btulshor --output-on-failure -R '^btulshor_(source_differential|driver_contract)$'
build/btulshor-env/bin/python tests/reporting/check_btulshor_source_fixtures.py --driver build/btulshor/csl_btulshor_compare --output build/btulshor-oracle.json
build/btulshor-env/bin/python scripts/reports/btulshor/capture.py --driver build/btulshor/csl_btulshor_compare --output build/btulshor-source-faithful-20261110-v1 --render-python build/btulshor-env/bin/python --oracle-receipt build/btulshor-oracle.json
```

Capture requires a clean tracked checkout and a driver configured at its current commit. Use a new output path; saved bundles are immutable. After extraction, `python offline_check.py` verifies the inventory without native code, Git or plotting dependencies. For a single untimed functional case, run `csl_btulshor_compare --case input.json` with `{"operation":"kpabep","points":[[0,0],[2,0],[2,2],[0,2],[1,1],[1,0],[0,0]]}`.

The [module contract](../contracts/legacy-btulshor.md) describes the installed `CSL::legacy_btulshor` target, replaceable MODIF/KPABEP ports, literal REACH layout, source status codes and wrapper resource limits. Binary64 arithmetic is explicit; historical compiler bit identity is not claimed.
