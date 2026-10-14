import csv,hashlib,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]); d=json.loads((root/'records.json').read_text()); rows=list(csv.DictReader((root/'trials.csv').open(encoding='utf-8')))
assert len(rows)==len(d['trials'])
for a,b in zip(rows,d['trials']):
    assert int(a['elapsed_ns'])==b['elapsed_ns'] and a['case_id']==b['case_id'] and a['method']==b['method']
    assert a['verified'].lower()==str(b['verified']).lower()
    assert b['status']=='complete' and b['verified'] is True, f"incomplete or unverified timed output: {b}"
assert d['process']['failures']==sum(x['failures'] for x in d['summary'])
assert d['code_commit'] and d['build']['executable_sha256']
assert d['process']['rows']==len(d['trials'])
assert d['process']['measured_rows']==sum(not x['warmup'] for x in d['trials'])
assert d['process']['warmup_rows']==sum(x['warmup'] for x in d['trials'])
interior=[x for x in d['trials'] if x['case_id']=='interior-basis' and not x['warmup']]
assert len(interior)==14
assert all(0 in x['basis_points'] for x in interior if x['method']=='basis-reuse')
assert all(x['status']=='complete' for x in interior if x['method']=='baseline')
assert all(0 in x['retained_points'] for x in interior if x['method']=='basis-reuse')
for group in d['summary']:
    measured=[x for x in d['trials'] if not x['warmup'] and x['case_id']==group['case_id'] and x['method']==group['method'] and x['status']=='complete' and x['verified']]
    elapsed=[x['elapsed_ns'] for x in measured]
    assert len(measured)==group['successes'] and (len(measured)+group['failures'])==group['attempts']
    assert int(statistics.median(elapsed))==group['median_ns'] and min(elapsed)==group['min_ns'] and max(elapsed)==group['max_ns']
assert all(b'"verified":true' in line for line in (root/'raw-stdout.jsonl').read_bytes().splitlines())
html=(root/'index.html').read_text(encoding='utf-8'); assert d['code_commit'] in html
files=sorted(x for x in root.rglob('*') if x.is_file() and x.name!='manifest.sha256')
(root/'manifest.sha256').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.relative_to(root).as_posix()+'\n' for f in files),encoding='utf-8')
for line in (root/'manifest.sha256').read_text().splitlines():
    h,n=line.split('  ',1); assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h
print(f'validated {len(rows)} trial records and {len(files)} manifested files')
