"""B08 exact-result staging policy, separate from its publisher source bytes."""
import b08_exact_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"b08-exact-[0-9a-f]{16}", publisher,
    native_digest=True))
