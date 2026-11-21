"""Compatibility entry point for the report-site module and command line."""

import report_site as _report_site

globals().update(
    {name: value for name, value in vars(_report_site).items() if not name.startswith("__")}
)

if __name__ == "__main__":
    raise SystemExit(_report_site.main())
