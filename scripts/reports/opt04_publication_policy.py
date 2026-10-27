"""OPT-04 staging policy, separate from the publisher's ID-bound source bytes."""
import opt04_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, publisher.SOURCE_PATTERN, publisher,
    native_digest=True, generated_svg=True, include_source_evidence=True, adapt_allow_test=True,
    csv_name="stdout.jsonl", trial_label="Trial log", figure_name="performance.svg"))
