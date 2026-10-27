"""SYN-04 T-S01 staging policy, separate from its publisher source bytes."""
import syn04_strategy_b_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND,
    r"syn04-strategy-b-ts01-\d{8}-[0-9a-f]{8,12}", publisher))
