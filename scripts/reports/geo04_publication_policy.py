"""GEO-04 staging policy, separate from the publisher's ID-bound source bytes."""
import geo04_registered_reports as publisher
from publication_policy import PublicationPolicy, register


POLICY = register(PublicationPolicy(
    kind="geo04-intersection",
    source_pattern=r"geo04-\d{8}T\d{6}Z-[0-9a-f]{12}",
    publisher=publisher,
    csv_name="raw-driver-output.csv"))
