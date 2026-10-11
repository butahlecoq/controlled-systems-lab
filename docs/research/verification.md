# Verification record

Date: 2026-10-11. This records checks of the research artifacts, not product readiness.

Commands executed:

~~~text
python docs/research/tools/characterize_legacy.py
python docs/research/tools/reference_b08.py
python docs/research/tools/verify_docs.py
~~~

See [machine-readable verification](verification.json), [legacy characterization](legacy-characterization.json) and [B08 independent reference](reference-b08.json).

Verification covers original SHA-256 preservation, inventory/page counts, duplicate pairs, local documentation links, research utility syntax and numerical-record consistency. Specific check counts are in the JSON; its status is authoritative for this run.

Twenty-one PDFs were text-extracted, along with DOCX, legacy Word piece-table text and source files. Selected mathematical/table pages were visually reviewed. Two legacy Word files retain unresolved embedded equations. Public checkouts omit originals/raw extraction; hash verification then reports those checks as skipped.

Full original MATLAB/Pascal implementations, all published nonlinear simulations, all proofs and every rendered mathematical expression remain outside this initial verification. The B08 computation uses rounded displayed data and floating-point arithmetic.

The initial public release contains curated documents, inventory/provenance, research utilities, characterization/reference JSON and review templates. Original articles/listings, raw extractions and temporary PDF images are excluded by .gitignore.
