"""Compare a composed site with the pinned pre-migration public Pages artifact."""

import argparse
import hashlib
import json
import tarfile
from collections import Counter
from html import escape
from pathlib import Path

try:
    from scripts.reports.preserve_published_routes import SOURCE, digest, safe
except ModuleNotFoundError:
    from preserve_published_routes import SOURCE, digest, safe


BOOK_MANIFEST = Path(__file__).resolve().parents[2] / "docs/catalogue/learning-book-v1.json"


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


def _learning_navigation_replacements(manifest: dict) -> dict:
    insertions = manifest.get("learning_navigation_insertions_reviewed_separately", [])
    if not insertions:
        return {}
    chapters = json.loads(BOOK_MANIFEST.read_text())["chapters"]
    replacements = {}

    def entry(chapter):
        return ('<li class="book-chapter"><span class="chapter-state">' +
                escape(chapter["status_label"]) + '</span> <a href="' +
                escape(chapter["id"] + '.html', quote=True) + '">' +
                escape(chapter["title"]) + '</a><p>' +
                escape(chapter["summary"]) + '</p></li>')

    def link(chapter, direction):
        label = "Previous" if direction == "prev" else "Next"
        return ('<a rel="' + direction + '" href="' +
                escape(chapter["id"] + '.html', quote=True) + '"><span>' + label +
                '</span><strong>' + escape(chapter["title"]) + '</strong></a>')

    inserted_ids = {item.get("chapter_id") for item in insertions}
    if len(inserted_ids) != len(insertions):
        return {}
    positions = {chapter["id"]: i for i, chapter in enumerate(chapters)}
    groups = {}
    for insertion in insertions:
        matches = [i for i, chapter in enumerate(chapters)
                   if chapter["id"] == insertion["chapter_id"]]
        if len(matches) != 1 or not 0 < matches[0] < len(chapters) - 1:
            continue
        index = matches[0]
        previous, chapter, following = chapters[index - 1:index + 2]
        if (digest(_canonical_json(chapter).encode()) != insertion["chapter_sha256"]
                or previous["id"] != insertion["previous_chapter_id"]
                or following["id"] != insertion["next_chapter_id"]):
            continue
        previous_base = next((chapters[j] for j in range(index - 1, -1, -1)
                              if chapters[j]["id"] not in inserted_ids), None)
        following_base = next((chapters[j] for j in range(index + 1, len(chapters))
                               if chapters[j]["id"] not in inserted_ids), None)
        if previous_base is None or following_base is None:
            continue
        groups.setdefault((previous_base["id"], following_base["id"]), []).append(chapter)
    for (previous_id, following_id), inserted in groups.items():
        previous = chapters[positions[previous_id]]
        following = chapters[positions[following_id]]
        inserted.sort(key=lambda item: positions[item["id"]])
        qualification = "; ".join(next(row["qualification"] for row in insertions
                                        if row["chapter_id"] == item["id"]) for item in inserted)
        changes = {
            "learn/index.html": (entry(previous), entry(previous) + "".join(entry(item) for item in inserted)),
            "learn/" + previous_id + ".html": (link(following, "next"), link(inserted[0], "next")),
            "learn/" + following_id + ".html": (link(previous, "prev"), link(inserted[-1], "prev")),
        }
        for route, (old, new) in changes.items():
            if route in replacements:
                raise ValueError("overlapping reviewed learning navigation insertions")
            replacements[route] = (old.encode(), new.encode(), qualification)
    return replacements


def _learning_navigation_only(route: str, expected: bytes, actual: bytes, replacement: tuple) -> bool:
    old, new, _ = replacement
    if expected.count(old) != 1:
        return False
    if route != "learn/index.html":
        opening = b'<nav class="lesson-neighbors" aria-label="Lesson navigation">'
        if expected.count(opening) != 1:
            return False
        start = expected.index(opening) + len(opening)
        end = expected.find(b'</nav>', start)
        if end < 0 or old not in expected[start:end]:
            return False
    return actual == expected.replace(old, new, 1)


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
    reviewed_learning_navigation_changes = {}
    learning_replacements = _learning_navigation_replacements(manifest)
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
                    if (route in learning_replacements and _learning_navigation_only(
                            route, expected_bytes, actual_bytes, learning_replacements[route])):
                        reviewed_learning_navigation_changes[route] = learning_replacements[route][2]
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
        and n not in reviewed_learning_navigation_changes
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
        "reviewed_learning_navigation_changes": reviewed_learning_navigation_changes,
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
