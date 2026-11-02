"""Schema-v3 policy for the B04-C research dossier."""
import b04_c_exact_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy(publisher.KIND,
    r"b04-c-exact-dyadic-v1", publisher, native_digest=True,
    extra_page_files=("evidence-manifest.json",),
    raw_json_link=False, csv_name="record.json", trial_label="Exact record",
    figure_name="trajectory.svg"))
