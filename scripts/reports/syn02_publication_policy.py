"""SYN-02 staging policy, separate from its publisher source bytes."""
import syn02_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND,
    r"syn02-terminal-\d{8}-[0-9a-f]{8}-[0-9a-f]{12}", publisher,
    svg_files=("latency.svg",)))
