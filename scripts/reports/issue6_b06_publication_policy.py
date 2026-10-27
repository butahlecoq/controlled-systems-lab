"""B06 staging policy, separate from its publisher source bytes."""
import issue6_b06_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, publisher.SOURCE_PATTERN, publisher,
    native_digest=True, svg_files=("terminal-projections.svg",),
    extra_html_files=("example-2d.html",), include_parent_archive=True,
    figure_name="terminal-projections.svg"))
