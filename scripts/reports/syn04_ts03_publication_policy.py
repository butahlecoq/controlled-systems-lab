"""SYN-04 T-S03 staging policy, separate from its publisher source bytes."""
import syn04_ts03_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND,
    r"syn04-strategy-b-ts03-\d{8}-[0-9a-f]{8,12}", publisher))
