#!/usr/bin/env python3
"""Package saved evidence without placing large raw profiler files in Git."""
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    root=args.bundle.resolve(strict=True);output=args.output.resolve()
    if output.exists():parser.error('output must be new')
    paths=sorted(p for p in root.rglob('*') if p.is_file())
    for p in paths:
        if p.is_symlink() or not p.resolve().is_relative_to(root):parser.error('unsafe archive source path')
    output.mkdir(parents=True)
    with zipfile.ZipFile(output/'offline.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for p in paths:archive.write(p,p.relative_to(root).as_posix())
    with zipfile.ZipFile(output/'offline.zip') as archive:
        if archive.testzip() is not None:raise ValueError('archive CRC failure')
        if set(archive.namelist())!={p.relative_to(root).as_posix() for p in paths}:raise ValueError('archive inventory mismatch')
        for p in paths:
            if hashlib.sha256(archive.read(p.relative_to(root).as_posix())).digest()!=hashlib.sha256(p.read_bytes()).digest():raise ValueError('archive member hash mismatch')
    for p in paths:
        relative=p.relative_to(root)
        # The archive retains every raw attempt and gmon file. Reading assets
        # stay directly accessible beside it for browser and reviewer use.
        if relative.parts[0] in ('attempts','diagnostics') or relative.name.startswith('gmon.') or len(relative.parts)>2 and relative.parts[0]=='limiter-profile' or relative.name=='SHA256SUMS':continue
        target=output/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    page=(output/'index.html').read_text().replace('href="attempts/"','href="offline.zip"')
    page=page.replace('<h1>','<p>Download the <a href="offline.zip">complete offline ZIP</a> for every raw attempt, stopped probe, development diagnostic and profiler sample. Extract it to browse the original relative attempt links. Historical absolute paths in receipts and CMake caches describe the capture host; use REPRODUCE.md commands instead.</p><h1>',1)
    (output/'index.html').write_text(page)
    shutil.copy2(root/'SHA256SUMS',output/'archive-members.sha256')
    final=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output).as_posix()}\n' for p in final))
    print(f'Packaged {len(paths)} immutable members; offline ZIP { (output/"offline.zip").stat().st_size } bytes')

if __name__=='__main__':main()
