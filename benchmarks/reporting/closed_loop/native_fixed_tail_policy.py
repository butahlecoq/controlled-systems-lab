"""External runner transport/verification for the C++ fixed-tail policy.

All feasibility, warm initialization, region construction and action optimization
happen in csl_closed_loop_native_policy. This adapter never chooses a control.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess

from contracts import manifest_sha256
from history_policy import make_request
from history_validation import validate
from fixed_tail_validation import validate_regions
from task_models import prediction_receipt, validate_source_binding

FAMILIES = ('polytope', 'box', 'zonotope', 'parallelotope', 'ellipsoid')
CONTROLLERS = {f'native-fixed-tail-{family}-ipopt/1': family for family in FAMILIES}


class NativeFixedTailPolicy:
    def __init__(self, task, task_sha256, controller_id, action_profile_id, factory_options=None):
        validate_source_binding(task)
        if manifest_sha256(task) != task_sha256 or controller_id not in CONTROLLERS:
            raise ValueError('native fixed-tail task or controller identity differs')
        if action_profile_id != task['control_domains']['continuous']['problem_id']:
            raise ValueError('native fixed-tail policy requires the original continuous action domain')
        options = dict(factory_options or {})
        if set(options) != {'wall_seconds', 'build_backend_profile'} or options['wall_seconds'] != 60:
            raise ValueError('native fixed-tail profile requires its registered budget and native build profile')
        self.task, self.task_sha256 = task, task_sha256
        self.controller_id, self.action_profile_id = controller_id, action_profile_id
        self.family = CONTROLLERS[controller_id]
        self.options, self.receipt = options, prediction_receipt(task)
        self.previous_history, self.last_query_capture, self.query_capture_callback = None, None, None
        executable = Path(os.environ['CSL_NATIVE_POLICY_BRIDGE']).resolve(strict=True)
        self.process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=None, text=True, bufsize=1)
        self.preparation_receipt = {'executable': str(executable),
            'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
            'binary_source': 'unknown', 'action_profile_id': action_profile_id,
            'original_horizon': task['episode']['intervals'], 'history_solver': 'native-casadi-ipopt',
            'controller_semantics': 'native C++ feasible fixed tail; continuous current action; all-stage physical inner regions; complete original source cost',
            'decision_implementation': 'C++',
            'stderr_policy': 'native process inherits the supervised worker stderr stream; shared process log, not isolated per-call stderr',
            'external_adapter_roles': ['source-bound predictor fixture preparation', 'transport', 'independent validation']}

    def set_query_capture_callback(self, callback):
        self.query_capture_callback = callback

    def _capture(self):
        if self.query_capture_callback:
            self.query_capture_callback(copy.deepcopy(self.last_query_capture))

    def query(self, task_id, observed_physical_state, absolute_update_index):
        if task_id != self.task['task_id']:
            raise ValueError('query task differs from source-bound native policy task')
        request = make_request(self.task, self.task_sha256, self.receipt,
            observed_physical_state, absolute_update_index, history_solver='casadi-ipopt')
        request.update(mode='fixed-tail-policy/1', controller_id=self.controller_id,
                       fixed_tail_family=self.family, wall_seconds=self.options['wall_seconds'])
        if self.previous_history is not None:
            request['previous_history'] = self.previous_history
        raw = json.dumps(request, separators=(',', ':'), allow_nan=False) + '\n'
        self.last_query_capture = {'schema': 'csl.closed-loop.native-query-capture/2',
            'capture_kind': 'bridge-exchange', 'request': request, 'bridge_request_raw': raw,
            'request_sha256': hashlib.sha256(raw.encode()).hexdigest(), 'bridge_request_sent': False,
            'bridge_request_transmission_status': 'prepared', 'response_parse_status': 'not_received',
            'bridge_response_raw': None}
        self._capture()
        self.last_query_capture['bridge_request_transmission_status'] = 'attempted'; self._capture()
        self.process.stdin.write(raw); self.process.stdin.flush()
        self.last_query_capture.update(bridge_request_sent=True, bridge_request_transmission_status='sent'); self._capture()
        response_raw = self.process.stdout.readline()
        self.last_query_capture.update(bridge_response_raw=response_raw,
            bridge_response_sha256=hashlib.sha256(response_raw.encode()).hexdigest(), response_parse_status='raw_received' if response_raw else 'missing_response')
        self._capture()
        if not response_raw:
            raise RuntimeError('native fixed-tail controller exited before responding')
        try:
            response = json.loads(response_raw)
        except ValueError:
            self.last_query_capture['response_parse_status'] = 'malformed_json'; self._capture(); raise
        self.last_query_capture.update(parsed_response=response, response_parse_status='parsed'); self._capture()
        if any(response.get(key) != value for key, value in {'task_id': task_id,
                'task_sha256': self.task_sha256, 'action_profile_id': self.action_profile_id,
                'policy_id': self.controller_id}.items()):
            raise ValueError('native fixed-tail response identity differs')
        if response.get('build_backend_profile') != self.options['build_backend_profile']:
            raise ValueError('native fixed-tail binary differs from the admitted build profile')
        calls = [{'operation': 'controller.solve', 'module_id': 'csl::reachability::fixed_tail_policy',
                  'profile_id': self.controller_id, 'provider': call['actual'], 'version': call['version']}
                 for call in response.get('providers', [])]
        result = {'task_sha256': self.task_sha256, 'action_profile_id': self.action_profile_id,
            'policy_id': self.controller_id, 'status': 'failed', 'invocations': calls,
            'native_query_capture': self.last_query_capture, 'solve_receipt': {'native_response': response}}
        if response['status'] != 'accepted':
            result['reason'] = response.get('reason', response['status']); return result
        checks = validate(self.task, absolute_update_index, observed_physical_state,
                          request['predictor_stages'], response['source_history'], response['history'],
                          response['source_cost']['total'])
        physical = validate_regions(response, len(observed_physical_state), self.task['episode']['intervals'] - absolute_update_index)
        checks['physical_regions'] = physical
        checks['accepted'] &= physical['accepted']
        result['solve_receipt']['independent_validation'] = checks
        if not checks['accepted']:
            result['reason'] = 'independent original source H/J verification failed'; return result
        result['geometry_invocations'] = [{'operation': 'fixed-tail.regions',
            'actual_method_id': 'csl.reachability.inner-template/1' if self.family != 'polytope' else 'csl.reachability.fixed-tail-reference/1',
            'version': '1', 'role': 'reachable_set_method',
            'absolute_stage': absolute_update_index + region['stage'], 'geometry_role': 'fixed-tail-inner'}
            for region in response['regions']]
        self.previous_history = response['next_warm_history']
        result.update(status='accepted', control=response['control'],
            predicted_states=checks['states'], predicted_controls=checks['controls'],
            selected_representation=self.family, policy_semantics=response['assurance'],
            coverage='selected fixed-tail physical family, all remaining stages; local numerical action')
        return result

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate(); self.process.wait()
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.returncode:
            raise RuntimeError(f'native fixed-tail bridge exited with status {self.process.returncode}')


def create_policy(task, *, task_sha256, controller_id, action_profile_id, factory_options=None):
    return NativeFixedTailPolicy(task, task_sha256, controller_id, action_profile_id, factory_options)
