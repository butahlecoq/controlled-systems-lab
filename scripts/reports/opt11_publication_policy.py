"""OPT-11 staging policy, separate from its publisher source bytes."""
import opt11_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"opt11-[0-9a-f]{16}", publisher,
    native_digest=True, svg_files=("latency.svg",), adapt_allow_test=True,
    render_allow_test=True, archive_allow_test=True))
