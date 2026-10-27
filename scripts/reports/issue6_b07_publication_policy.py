"""B07 staging policy, separate from its publisher source bytes."""
import issue6_b07_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, publisher.SOURCE_PATTERN, publisher,
    native_digest=True, svg_files=("projections.svg",), include_parent_archive=True,
    committed_archive=True, raw_json_link=False, csv_name="results.jsonl",
    trial_label="Run records", figure_name="projections.svg"))
