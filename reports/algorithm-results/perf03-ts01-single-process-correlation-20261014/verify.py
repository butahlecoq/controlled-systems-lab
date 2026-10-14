import csv, json, pathlib, statistics
import hashlib
root=pathlib.Path(__file__).parent
summary=json.loads((root/'profile-summary.json').read_text(encoding='utf-8'))
rows=list(csv.DictReader((root/'paired-timings.csv').open(encoding='utf-8',newline='')))
assert len(rows)==30001, len(rows)
assert sum(r['warmup']=='true' for r in rows)==1
measured=[r for r in rows if r['warmup']=='false']
assert len(measured)==30000
assert all(r['unprofiled_status']==r['profiled_status']=='passed' for r in measured)
assert all(r['result_marker_equal']=='true' for r in rows)
for key,column in [('unprofiled','unprofiled_elapsed_ns'),('profiled','profiled_elapsed_ns')]:
    values=[int(r[column]) for r in measured]
    reported=summary['paired_execution'][key]['per_call']
    assert len(values)==reported['n']==30000
    assert statistics.median(values)==reported['median_ns']
    assert min(values)==reported['min_ns'] and max(values)==reported['max_ns']
page=(root/'index.html').read_text(encoding='utf-8')
for required in ('Timing result: inconclusive', 'Sampled CPU attribution', 'speedup', 'paired-timings.csv', 'profile-summary.json', 'Independent review'):
    assert required in page, required
assert 'https://' not in page and 'http://' not in page
manifest={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (root/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines()}
expected={p.name for p in root.iterdir() if p.is_file() and p.name!='SHA256SUMS.txt'}
assert set(manifest)==expected, (set(manifest),expected)
for name,digest in manifest.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest, name
profile=summary['profiler']['trace']
assert profile['lost_events']==0 and profile['target_process_stack_hits']==130813
assert summary['workload']['successes']==30000 and summary['workload']['failures']==0
print('PASS: matched run records, profile counters, static HTML evidence bounds and SHA-256 manifest agree.')
