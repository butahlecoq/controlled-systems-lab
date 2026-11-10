"""Strict supported native stream and subprocess evidence boundary."""
import hashlib
import json
import math

RK4_FIELDS={'abstol','controls_sha256','declared_times','diagnostics','elapsed_seconds','integration_receipts','method','missing_prerequisites','physical_states','provider','reltol','scaled_states','scenario_sha256','schema','status','times','witness_sha256'}
CVODES_FIELDS={'abstol','casadi_version','control_violation_physical','controls_sha256','elapsed_seconds','error','method','objective','physical_states','reltol','sampled_state_violation_physical','scaled_states','scenario_sha256','schema','status','times','witness_sha256'}
RK4_STATUSES={'complete','unavailable','invalid_input','numerical_failure','callback_failure','cancelled','resource_limit'}


def read_native_attempt(folder,receipt,*,status_key,time_key,extensions,method='rk4',wall_seconds=300):
    status=receipt[status_key];code=receipt['return_code'];elapsed=receipt[time_key]
    if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<0:raise ValueError('invalid native process duration')
    if status not in {'completed','failed','timed_out','invalid_output'}:raise ValueError('unsupported native process outcome')
    if status=='completed' and code!=0:raise ValueError('completed native process has nonzero return code')
    if status=='failed' and (code is None or code==0):raise ValueError('failed native process lacks nonzero return code')
    if status=='timed_out' and (code is not None or elapsed<wall_seconds-.5):raise ValueError('native timeout receipt contradicts return code/deadline')
    if status=='completed' and elapsed>wall_seconds+1:raise ValueError('completed native process exceeds declared deadline')
    for name,key in [('stdout.json','stdout_sha256'),('stderr.txt','stderr_sha256')]:
        if key in receipt and hashlib.sha256((folder/name).read_bytes()).hexdigest()!=receipt[key]:raise ValueError('native process stream hash mismatch')
    path=folder/'record.json'
    if status!='completed':
        if path.exists():raise ValueError('unsuccessful native process has an annotated success/prefix record')
        return None
    raw=json.loads((folder/'stdout.json').read_text());record=json.loads(path.read_text())
    fields=RK4_FIELDS if method=='rk4' else CVODES_FIELDS
    if not isinstance(raw,dict) or set(raw)!=fields:raise ValueError('native mandatory field set mismatch')
    schema='csl.mpc11.independent-replay/1' if method=='rk4' else 'csl.mpc11.nonlinear-execution/1'
    native_elapsed=raw['elapsed_seconds']
    if not isinstance(native_elapsed,(int,float)) or not math.isfinite(native_elapsed) or native_elapsed<0 or native_elapsed>elapsed+.1:raise ValueError('native elapsed time contradicts process receipt')
    if raw['schema']!=schema:raise ValueError('unsupported native stream schema')
    if method=='rk4':
        if raw['method']!='adaptive-rk4-step-doubling' or raw['provider']!='CSL::simulation' or raw['status'] not in RK4_STATUSES:raise ValueError('unsupported native replay provider/method/status')
    elif raw['method']!='cvodes' or raw['status'] not in {'complete','model-domain-error','integration-failure'}:raise ValueError('unsupported CVODES method/status')
    if set(record)!=fields|set(extensions) or {key:record[key] for key in fields}!=raw:raise ValueError('annotated record full native projection mismatch')
    return record
