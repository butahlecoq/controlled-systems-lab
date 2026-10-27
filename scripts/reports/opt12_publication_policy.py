"""OPT-12 staging policy, separate from its publisher source bytes."""
import opt12_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, publisher.SOURCE_PATTERN, publisher,
    native_digest=True, include_parent_archive=True))
