"""GEO-02 staging policy, separate from its publisher source bytes."""
import geo02_registered_reports as publisher
from publication_policy import PublicationPolicy, register

POLICY = register(PublicationPolicy("geo02-affine-sum", r"geo02-\d{8}T\d{6}Z-[0-9a-f]{12}", publisher,
    csv_name="raw-driver-output.csv", svg_files=("timings.svg",)))
