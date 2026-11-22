"""Compatibility entry point for the report-site module and command line."""

import report_site as _report_site

catalogue_index = _report_site.catalogue_index
register_publication_policies = _report_site.register_publication_policies

globals().update(
    {name: value for name, value in vars(_report_site).items() if not name.startswith("__")}
)

if __name__ == "__main__":
    raise SystemExit(_report_site.main())
