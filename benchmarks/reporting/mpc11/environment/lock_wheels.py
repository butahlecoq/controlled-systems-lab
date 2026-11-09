#!/usr/bin/env python3
"""Bind an optional Linux wheel download to publisher hashes and license files."""
from __future__ import annotations
import argparse
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheels', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    artifacts, requirements, notices = [], [], []
    notice_archive = zipfile.ZipFile(args.output / "notices.zip", "w", compression=zipfile.ZIP_DEFLATED)
    for wheel in sorted(args.wheels.glob('*.whl')):
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        with zipfile.ZipFile(wheel) as archive:
            if any('acados' in name.lower() for name in archive.namelist()):
                raise ValueError('Excluded acados content in optional wheel')
            metadata_name = next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
            name, version = metadata['Name'], metadata['Version']
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json') as stream:
                publisher = json.load(stream)
            record = next(r for r in publisher['urls'] if r['filename'] == wheel.name)
            if record['digests']['sha256'] != digest:
                raise ValueError(f'Publisher hash mismatch: {wheel.name}')
            artifacts.append({'name': name, 'version': version, 'filename': wheel.name,
                'sha256': digest, 'publisher_url': record['url'],
                'metadata_license': str(metadata.get('License-Expression') or metadata.get('License') or ''),
                'requires_dist': [str(item) for item in metadata.get_all('Requires-Dist', [])]})
            requirements.append(f'{name}=={version} --hash=sha256:{digest}')
            for entry in archive.namelist():
                leaf = Path(entry).name.lower()
                if not entry.endswith('/') and (any(token in leaf for token in ['license', 'copying', 'notice', 'cecill', 'copyright']) or '/licenses/' in entry):
                    data = archive.read(entry)
                    target = args.output / 'notices' / wheel.stem / entry
                    if '..' in Path(entry).parts or Path(entry).is_absolute():
                        raise ValueError('Unsafe wheel notice path')
                    notice_archive.writestr(str(target.relative_to(args.output)), data)
                    notices.append({'wheel': wheel.name, 'member': entry,
                        'saved_path': str(target.relative_to(args.output)),
                        'sha256': hashlib.sha256(data).hexdigest()})
    notice_archive.close()
    if not artifacts:
        raise ValueError('No wheels found')
    (args.output/'requirements-linux-cp311.lock').write_text('\n'.join(requirements)+'\n')
    (args.output/'wheel-manifest.json').write_text(json.dumps({'schema':'csl.mpc11.optional-wheels/1',
        'platform':'Linux x86-64 CPython 3.11; exact wheel tags are authoritative',
        'artifacts':artifacts,'notice_archive':'notices.zip','license_notices':notices},indent=2)+'\n')
    print(json.dumps({'wheels':len(artifacts),'notices':len(notices)}))


if __name__ == '__main__':
    main()
