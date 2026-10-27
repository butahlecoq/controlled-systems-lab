"""EXT-03 staging policy, separate from its publisher source bytes."""
import ext03_transform.registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"ext03-transform-20261024-a3a3af9", publisher,
    svg_files=("visual.svg",), figure_name="visual.svg"))
