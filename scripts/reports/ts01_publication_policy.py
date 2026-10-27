"""SYN-07 staging policy, separate from its publisher source bytes."""
import ts01_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND,
    r"syn07-ts01-\d{8}-[0-9a-f]{8,12}", publisher))
