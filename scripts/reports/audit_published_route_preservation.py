"""Compare a composed site with the pinned pre-migration public Pages artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

try:
    from scripts.reports.preserve_published_routes import SOURCE, digest, safe
except ModuleNotFoundError:
    from preserve_published_routes import SOURCE, digest, safe


def audit(baseline: Path, site: Path) -> dict:
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    with baseline.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['baseline']['artifact_tar_sha256']:
            raise ValueError('baseline artifact differs from pinned public artifact')
    missing, changed, changed_zips = [], [], []
    total = zip_count = 0
    with tarfile.open(baseline) as bundle:
        for member in bundle:
            if not member.isfile():
                continue
            route = safe(member.name.removeprefix('./')).as_posix()
            total += 1
            zip_count += route.endswith('.zip')
            path = site / route
            expected = digest(bundle.extractfile(member).read())
            if not path.is_file() or path.is_symlink():
                missing.append(route)
            elif digest(path.read_bytes()) != expected:
                changed.append(route)
            if route.endswith('.zip') and (route in missing or route in changed):
                changed_zips.append(route)
    mutable = manifest['mutable_routes_reviewed_separately']
    unexpected = [n for n in changed if n not in mutable]
    return {'baseline_files': total, 'baseline_zip_count': zip_count,
            'missing': missing, 'changed_or_missing_zips': changed_zips,
            'unexpected_changed': unexpected,
            'reviewed_mutable_changes': {n: mutable[n] for n in changed if n in mutable},
            'passed': not (missing or changed_zips or unexpected)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.baseline, args.site)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
