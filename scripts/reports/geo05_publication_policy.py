"""GEO-05 staging policy, separate from the publisher's ID-bound source bytes."""
import geo05_registered_reports as publisher
from publication_policy import PublicationPolicy, register


POLICY = register(PublicationPolicy(
    kind=publisher.KIND, source_pattern=r"geo05-[0-9a-f]{16}", publisher=publisher,
    csv_name="trials.csv"))
