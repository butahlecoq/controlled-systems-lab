# Research utilities

These scripts support archival analysis and independent numerical checks. They do not select the product language or implement the proposed general library.

Run from the repository root using a Python environment with PyMuPDF, NumPy and SciPy. The assessment environment used NumPy 2.3.2 and SciPy 1.16.3; a complete environment lock has not been recovered.

~~~text
python docs/research/tools/extract_archive.py
python docs/research/tools/extract_legacy_word.py
python docs/research/tools/characterize_legacy.py
python docs/research/tools/reference_b08.py
python docs/research/tools/check_b04.py
~~~

The first three require the local original papers and registration folders in their inventory paths. They are intentionally excluded from the public repository. Run both extraction scripts in order: the first handles PDFs/DOCX/source text; the second updates legacy Word entries with piece-table text. Extraction regenerates the inventory and raw text and should be run only when refreshing the source register intentionally.

Legacy Word recovery does not decode embedded Equation Editor objects or figures. PDF/DOCX extraction is not a faithful reconstruction of every formula.

The characterization script executes selected archived definitions, bypassing demonstration code, and writes legacy-characterization.json. The B08 reference is independent of archived Python source: it uses the transcribed four-step linear model, enumerates all finite controls and disturbance-box corner images, and writes reference-b08.json. It is a floating-point reference, not a validated rounding proof, nonlinear simulation or historical timing reproduction.

~~~text
python docs/research/tools/verify_docs.py
~~~

The B04 consistency utility uses only Python standard-library rational arithmetic. It reads the historical manifest, checks terminal invariants and computes an unrestricted terminal-plane lower bound; it does not solve missing historical constraints. Results are in [b04-consistency.json](../b04-consistency.json).

The verification utility checks document links, original hashes where originals exist, inventory coverage, Python syntax, and reference JSON consistency. It is documentation/research verification, not a product test suite.

## B04 saved-witness reference check

[check_b04_saved_witnesses.py](check_b04_saved_witnesses.py) reproduces the [curated B04 witness/replay checks](../b04-saved-witnesses.md). It requires Python 3, NumPy and SciPy (`loadmat` with `simplify_cells`); the recorded run used Python 3.13.5, NumPy 2.3.2 and SciPy 1.16.3. PyMuPDF, MATLAB, a solver and archived executable code are not required. These are documented dependencies and observed versions, not new project dependency pins.

Supply each private original explicitly. The following PowerShell example assumes you set `$privateB04` to the directory containing your registered originals, and `$checkOutput` to a separate writable JSON destination:

~~~powershell
python -O docs/research/tools/check_b04_saved_witnesses.py --figure "$privateB04/1st.fig" --kernel "$privateB04/program.m" --driver "$privateB04/ReachableSets.m" --article "$privateB04/Shorikov_Kalev_Article_v4.pdf" --image "$privateB04/1st.png" --output "$checkOutput"
~~~

The three mandatory flags verify A39 (FIG), A40 (kernel) and A01 (driver) against registered SHA-256 and byte counts. Optional `--article` and `--image` add A41/A42 identity checks; neither redoes the prior visual audit. Sources are read only, and an output path that aliases an input is rejected. The private path is never included in successful JSON. Omit `--output` to print JSON to stdout. Output contains source IDs/hashes, aggregate checks, endpoints, objectives, rounding-box results, replay events and environment versions. It contains no full trajectory/action arrays. All seven relevant saved histories are read directly from fixed graphics anchors.

Exit 0 means all declared witness/replay checks passed, including detection of the frozen discrepancy; it does not mean full historical reproduction. Exit 1 means a numerical check failed (inspect the JSON `checks` object). Exit 2 reports missing/changed sources, unavailable dependencies or invalid input/output. Checks remain active under `python -O`. The archived kernel is implemented as authored Python formulas after source identity verification, not executed or dynamically translated. The [evidence JSON](../evidence/b04-saved-witnesses.json) records derivations, source anchors, regression tolerances and a five-source run's aggregate output. Regeneration produces the `observed_checks` portion; editorial provenance/conventions remain authored separately.

Run public boundary tests without private files:

~~~text
python docs/research/tools/test_b04_saved_witnesses.py
~~~

That command tests actionable missing-source errors, integrity rejection and input preservation, and explicitly **skips archival numerical reproduction**. To execute all tests against the originals:

~~~powershell
python docs/research/tools/test_b04_saved_witnesses.py --figure "$privateB04/1st.fig" --kernel "$privateB04/program.m" --driver "$privateB04/ReachableSets.m"
~~~

The tests run the checker subprocess under optimized Python and compare actual computed values with literals from the prior independent audit. They do not validate complete stage feasibility, constrained optimality, full families, frozen-controller generation or a corrected 100-second replay. No full archive search or native rebuild is needed for this focused reference utility.
