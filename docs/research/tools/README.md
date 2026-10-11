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
