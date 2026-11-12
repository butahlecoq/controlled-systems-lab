"""Stage exact previously published scientific assets without rerunning builders."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

SOURCE = Path(__file__).resolve().parents[2] / 'reports/published-route-preservation'
MAX_ARCHIVE = 16 * 1024**2
MAX_EXPANDED = 64 * 1024**2


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or not path.parts or path.is_absolute() or path.as_posix() != name or
            '\\' in name or any(p in ('.', '..') for p in path.parts)):
        raise ValueError('unsafe preserved route: ' + name)
    return path


def checked(data: bytes, record: dict) -> bytes:
    if len(data) != record['size'] or digest(data) != record['sha256']:
        raise ValueError('preserved asset hash/size differs')
    return data


def regular(path: Path) -> bytes:
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('preserved source must be a regular file')
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('preserved source exceeds quota')
    return path.read_bytes()


def payloads(source: Path = SOURCE) -> dict[str, bytes]:
    if source.is_symlink() or not source.is_dir():
        raise ValueError('unsafe preservation source')
    manifest = json.loads(regular(source / 'manifest.json'))
    if manifest['schema'] != 'csl.published-route-preservation/1':
        raise ValueError('unsupported preservation manifest')
    result = {}
    for archive in manifest['archives']:
        name = safe(archive['path']).as_posix()
        if '/' in name or archive['size'] > MAX_ARCHIVE:
            raise ValueError('invalid preserved archive')
        data = checked(regular(source / name), archive)
        result[name] = data
        with zipfile.ZipFile(source / name) as bundle:
            entries = bundle.infolist()
            if (len(entries) != len(archive['members']) or len(entries) > 1024 or
                    len({i.filename for i in entries}) != len(entries) or
                    sum(i.file_size for i in entries) > MAX_EXPANDED):
                raise ValueError('preserved ZIP inventory/quota differs')
            for entry in entries:
                route = safe(entry.filename).as_posix()
                if (entry.is_dir() or entry.flag_bits & 1 or
                        stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG) or
                        entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError('unsafe preserved ZIP member')
                record = archive['members'][route]
                if entry.file_size != record['size']:
                    raise ValueError('preserved member size differs')
                content = checked(bundle.read(entry), record)  # Also checks ZIP CRC.
                if record['publish']:
                    if '.git' in safe(route).parts or not route.startswith(name[:-4] + '/'):
                        raise ValueError('invalid published member scope')
                    if route in result:
                        raise ValueError('duplicate preserved route')
                    result[route] = content
    for alias in manifest['aliases']:
        route = safe(alias['route']).as_posix()
        source_name = safe(alias['source']).as_posix()
        if '/' in source_name or route in result:
            raise ValueError('invalid preserved alias')
        result[route] = checked(regular(source / source_name), alias)
    return result


def destination(site: Path, route: str) -> Path:
    path = site
    for part in safe(route).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('symlink in preserved destination: ' + route)
        if path.exists() and path != site / route and not path.is_dir():
            raise ValueError('non-directory in preserved destination: ' + route)
    if path.exists() and not path.is_file():
        raise ValueError('non-file preserved destination: ' + route)
    return path


def stage(site: Path, source: Path = SOURCE) -> dict:
    site = Path(site)
    if any(p.is_symlink() for p in (site, *site.parents)) or not site.is_dir():
        raise ValueError('preservation needs an existing regular site directory')
    assets = payloads(source)
    manifest = json.loads(regular(source / 'manifest.json'))
    aliases = manifest['aliases']
    replacements = {a['route']: a.get('replaces_sha256') for a in aliases}
    # Validate the entire input and destination before changing any output.
    for route, data in assets.items():
        path = destination(site, route)
        if path.exists() and path.read_bytes() != data:
            if digest(path.read_bytes()) != replacements.get(route):
                raise ValueError('conflicting preserved route: ' + route)
    for route, data in assets.items():
        path = destination(site, route)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return {'preserved_routes': len(assets), 'preserved_top_level_zips': len(manifest['archives'])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.site), sort_keys=True))


if __name__ == '__main__':
    main()
