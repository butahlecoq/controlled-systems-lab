# Reproduce the saved checks and figure

The raw algorithm capture used clean source commit
`3b98f5b02838909981b7ce70378f58dc25c74457`. Its original source copies and
`checks-initial-3b98f5b0.json` are retained. Post-capture review fixed process-stop
classification and bound rendering to checked bytes at
`77db095b85675a783f6dd51a44a5a54545722ad2`. These checker fixes did not rerun or
rewrite any algorithm history. Their source/provenance is in `post-capture/`.

After extracting the complete offline ZIP into a new directory:

```sh
sha256sum -c SHA256SUMS
python3 post-capture/check_family_query.py .
# Use the repository's optional report environment: Matplotlib 3.11.2,
# jsonschema 4.25.0, six 1.17.0 (see source/report-requirements.txt).
python3 post-capture/render_family_query.py .
```

The figure renderer uses only saved histories and shared quantitative axis
helpers preserved in `source/`. Its SVG and PNG exports identify scalar state
dimension one, two control coordinates, and actual selected scalar state paths.
Raw observations and their hashes are the evidence; rerunning the checker
updates checker-duration observations and `checks.json`, so it changes the
previous manifest. Verify the original checksums before regeneration and retain
regenerated outputs separately when comparing them.

To recapture algorithm work, check out the exact capture commit in the full
repository and follow `source/FAMILY-QUERY.md`. Set a new build/output path and
pass the newly built executable to `run_family_query.py`. Do not execute the
historical absolute command paths blindly: receipts, CMake caches and gprof
commands retain capture-host paths as provenance, not portable executable
instructions. This archive contains no distributable CSL binary or interpreter.

The primary 170 attempts include 168 completed independently verified runs and
two deliberate materialization-limit resource stops. The separate profiler has
40 additional independently verified runs; its gmon files and raw text are
preserved. Those runs never enter primary distributions. Profiler sampling
combines whole A/B command processes; it does not isolate verifier time or
establish a unique limiter. Native-clock on/off overhead remains a separate
issue #95 gate. Pages publication and installed-consumer/platform integration
are not claimed here.
