"""Publication policy declaration kept outside B09's identity-bound adapter."""
import issue6_b09_registered_reports as publisher
from publication_policy import PublicationPolicy, register


POLICY = register(PublicationPolicy(
    kind=publisher.KIND, source_pattern=publisher.SOURCE_PATTERN, publisher=publisher,
    native_digest=True, svg_files=("projections-lambda0.svg", "projections-lambda1.svg"),
    include_parent_archive=True, committed_archive=True,
    csv_name="raw-runs.jsonl", trial_label="Raw timing rows",
    figure_name="projections-lambda0.svg"))
