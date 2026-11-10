"""Check actual Strategy B build observations, independently of family evidence."""
NAMES=('strategy-b/joint-h-assembly','strategy-b/objective-lift','strategy-b/program-freeze')


def check_phases(record):
    if record['strategy']!='csl.synthesis.strategy-b':raise ValueError('Strategy B build observations required')
    if not record['instrumented']:
        if record.get('synthesis_timing') is not None:raise ValueError('disabled collection carries timing')
        return {'status':'unobserved','scope':'collector disabled; no phase timings inferred'}
    spans=record['synthesis_timing']['spans'];operations={}
    for span in spans:
        if span['operation'] in ('strategy-b/program-build',*NAMES):
            if span['operation'] in operations:raise ValueError('ambiguous build phase observation')
            operations[span['operation']]=span
    if not all(name in operations for name in ('strategy-b/program-build',*NAMES)):
        raise ValueError('split phases were not planned')
    parts=[operations[name] for name in NAMES];build=operations['strategy-b/program-build']
    if not all(span['completed'] for span in [build,*parts]):
        if record['termination']!='completed':
            return {'status':'unobserved-or-partial-build-stop','scope':'retain raw partial observations; no completed build inference'}
        raise ValueError('declared but uncalled build phases are not measurements')
    for span in [build,*parts]:
        if span['start_tick'] is None or span['end_tick'] is None or span['ticks']!=span['end_tick']-span['start_tick'] or span['ticks']<0:
            raise ValueError('invalid actual build clock interval')
    previous=build['start_tick']
    for span in parts:
        if span['parent']!=build['id'] or span['start_tick']<previous or span['end_tick']>build['end_tick']:
            raise ValueError('build phases must be nested, ordered and nonoverlapping')
        previous=span['end_tick']
    if any(span['termination']!='completed' for span in [build,*parts]):
        if record['termination']=='completed':raise ValueError('successful run contains failed build phase')
        return {'status':'observed-build-failure','scope':'raw failed build intervals retained; no mathematical completion inferred'}
    t=record['horizon'];width=2*t+1;nnz=5*t+1
    if t not in (2,4,8):raise ValueError('unsupported literal phase fixture')
    expected=((width,nnz),(1,width),(nnz,width))
    for span,(input_size,output_size) in zip(parts,expected):
        if span['input_size']!=input_size or span['output_size']!=output_size:
            raise ValueError('phase sizes differ from actual literal sparse/program dimensions')
    residual=build['ticks']-sum(span['ticks'] for span in parts)
    if residual<0:raise ValueError('negative build residual')
    return {'status':'observed' if record['termination']=='completed' else 'observed-build-with-later-stop',
        'build_ticks':build['ticks'],'joint_h_assembly_ticks':parts[0]['ticks'],
        'objective_lift_ticks':parts[1]['ticks'],'program_freeze_ticks':parts[2]['ticks'],
        'build_residual_ticks':residual,
        'residual_scope':'admission/capacity checks, identity/map/result construction, phase lookup/closure overhead and other gaps; not sparse assembly or isolated snapshot time',
        'size_scope':'assembly width->nonzeros; objective terminal-state dimension->joint dimension; program freeze nonzeros->program variables'}
