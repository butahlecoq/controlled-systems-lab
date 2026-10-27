"""SYN-03 T-S01 staging policy, separate from its publisher source bytes."""
import syn03_strategy_a_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND,
    r"syn03-strategy-a-ts01-\d{8}-[0-9a-f]{8,12}", publisher))
