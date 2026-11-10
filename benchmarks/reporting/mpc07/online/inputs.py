"""Select immutable measured-repetition0 policies after the existing exact checks."""
import hashlib
from collections import Counter
import json
from scripts.reports import stage_mpc07_comparison as upstream


def encoded(value):return (json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+'\n').encode()
def digest(data):return hashlib.sha256(data).hexdigest()


def select():
    files,_,summary=upstream.validate()
    profiles=[];unavailable=[]
    for source,label in ((upstream.FIXED_CURRENT,'fixed'),(upstream.JOINT_CURRENT,'joint')):
        records=json.loads(files[source]['current-rechecks.json'])
        for row in records:
            receipt=row['receipt']
            if 'purpose' in receipt or receipt['repetition']!=0:continue
            checked=row['current_check'];n=receipt['horizon'];kind=receipt['policy_class']
            sigma=receipt.get('sigma');encoding='past-eta' if label=='fixed' else 'past-zeta'
            if checked['status'] not in ('verified-rational-reconstruction','verified-joint-rational-policy'):
                unavailable.append(dict(source_folder=source,source_path=row['path'],status=checked['status'],source_record_sha256=digest(encoded(row))))
                continue
            identity=f'{label}-T{n}-'+(str(sigma).replace('/','over')+'-' if sigma else '')+kind
            profiles.append(dict(id=identity,source_folder=source,source_record_sha256=digest(encoded(row)),source_sidecar_sha256=digest(files[source]['current-rechecks.json']),source_path=row['path'],horizon=n,policy_class=kind,encoding=encoding,epsilon='0' if sigma=='1' else '1/64',sigma=sigma,policy=checked))
    profiles.sort(key=lambda p:p['id'])
    if not profiles or len({p['id'] for p in profiles})!=len(profiles):raise ValueError('selected source profile inventory')
    return dict(schema='csl.mpc07.online-inputs/1',upstream_anchors=upstream.ANCHORS,upstream_checked_outcomes=summary['attempts'],profiles=profiles,unavailable_profiles=unavailable,profile_counts=dict(Counter(p['encoding'] for p in profiles)),trace_families=['positive','alternating'],warmup_repetitions=1,measured_repetitions=5,
        trace_definition='delta=epsilon constant in both families; w=+1 or w=(-1)^stage; controller never receives either',model=dict(initial=['0','0'],position_update='p+q+u/2',velocity_update='(1+delta)*q+u+w',state_bounds=['64','16'],control_bound='1',cost='terminal q^2'),tolerance=dict(absolute=1e-10,relative=1e-10),
        scope='causal binary64 evaluation of existing rational policies; no LP solve or MPC reoptimization; two physical sample traces do not prove robustness')


if __name__=='__main__':
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('new output required')
    a.output.write_bytes(encoded(select()))
