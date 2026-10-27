"""GEO-06 staging policy, separate from its publisher source bytes."""
import geo06_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"geo06-[0-9a-f]{16}", publisher,
    native_digest=True))
