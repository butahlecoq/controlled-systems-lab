#!/usr/bin/env python3
"""Check complete authored MPC-11 inputs without installing a solver."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def validate(value: dict) -> str:
    if value['schema'] != 'csl.mpc11.scenario/1':
        raise ValueError('unsupported scenario schema')
    if value['case_id'] not in {'SYN-NL-LV-01', 'SYN-NL-FUEL-01'}:
        raise ValueError('unknown authored case')
    required = {'equations', 'parameters', 'execution', 'independent_replay', 'affine', 'nmpc', 'objective', 'initial_guess', 'time', 'states', 'controls', 'hold'}
    if not required <= value.keys():
        raise ValueError('incomplete authored scenario configuration')
    states, controls = value['states'], value['controls']
    names = [item['name'] for item in states + controls]
    if len(set(names)) != len(names):
        raise ValueError('state/control names must be unique')
    for item in states + controls:
        lo, hi = item['physical_bounds']
        if not item['unit'] or not math.isfinite(lo) or not math.isfinite(hi) or lo > hi:
            raise ValueError('invalid unit or physical bounds')
    for state in states:
        if not math.isfinite(state['scale']) or state['scale'] <= 0:
            raise ValueError('state scale must be positive and finite')
        lo, hi = state['physical_bounds']
        if not lo <= state['initial'] <= hi:
            raise ValueError('initial state violates physical bounds')
    time = value['time']
    n, dt = time['intervals'], time['dt']
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0 or dt <= 0:
        raise ValueError('invalid physical time grid')
    if len(time['grid']) != n + 1 or any(abs(t - k * dt) > 1e-12 for k, t in enumerate(time['grid'])):
        raise ValueError('grid differs from physical interval schedule')
    if abs(time['final'] - n * dt) > 1e-12:
        raise ValueError('terminal time mismatch')
    expected_grid = (40, .5, 20, 's') if value['case_id'] == 'SYN-NL-FUEL-01' else (30, .1, 3, 'day')
    if (n, dt, time['final'], time['unit']) != expected_grid:
        raise ValueError('physical grid differs from named authored case')
    obj = value['objective']
    for key in ['terminal_target', 'terminal_scale', 'terminal_weights']:
        if len(obj[key]) != len(states):
            raise ValueError('terminal objective dimension mismatch')
    if any(not math.isfinite(x) for key in ['terminal_target', 'terminal_scale', 'terminal_weights', 'running_scale'] for x in obj[key]):
        raise ValueError('objective vectors must be finite')
    if any(x < 0 for x in obj['terminal_weights']) or not math.isfinite(obj['running_weight']) or obj['running_weight'] < 0:
        raise ValueError('objective weights must be finite and nonnegative')
    if any(x <= 0 for x in obj['terminal_scale'] + obj['running_scale']):
        raise ValueError('objective scale must be positive')
    if len(obj['running_scale']) != len(controls):
        raise ValueError('running objective dimension mismatch')
    if value['hold'] != 'zero-order' or value['nmpc']['horizon'] != 'shrinking-to-fixed-terminal':
        raise ValueError('unsupported horizon or hold convention')
    if value['nmpc']['running_cost_denominator'] != 'original-interval-count':
        raise ValueError('shrinking horizon must retain original objective denominator')
    if value['nmpc']['affine_trust_region'] or value['nmpc']['failure'] != 'stop-before-next-input-no-fallback':
        raise ValueError('unsupported controller configuration')
    affine = value['affine']
    if len(affine['trust_state_absolute']) != len(states) or len(affine['trust_input_absolute']) != len(controls):
        raise ValueError('trust-region dimension mismatch')
    if any(not math.isfinite(x) or x <= 0 for x in affine['trust_state_absolute'] + affine['trust_input_absolute']):
        raise ValueError('trust bounds must be finite and positive')
    if value['case_id'] == 'SYN-NL-FUEL-01':
        if names != ['m_ox', 'm_f', 'q_ox', 'q_f', 'u_ox', 'u_f']:
            raise ValueError('fuel coordinate order mismatch')
        if affine['reference_domain'] != [0, time['final']]:
            raise ValueError('fuel reference must cover exactly the fixed horizon')
        if affine['state_reference'] != ['100-2*t', '30-.6*t', '2', '.6'] or affine['input_reference'] != ['2/(3*sqrt((100-2*t)/100))', '.6/sqrt((30-.6*t)/30)']:
            raise ValueError('unsupported authored fuel reference')
        params = {name: item['value'] for name, item in value['parameters'].items()}
        for k in range(n):
            t = (k + .5) * dt
            commands = [2 / (params['Q_ox'] * math.sqrt((100 - 2*t) / params['m_ox0'])), .6 / (params['Q_f'] * math.sqrt((30 - .6*t) / params['m_f0']))]
            if any(not bound[0] <= u <= bound[1] for u, bound in zip(commands, [c['physical_bounds'] for c in controls])):
                raise ValueError('fuel nominal command exceeds actuator limits')
        expected = {'Q_ox': 3, 'Q_f': 1, 'tau_ox': 2, 'tau_f': 2, 'm_ox0': 100, 'm_f0': 30}
        if params != expected:
            raise ValueError('fuel parameters differ from fixed authored reference')
    else:
        p = {name: data['value'] for name, data in value['parameters'].items()}
        if [p['c']/p['d'], p['a']/p['b']] != affine['state_reference']:
            raise ValueError('LV coexistence reference mismatch')
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    # These IDs name fixed authored scenarios, not an arbitrary model family.
    expected = {
        'SYN-NL-FUEL-01': {'c0fb79df63b9b87116ddb96552d139de177eb9ac71440b662d3d4719f6f65572', '9ddce6172b829a8860d5b97c249ce56530003f839df436698c084e50b5d338af'},
        'SYN-NL-LV-01': {'debf46903cbcd78694ea91bd1734f8ba9e503be36387288bbf1395661450c45b', '3709fe9cb1e60f951a29fbffee8a5178ce9c335d9ac9a8fcfd331be543c8f138'},
    }
    if digest not in expected[value['case_id']]:
        raise ValueError('configuration differs from the fixed authored case; use a reviewed new profile')
    return digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()
    paths = args.paths or sorted((Path(__file__).parent / 'scenarios').glob('*.json'))
    for path in paths:
        value = json.loads(path.read_text())
        print(json.dumps({'case_id': value['case_id'], 'canonical_sha256': validate(value), 'status': 'valid-config-not-feasibility'}))


if __name__ == '__main__':
    main()
