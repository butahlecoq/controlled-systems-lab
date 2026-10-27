"""Issue #3 staging policy, separate from its publisher source bytes."""
import issue3_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"issue3-finite-catalogue-[0-9a-f]{16}", publisher,
    native_digest=True, svg_files=("latency.svg",), committed_archive=True))
