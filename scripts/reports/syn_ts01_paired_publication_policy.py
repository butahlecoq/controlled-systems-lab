"""Paired T-S01 staging policy, separate from its publisher source bytes."""
import syn_ts01_paired_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND, r"syn-ts01-paired-20261014-b7f1ac0", publisher,
    figure_name="performance.svg"))
