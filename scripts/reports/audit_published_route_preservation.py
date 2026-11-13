"""Compare a composed site with the pinned pre-migration public Pages artifact."""

import argparse
import hashlib
import json
import tarfile
from collections import Counter
from pathlib import Path

try:
    from scripts.reports.preserve_published_routes import SOURCE, digest, safe
except ModuleNotFoundError:
    from preserve_published_routes import SOURCE, digest, safe


ORDER_INSENSITIVE_RECEIPT_ROUTE = "pages-mpc11-environment.json"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonstandard_constant(value):
    raise ValueError(f"non-standard JSON constant: {value}")


def _canonical_json(value) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _receipt_inventory_reordered_only(expected: bytes, actual: bytes) -> bool:
    try:
        old = json.loads(
            expected,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonstandard_constant,
        )
        new = json.loads(
            actual,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonstandard_constant,
        )
        if (
            not isinstance(old, dict)
            or not isinstance(new, dict)
            or not isinstance(old.get("installed"), list)
            or not isinstance(new.get("installed"), list)
        ):
            return False
        old_rest = {key: value for key, value in old.items() if key != "installed"}
        new_rest = {key: value for key, value in new.items() if key != "installed"}
        if _canonical_json(old_rest) != _canonical_json(new_rest):
            return False
        return Counter(map(_canonical_json, old["installed"])) == Counter(
            map(_canonical_json, new["installed"])
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def audit(baseline: Path, site: Path) -> dict:
    manifest = json.loads((SOURCE / "manifest.json").read_text())
    with baseline.open("rb") as stream:
        if (
            hashlib.file_digest(stream, "sha256").hexdigest()
            != manifest["baseline"]["artifact_tar_sha256"]
        ):
            raise ValueError("baseline artifact differs from pinned public artifact")
    missing, changed, changed_zips = [], [], []
    reviewed_receipt_order_changes = {}
    order_only_receipts = manifest.get("order_insensitive_receipts_reviewed_separately", {})
    total = zip_count = 0
    with tarfile.open(baseline) as bundle:
        for member in bundle:
            if not member.isfile():
                continue
            route = safe(member.name.removeprefix("./")).as_posix()
            total += 1
            zip_count += route.endswith(".zip")
            path = site / route
            extracted = bundle.extractfile(member)
            if extracted is None:
                raise ValueError(f"could not read baseline route: {route}")
            expected_bytes = extracted.read()
            expected = digest(expected_bytes)
            if not path.is_file() or path.is_symlink():
                missing.append(route)
            else:
                actual_bytes = path.read_bytes()
                if digest(actual_bytes) != expected:
                    changed.append(route)
                    if (
                        route == ORDER_INSENSITIVE_RECEIPT_ROUTE
                        and route in order_only_receipts
                        and _receipt_inventory_reordered_only(expected_bytes, actual_bytes)
                    ):
                        reviewed_receipt_order_changes[route] = order_only_receipts[route]
            if route.endswith(".zip") and (route in missing or route in changed):
                changed_zips.append(route)
    mutable = manifest["mutable_routes_reviewed_separately"]
    reviewed_copies = manifest["mutable_copy_reviewed_sha256"]
    unexpected = [
        n
        for n in changed
        if n not in reviewed_receipt_order_changes
        and (
            n not in mutable
            or (n in reviewed_copies and digest((site / n).read_bytes()) != reviewed_copies[n])
        )
    ]
    return {
        "baseline_files": total,
        "baseline_zip_count": zip_count,
        "missing": missing,
        "changed_or_missing_zips": changed_zips,
        "unexpected_changed": unexpected,
        "reviewed_mutable_changes": {n: mutable[n] for n in changed if n in mutable},
        "reviewed_receipt_order_changes": reviewed_receipt_order_changes,
        "passed": not (missing or changed_zips or unexpected),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--site", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.baseline, args.site)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
