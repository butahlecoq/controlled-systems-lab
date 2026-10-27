"""Validated issue #3 staging policy, separate from its publisher source bytes."""
import issue3_validated_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"issue3-validated-minimax-20261023-r1", publisher,
    native_digest=True))
