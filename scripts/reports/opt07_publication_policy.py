"""OPT-07 staging policy, separate from its publisher source bytes."""
import opt07_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"opt07-[0-9a-f]{16}", publisher,
    native_digest=True, svg_files=("latency.svg",), figure_name="latency.svg"))
