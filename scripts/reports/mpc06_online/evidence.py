"""Checked-source boundary shared by MPC-06 replay and rendering.

A checksum inventory detects changed bytes. Raw/structured correspondence is a
separate check: every retained APP-04 and QP response must be the actual parsed
native response in its repetition and program order.
"""
import hashlib
import json
from pathlib import Path,PurePosixPath
import re
from fractions import Fraction as Q

TOOLS=('check.py','evidence.py','model.py','study.py','render.py')
REVIEWED_REPORT_ID='mpc06-online-anchor-portable-v3'
REVIEWED_SOURCE_ID='mpc06-online-anchor-v1'
REVIEWED_REPORT_MANIFEST_SHA256='8edb28e2744b1b061a47971e5f0613c30be64e7c25727c70bd1ec52d4244034a'


def digest(data):return hashlib.sha256(data).hexdigest()


def json_value(data):
    def reject(value):raise ValueError('nonfinite JSON number: '+value)
    return json.loads(data,parse_constant=reject)


def files(bundle):
    if bundle.is_symlink() or not bundle.is_dir():raise ValueError('invalid source bundle')
    result={}
    for path in sorted(bundle.rglob('*')):
        if path.is_symlink():raise ValueError('source bundle contains symlink')
        if path.is_file():result[path.relative_to(bundle).as_posix()]=path.read_bytes()
    return result


def load_sources(bundle):
    """Validate complete inventory, scenario/source bytes and extraction."""
    contents=files(bundle);manifest={}
    for line in contents['SHA256SUMS'].decode().splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not match:raise ValueError('invalid source checksum entry')
        name=match[2];path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or name in manifest:raise ValueError('invalid source checksum path')
        manifest[name]=match[1]
    actual={name:digest(data) for name,data in contents.items() if name!='SHA256SUMS'}
    if manifest!=actual:raise ValueError('source inventory/checksum mismatch')
    record=json_value(contents['result.json'])
    if digest(contents['base-scenario.json'])!=record['base_scenario_sha256']:raise ValueError('base scenario binding mismatch')
    scenario=json_value(contents['base-scenario.json']);plant=record['plant']
    dynamics=scenario['dynamics'];constraints=scenario['constraints']
    if any(dynamics[key]!=plant[key] for key in ('A','B','E')) or scenario['feedback']['K']!=[record['policy']['gain']]:
        raise ValueError('base scenario/model binding mismatch')
    if list(map(Q,dynamics['disturbance_set']['bounds']))!=list(map(Q,plant['W'])) or constraints['state_box']!=plant['X'] or constraints['input_interval']!=plant['U']:
        raise ValueError('base scenario/constraint binding mismatch')
    for source,expected in record['source_file_sha256'].items():
        snapshot='source/'+PurePosixPath(source).name
        if snapshot not in contents or digest(contents[snapshot])!=expected:raise ValueError('capture source snapshot binding mismatch: '+source)
    processes={}
    for process in record['processes']:
        repetition=process['repetition']
        if type(repetition) is not int or repetition<0 or repetition in processes:raise ValueError('duplicate/invalid native repetition')
        processes[repetition]=process
    if set(processes)!=set(range(record['repetitions'])):raise ValueError('native repetition inventory mismatch')
    expected_streams={f'repetition-{i:02}/stdout.txt' for i in processes}
    if {name for name in contents if re.fullmatch(r'repetition-[0-9]+/stdout.txt',name)}!=expected_streams:
        raise ValueError('native response stream inventory mismatch')
    if any(a['repetition'] not in processes for a in record['attempts']):raise ValueError('attempt has no native process')
    for repetition,process in processes.items():
        name=f'repetition-{repetition:02}/stdout.txt'
        lines=contents[name].decode().splitlines()
        if process.get('status')=='inconclusive':
            # Partial streams stay bound as bytes and cannot yield verified status.
            continue
        try:responses=[json_value(line) for line in lines]
        except (ValueError,UnicodeError) as error:raise ValueError('invalid native response stream') from error
        expected=[process['approximation']]
        expected.extend(step['native'] for attempt in record['attempts'] if attempt['repetition']==repetition for step in attempt['steps'] if 'native' in step)
        if responses!=expected:raise ValueError('native response stream differs from structured outcomes')
        if not responses or responses[0].get('schema')!='csl.mpc06-online-approximation/1':raise ValueError('missing native APP-04 response')
        for index,response in enumerate(responses[1:]):
            if response.get('schema')!='csl.mpc06-online-qp/1' or response.get('program')!='nominal-qp/'+str(index):
                raise ValueError('native response program/order mismatch')
    for process in record['processes']:
        if process.get('status')=='inconclusive':continue
        offline=process['approximation']['construction_ns']
        if type(offline) is not int or offline<0 or offline>process['process_startup_and_offline_wall_ns']:
            raise ValueError('native offline timing exceeds observed process interval')
    for attempt in record['attempts']:
        for step in attempt['steps']:
            if 'native' not in step or step['native'].get('status')!='completed':continue
            native=step['native']
            for key in ('prepare_ns','setup_ns','solve_ns'):
                if type(native[key]) is not int or native[key]<0:raise ValueError('invalid native timing')
            for key in ('native_roundtrip_ns','exact_construction_ns','checker_ns'):
                if type(step[key]) is not int or step[key]<0:raise ValueError('invalid recorded timing')
            if sum(native[key] for key in ('prepare_ns','setup_ns','solve_ns'))>step['native_roundtrip_ns']:
                raise ValueError('native timing exceeds observed response interval')
    return record,{name:digest(data) for name,data in contents.items()}


