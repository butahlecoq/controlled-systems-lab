"""Publication policy for the immutable BTULSHOR comparison adapter."""
import btulshor_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(
    kind=publisher.KIND, source_pattern=publisher.SOURCE_PATTERN, publisher=publisher,
    native_digest=True, svg_files=("point-projections.svg",), include_parent_archive=True,
    raw_json_link=False, csv_name="raw/summary.json", trial_label="Comparison summary",
    figure_name="point-projections.svg",
    extra_links=(("Native offline ZIP", publisher.SOURCE_ID + ".zip"),)))
