"""Policies for report kinds sharing the legacy registered-record adapter."""
import registered_reports as publisher
from publication_policy import PublicationPolicy, register


POLICIES = (
    PublicationPolicy("opt05-hull", r"opt05-hull-\d{8}-[0-9a-f]{8}", publisher,
                      svg_files=("latency.svg",)),
    PublicationPolicy("opt06-basis-reuse", r"opt06-basis-reuse-\d{8}-[0-9a-f]{8}-r2", publisher,
                      svg_files=("latency.svg",), figure_name="latency.svg"),
    PublicationPolicy("geo03-hv", r"geo03-\d{8}-[0-9a-f]{12}", publisher,
                      svg_files=("latency.svg",)),
)
for policy in POLICIES:
    register(policy)