def tool_bindings():
    directory=Path(__file__).resolve().parent
    return {name:digest((directory/name).read_bytes()) for name in TOOLS}


def reviewed_report_manifest(report,manifest_path):
    manifest_bytes=manifest_path.read_bytes()
    if digest(manifest_bytes)!=REVIEWED_REPORT_MANIFEST_SHA256:
        raise ValueError('reviewed report manifest binding mismatch')
    manifest={}
    for line in manifest_bytes.decode('ascii').splitlines():
        match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
        if not match or match[2] in manifest:raise ValueError('invalid reviewed report manifest')
        manifest[match[2]]=match[1]
    actual={}
    for path in report.rglob('*'):
        if path.is_symlink():raise ValueError('reviewed report contains a symlink')
        if path.is_file() and path!=manifest_path:
            actual[path.relative_to(report).as_posix()]=digest(path.read_bytes())
    if actual!=manifest:raise ValueError('reviewed report files differ from its pinned manifest')
    return manifest


def captured_tool_bindings(receipt_path,source_report_id):
    """Return the producer bindings captured with an immutable report bundle."""
    report=Path(receipt_path).resolve().parent
    snapshot=report/'review-tools'
    if not snapshot.exists():
        if report.name==REVIEWED_REPORT_ID:
            raise ValueError('reviewed report checker snapshot is missing')
        return tool_bindings()
    if snapshot.is_symlink() or not snapshot.is_dir():raise ValueError('invalid captured review-tool snapshot')
    manifest_path=report/'SHA256SUMS'
    if manifest_path.is_symlink() or not manifest_path.is_file():raise ValueError('missing captured report manifest')
    pinned_reviewed_report=digest(manifest_path.read_bytes())==REVIEWED_REPORT_MANIFEST_SHA256
    if report.name==REVIEWED_REPORT_ID:
        if not pinned_reviewed_report:
            raise ValueError('reviewed report manifest binding mismatch')
    if pinned_reviewed_report:
        if source_report_id!=REVIEWED_SOURCE_ID:
            raise ValueError('reviewed report source identity mismatch')
        manifest=reviewed_report_manifest(report,manifest_path)
    else:
        manifest={}
        for line in manifest_path.read_text(encoding='ascii').splitlines():
            match=re.fullmatch(r'([0-9a-f]{64})  (.+)',line)
            if not match:raise ValueError('invalid captured report checksum entry')
            manifest[match[2]]=match[1]
    bindings={name:digest((snapshot/name).read_bytes()) for name in TOOLS}
    if any(manifest.get(f'review-tools/{name}')!=value for name,value in bindings.items()):
        raise ValueError('captured review-tool snapshot differs from its report manifest')
    if not pinned_reviewed_report and bindings!=tool_bindings():
        raise ValueError('new report checker snapshot differs from current sources')
    return bindings


def receipt_id(receipt):
    payload={key:value for key,value in receipt.items() if key!='receipt_sha256'}
    return digest(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


def make_receipt(bundle,inputs,verification):
    receipt=dict(schema='csl.mpc06-online-verification/2',source_report_id=bundle.name,
        inputs=inputs,checked_sources=tool_bindings(),verification=verification)
    receipt['receipt_sha256']=receipt_id(receipt)
    return receipt


def checked_sources(bundle,receipt_path):
    """Only this boundary admits saved records to the renderer."""
    record,inputs=load_sources(bundle)
    receipt=json_value(receipt_path.read_bytes())
    if receipt.get('schema')!='csl.mpc06-online-verification/2' or receipt.get('source_report_id')!=bundle.name:
        raise ValueError('missing versioned checked-source receipt')
    if receipt.get('receipt_sha256')!=receipt_id(receipt):raise ValueError('verification receipt content binding mismatch')
    if receipt.get('inputs')!=inputs:raise ValueError('verification receipt input binding mismatch')
    if receipt.get('checked_sources')!=captured_tool_bindings(receipt_path,receipt.get('source_report_id')):raise ValueError('verification receipt script binding mismatch')
    if receipt['verification']['status'] not in ('verified','inconclusive'):raise ValueError('missing independent check disposition')
    expected_count=sum(len(attempt['steps']) for attempt in record['attempts'] if attempt['status']=='completed')
    expected_status='inconclusive' if any(p.get('status')=='inconclusive' for p in record['processes']) or any(a['status']!='completed' for a in record['attempts']) else 'verified'
    if receipt['verification']['completed_native_qps']!=expected_count or receipt['verification']['status']!=expected_status:
        raise ValueError('verification receipt disposition binding mismatch')
    return record,receipt
