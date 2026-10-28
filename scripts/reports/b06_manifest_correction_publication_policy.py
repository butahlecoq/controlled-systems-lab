"""Staging policy for the immutable B06 manifest-correction companion."""
import b06_manifest_correction_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(
    publisher.KIND,
    publisher.SOURCE_PATTERN,
    publisher,
    svg_files=("terminal-projections.svg",),
    extra_page_files=(
        f"../{publisher.SOURCE_ID}.zip",
        "measured-source/b06_finite_minimax.cpp",
        "measured-source/b06_exact_oracle.cpp",
        "terminal-projections.svg", "example-2d.html", "scenario.json",
        "raw-runs.jsonl", "exact-oracle.json", "geometry.json", "capture.json",
        "environment.txt",
    ),
    raw_json_link=False,
    csv_name="manifest-correction.json",
    trial_label="Correction record",
    figure_name="terminal-projections.svg",
    extra_links=(("Corrected scenario", "corrected-scenario.json"),
                 ("Measured driver source", "measured-source/b06_finite_minimax.cpp"),
                 ("Exact oracle source", "measured-source/b06_exact_oracle.cpp")),
))
