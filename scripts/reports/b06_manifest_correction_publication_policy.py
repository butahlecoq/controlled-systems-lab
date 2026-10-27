"""Staging policy for the immutable B06 manifest-correction companion."""
import b06_manifest_correction_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(
    publisher.KIND,
    publisher.SOURCE_PATTERN,
    publisher,
    svg_files=("terminal-projections.svg",),
    raw_json_link=False,
    csv_name="manifest-correction.json",
    trial_label="Correction record",
    figure_name="terminal-projections.svg",
    extra_links=(("Corrected scenario", "corrected-scenario.json"),),
))
