"""Staging policy for the immutable B06 manifest-correction companion."""
import b06_manifest_correction_registered_reports as publisher
from publication_policy import PublicationPolicy, register

SOURCE_REPORT = "issue6-b06-reference-761bdc6e40b93814f873f105313d1eed4f63711653aa583a16a2ddfbc67c2a82"

POLICY = register(PublicationPolicy(
    publisher.KIND,
    publisher.SOURCE_PATTERN,
    publisher,
    svg_files=("terminal-projections.svg",),
    include_parent_archive=True,
    extra_page_files=(
        f"../{SOURCE_REPORT}/index.html",
        f"../{SOURCE_REPORT}.zip",
        f"../{SOURCE_REPORT}/raw-runs.jsonl",
        f"../{SOURCE_REPORT}/exact-oracle.json",
    ),
    raw_json_link=False,
    csv_name="manifest-correction.json",
    trial_label="Correction record",
    figure_name="terminal-projections.svg",
    extra_links=(("Corrected scenario", "corrected-scenario.json"),),
))
