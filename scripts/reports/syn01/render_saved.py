"""Render a validated SYN-01 record without invoking the numerical driver."""
import argparse
import json
from pathlib import Path

import report


def render(records_path, out_dir):
    record = json.loads(Path(records_path).read_text(encoding="utf-8"))
    errors = report.validate_record(record)
    if errors:
        raise ValueError("invalid saved SYN-01 record: " + ", ".join(errors))
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=False)
    (output / "index.html").write_text(report.render_html(record), encoding="utf-8", newline="\n")
    (output / "latency.svg").write_text(report.render_svg(record), encoding="utf-8", newline="\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("records", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    render(args.records, args.out)


if __name__ == "__main__":
    main()
