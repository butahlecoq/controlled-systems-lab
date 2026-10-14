import csv,hashlib,json,re,statistics,sys
from pathlib import Path

root=Path(sys.argv[1])
record=json.loads((root/'records.json').read_text(encoding='utf-8'))
point_counts={case['case_id']:case['points'] for case in record['fixtures']}
trials=record['trials']

def verify_manifest(directory):
    manifest=directory/'manifest.sha256'
    assert manifest.is_file(), f'missing manifest: {manifest}'
    expected={}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1)
        assert name not in expected, f'duplicate manifest entry: {name}'
        expected[name]=digest
    actual={p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() and p != manifest}
    if directory == root:
        actual -= {'bundle.zip','bundle.zip.sha256'}
    assert set(expected)==actual, f'manifest file inventory differs: {directory}'
    for name,digest in expected.items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest()==digest, f'manifest hash mismatch: {directory/name}'
    return len(actual)

def verify_chart(page):
    text=page.read_text(encoding='utf-8')
    assert 'viewBox="0 0 1000 310"' in text
    inline=re.search(r'<svg\b.*?</svg>',text)
    assert inline
    svg=inline.group(0)
    for x,width in re.findall(r'<rect x="(\d+)"[^>]*width="(\d+)"',svg):
        assert int(x)+int(width)<=1000, f'bar clipped in {page}'
    for x,label in re.findall(r'<text x="(\d+)"[^>]*>(.*?)</text>',svg):
        assert int(x)+len(label)*8<=1000, f'chart label may clip in {page}'

with (root/'trials.csv').open(encoding='utf-8',newline='') as stream:
    csv_rows=list(csv.DictReader(stream))
assert len(csv_rows)==len(trials)
for csv_row,row in zip(csv_rows,trials):
    assert int(csv_row['elapsed_ns'])==row['elapsed_ns']
    assert csv_row['case_id']==row['case_id'] and csv_row['method']==row['method']
    for field in ('verified','output_ids_valid','contains_all_inputs'):
        assert csv_row[field].lower()==str(row[field]).lower()
    count=point_counts[row['case_id']]
    ids=row['retained_points']
    assert row['status']=='complete' and row['verified'] is True
    assert row['output_ids_valid'] is True and row['contains_all_inputs'] is True
    assert ids and len(ids)==len(set(ids)) and all(type(i) is int and 0<=i<count for i in ids)
    assert row['retained']==len(ids)
raw=[json.loads(line) for line in (root/'raw-stdout.jsonl').read_text(encoding='utf-8').splitlines()]
assert raw==trials, 'raw stdout rows differ from records.json'
assert record['process']['rows']==len(trials)
assert record['process']['measured_rows']==sum(not x['warmup'] for x in trials)
assert record['process']['warmup_rows']==sum(x['warmup'] for x in trials)
assert record['process']['failures']==sum(x['failures'] for x in record['summary'])==0
assert record['code_commit'] and record['build']['executable_sha256'] and record['build']['harness_sha256']
interior=[x for x in trials if x['case_id']=='interior-basis' and not x['warmup']]
assert len(interior)==14
assert all(0 in x['basis_points'] for x in interior if x['method']=='basis-reuse')
assert all(x['status']=='complete' for x in interior if x['method']=='baseline')
assert all(0 in x['retained_points'] for x in interior if x['method']=='basis-reuse')
for group in record['summary']:
    measured=[x for x in trials if not x['warmup'] and x['case_id']==group['case_id'] and x['method']==group['method']]
    elapsed=[x['elapsed_ns'] for x in measured if x['status']=='complete' and x['verified']]
    assert len(measured)==group['successes'] and len(measured)+group['failures']==group['attempts']
    assert int(statistics.median(elapsed))==group['median_ns'] and min(elapsed)==group['min_ns'] and max(elapsed)==group['max_ns']
    for sf,tf in [('median_membership_lp_calls','lp_calls'),('median_basis_solves','basis_solves'),('median_pivots','pivots'),('median_degenerate_pivots','degenerate_pivots'),('median_bulk_candidates','bulk_candidates'),('median_bulk_removals','bulk_removals')]:
        assert group[sf]==statistics.median([x[tf] for x in measured])
with (root/'summary.csv').open(encoding='utf-8',newline='') as stream:
    summary_csv=list(csv.DictReader(stream))
assert len(summary_csv)==len(record['summary'])
for actual,expected in zip(summary_csv,record['summary']):
    for key,value in expected.items(): assert actual[key]==str(value), f'summary CSV mismatch at {key}'
assert record['complexity']['representation'] and record['complexity']['work'] and record['evaluation_plan']
verify_chart(root/'index.html')
if (root/'evidence'/'accepted-002'/'index.html').is_file():
    verify_chart(root/'evidence'/'accepted-002'/'index.html')
svg=(root/'latency.svg').read_text(encoding='utf-8')
assert 'viewBox="0 0 1000 310"' in svg
manifested=verify_manifest(root)
for nested in root.rglob('manifest.sha256'):
    if nested.parent!=root: verify_manifest(nested.parent)
bundle=(root/'bundle.zip').read_bytes()
bundle_hash=hashlib.sha256(bundle).hexdigest()
assert (root/'bundle.zip.sha256').read_text(encoding='ascii').strip()==f'{bundle_hash}  bundle.zip'
with __import__('zipfile').ZipFile(root/'bundle.zip') as archive:
    names=archive.namelist()
    expected={f'{root.name}/{p.relative_to(root).as_posix()}' for p in root.rglob('*') if p.is_file() and p.name not in {'bundle.zip','bundle.zip.sha256'}}
    assert len(names)==len(set(names)) and set(names)==expected and archive.testzip() is None
    for name in expected:
        relative=name[len(root.name)+1:]
        assert archive.read(name)==(root/relative).read_bytes(), f'bundle content mismatch: {relative}'
print(f'validated {len(trials)} raw trial rows, original-point and ID invariants, {len(record["summary"])} summary groups, unclipped chart(s), and {manifested} manifest-listed files without rewriting manifests')
