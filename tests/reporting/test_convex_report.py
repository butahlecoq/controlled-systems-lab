"""Independent convex reporting oracles; all generated records are purpose=test."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts' / 'reports'))
import report_data as data

PIN = '2b44b074cf41439325ce4d0bbdac2d51379f56faf17ba15320a410d3c1f07275'

class NativePhaseTests(unittest.TestCase):
    def trial(self, lines='', termination='resource_limit', status='returned'):
        raw = ('adapter.version=1.0.0+highs.1.11.0\nnative.version=1.11.0\n'
               f'native.archive_sha256={PIN}\nprogram.original=original\nprogram.solver=solver\n' + lines + '\nnative.log:\n')
        return {'identity': {'problem':'literal','program':'original'},
                'attempt': {'number':1,'state':'returned_result','workspace_reuse':False},
                'harness': {'status':status}, 'public_run_entered':True,
                'result': {'termination':termination,'outcome':'undetermined','raw_diagnostics':raw}}

    def project(self, trial, route='qp'):
        return data.convex_native_phases(trial, route, 'solver')

    def expect(self, value, state, reason, count=None, iteration_reason='phase_not_called', kind='simplex'):
        self.assertEqual(value['execution']['state'],state)
        self.assertEqual(value['execution']['reason'],reason)
        self.assertEqual(value['iterations'], {'available':count is not None,'kind':kind,'value':count,'reason':None if count is not None else iteration_reason})
        self.assertEqual(value['elapsed'], {'available':False,'value':None,'unit':'ns','reason':'not_exposed_by_adapter'})
        if state != 'observed_return': self.assertIsNone(value['execution']['statuses'])

    def test_configured_feasibility_does_not_prove_call(self):
        p=self.project(self.trial('phase.feasibility.time_limit=0'))
        self.expect(p['feasibility'],'known_not_called','stopped_before_phase_call')
        self.expect(p['qp'],'known_not_called','earlier_phase_exit',kind='qp')
        self.expect(p['linear'],'known_not_called','route_not_selected')

    def test_observed_feasibility_and_configured_qp(self):
        p=self.project(self.trial('phase.feasibility.time_limit=1\nphase.feasibility.api_status=0\nphase.feasibility.model_status=7\nphase.feasibility.iterations=0\nstart.valid=true\nstart.default_fallback=false\nphase.qp.time_limit=0','cancelled'))
        self.expect(p['feasibility'],'observed_return','returned_status_pair',0)
        self.assertEqual(p['feasibility']['execution']['statuses'],{'api_status':0,'model_status':7})
        self.expect(p['qp'],'known_not_called','stopped_before_phase_call',kind='qp')

    def test_configured_linear_is_not_returned(self):
        p=self.project(self.trial('phase.linear.time_limit=0'),'linear')
        self.expect(p['linear'],'known_not_called','stopped_before_phase_call')
        self.expect(p['feasibility'],'known_not_called','route_not_selected')

    def test_returned_info_unavailable_differs_from_literal_zero(self):
        base='phase.linear.time_limit=1\nphase.linear.api_status=0\nphase.linear.model_status=7\n'
        unavailable=self.project(self.trial(base+'phase.linear.info=unavailable','completed'),'linear')['linear']
        zero=self.project(self.trial(base+'phase.linear.iterations=0','completed'),'linear')['linear']
        self.expect(unavailable,'observed_return','returned_status_pair',iteration_reason='native_info_unavailable')
        self.expect(zero,'observed_return','returned_status_pair',0)
        self.assertNotEqual(data.digest(unavailable),data.digest(zero))

    def test_scheduler_width_diagnostics_are_accepted_but_validated(self):
        returned=('phase.linear.time_limit=1\nphase.linear.scheduler_threads=4\n'
                  'phase.linear.api_status=0\nphase.linear.model_status=7\nphase.linear.iterations=0')
        p=self.project(self.trial(returned,'completed'),'linear')
        self.expect(p['linear'],'observed_return','returned_status_pair',0)
        for invalid in ('0','-1','4097','many'):
            with self.subTest(width=invalid),self.assertRaises(ValueError):
                self.project(self.trial(returned.replace('scheduler_threads=4','scheduler_threads='+invalid),'completed'),'linear')
        retry=self.trial('phase.feasibility.time_limit=1\nphase.feasibility.api_status=0\n'
                         'phase.feasibility.model_status=7\nphase.feasibility.iterations=0\n'
                         'start.valid=true\nstart.default_fallback=false\nphase.qp.time_limit=1\n'
                         'phase.qp.api_status=0\nphase.qp.model_status=7\nphase.qp.iterations=0\n'
                         'phase.qp.retry.time_limit=1\nphase.qp.retry.scheduler_threads=2\n'
                         'phase.qp.retry.api_status=0\nphase.qp.retry.model_status=7','completed')
        self.project(retry)
        retry['result']['raw_diagnostics']=retry['result']['raw_diagnostics'].replace(
            'phase.qp.retry.scheduler_threads=2','phase.qp.retry.scheduler_threads=999999')
        with self.assertRaises(ValueError):self.project(retry)

    def test_exception_aborted_and_before_entry_are_distinct(self):
        for status,reason in [('exception','exception_boundary_unobserved'),('aborted','aborted_boundary_unobserved')]:
            trial=self.trial(status=status);trial['result']=None;trial['attempt']=None
            for phase,value in self.project(trial).items():
                self.expect(value,'unknown',reason,iteration_reason='execution_unknown',kind='qp' if phase=='qp' else 'simplex')
            trial['public_run_entered']=False
            for phase,value in self.project(trial).items():
                self.expect(value,'known_not_called','before_public_entry',kind='qp' if phase=='qp' else 'simplex')

    def test_prefix_corruption_and_log_spoof(self):
        base='phase.linear.time_limit=1\nphase.linear.api_status=0\nphase.linear.model_status=7\nphase.linear.iterations=0'
        for bad in [base.replace('phase.linear.model_status=7\n',''),base+'\nphase.linear.api_status=0',base+'\nphase.linear.info=unavailable',base.replace('iterations=0','iterations=-1'),base.replace('api_status=0','api_status=-1'),base+'\nnative_run=false']:
            with self.subTest(prefix=bad),self.assertRaises(ValueError):self.project(self.trial(bad),'linear')
        trial=self.trial('phase.linear.time_limit=0');trial['result']['raw_diagnostics']+=base
        p=self.project(trial,'linear')
        self.expect(p['linear'],'known_not_called','stopped_before_phase_call')
        forged=copy.deepcopy(p);forged['linear']['execution']['state']='observed_return'
        self.assertNotEqual(forged,self.project(trial,'linear'))

    def test_budget_with_setup_error_or_exception_cannot_prove_noncall(self):
        for status in ('returned','exception'):
            trial=self.trial('phase.feasibility.time_limit=0\nsetup.error=failed',status=status)
            self.assertEqual(self.project(trial)['feasibility']['execution']['state'],'unknown')

    def test_returned_prefix_requires_actual_native_statement_order(self):
        for raw in ('phase.linear.api_status=0\nphase.linear.model_status=7\nphase.linear.time_limit=1\nphase.linear.iterations=0',
                    'phase.linear.time_limit=1\nphase.linear.model_status=7\nphase.linear.api_status=0\nphase.linear.iterations=0'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.project(self.trial(raw),'linear')

    def test_completed_earlier_phase_survives_later_setup_error(self):
        trial=self.trial('phase.feasibility.time_limit=1\nphase.feasibility.api_status=0\nphase.feasibility.model_status=7\nphase.feasibility.iterations=2\nsetup.error=later setup failed','numerical_failure')
        p=self.project(trial)
        self.expect(p['feasibility'],'observed_return','returned_status_pair',2)
        self.assertEqual(p['qp']['execution']['state'],'unknown')

    def test_wrong_route_configuration_and_positive_boundary_conflicts_reject(self):
        feasibility=('phase.feasibility.time_limit=1\nphase.feasibility.api_status=0\n'
                     'phase.feasibility.model_status=7\nphase.feasibility.iterations=0')
        linear=('phase.linear.time_limit=1\nphase.linear.api_status=0\n'
                'phase.linear.model_status=7\nphase.linear.iterations=0')
        cases=[('qp','phase.linear.time_limit=0'),
               ('linear','phase.feasibility.time_limit=0'),
               ('linear','phase.qp.time_limit=0'),
               ('constant','phase.linear.time_limit=0'),
               ('constant','phase.feasibility.time_limit=0'),
               ('constant','phase.qp.time_limit=0'),
               ('qp','native_run=false\nphase.feasibility.time_limit=0'),
               ('linear','native_run=false\nphase.linear.time_limit=0'),
               ('qp','phase.qp.time_limit=0'),
               ('qp',feasibility+'\nphase.qp.time_limit=0\nstart.valid=true\nstart.default_fallback=false'),
               ('qp',feasibility+'\nqp_run=false\nstart.valid=false\nphase.qp.time_limit=0'),
               ('linear','start.valid=true\nstart.default_fallback=false'),
               ('qp','wrapper.decision=constant_rows'),
               ('qp',feasibility+'\nstart.valid=true\nstart.default_fallback=false\nnative_run=false')]
        for route,raw in cases:
            with self.subTest(route=route,raw=raw),self.assertRaises(ValueError):
                self.project(self.trial(raw),route)
        for raw,route in [('', 'qp'),('phase.feasibility.time_limit=0','qp'),(linear,'linear')]:
            trial=self.trial(raw);trial['public_run_entered']=False
            with self.subTest(before_entry=raw),self.assertRaises(ValueError):self.project(trial,route)

    def test_invalid_start_and_explicit_native_noncall_remain_supported(self):
        feasibility=('phase.feasibility.time_limit=1\nphase.feasibility.api_status=0\n'
                     'phase.feasibility.model_status=7\nphase.feasibility.iterations=0')
        p=self.project(self.trial(feasibility+'\nqp_run=false\nstart.valid=false','numerical_failure'))
        self.expect(p['feasibility'],'observed_return','returned_status_pair',0)
        self.expect(p['qp'],'known_not_called','invalid_qp_start',kind='qp')
        for value in self.project(self.trial('native_run=false')).values():
            self.assertEqual(value['execution']['reason'],'explicit_pre_entry_stop')



class SavedConvexTests(unittest.TestCase):
    def fixture(self):
        return data.load_view(Path(__file__).parent/'fixtures'/'convex-view-v2.json')

    def test_literal_view_preserves_distinct_original_and_squared_costs(self):
        v=self.fixture();self.assertFalse(data.publishable(v));self.assertEqual(len(v['payload']['scenarios']),9)
        self.assertEqual(v['payload']['trials'][2]['result']['solver_objective'],17)
        self.assertAlmostEqual(v['payload']['trials'][2]['result']['original_objective'],17**.5)
        self.assertEqual(v['payload']['trials'][4]['result']['original_objective'],5)
        self.assertEqual(v['payload']['trials'][4]['result']['solver_objective'],25)
        self.assertEqual(data.validate_view(v),v)

    def test_resealed_wrong_saved_observation_is_rejected(self):
        changes=[lambda t:t['native_phases']['qp']['execution'].update(state='known_not_called'),
                 lambda t:t['native_phases']['qp']['iterations'].update(value=99),
                 lambda t:t['native_phases']['qp']['elapsed'].update(available=True,value=0),
                 lambda t:t['result'].update(solver_objective=9),
                 lambda t:t['result']['dual_residuals'].update(complementarity=None),
                 lambda t:t['registry'].update(requested='csl.lp.highs'),
                 lambda t:t.update(public_run_entered=False),
                 lambda t:t['attempt'].update(number=2),
                 lambda t:t['result']['bounds'].update(lower=1)]
        for change in changes:
            v=self.fixture();change(v['payload']['trials'][2])
            with self.subTest(change=change),self.assertRaises(ValueError):data.validate_view(data.seal(v['payload']))

    def test_each_present_residual_context_uses_the_declared_policy_even_on_failure(self):
        for failed in (False,True):
            for block in ('primal_residuals','dual_residuals'):
                for field in ('absolute_tolerance','relative_tolerance'):
                    view=self.fixture();trial=view['payload']['trials'][0]
                    if failed:
                        trial['validation']={'passed':False,'errors':['retained stopped result']}
                        trial['result'].update(termination='resource_limit',outcome='undetermined')
                    data.validate_view(data.seal(view['payload']))
                    trial['result'][block]['context'][field]=1.0
                    with self.subTest(failed=failed,block=block,field=field),self.assertRaises(ValueError):
                        data.validate_view(data.seal(view['payload']))

    def test_unavailable_residual_blocks_remain_unavailable_on_retained_failure(self):
        for absent in (('primal_residuals',),('dual_residuals',),('primal_residuals','dual_residuals')):
            view=self.fixture();trial=view['payload']['trials'][0]
            trial['validation']={'passed':False,'errors':['residuals unavailable']}
            names=[]
            for block in absent:
                names.extend(('rows','variables') if block=='primal_residuals' else ('stationarity','signs','complementarity'))
                trial['result'][block]=None
            raw=trial['result']['raw_diagnostics']
            trial['result']['raw_diagnostics']='\n'.join(line for line in raw.split('\n') if not any(line.startswith('check.'+name+'.') for name in names))
            accepted=data.validate_view(data.seal(view['payload']))
            for block in absent:self.assertIsNone(accepted['payload']['trials'][0]['result'][block])

    def test_resealed_wrong_route_and_before_entry_records_reject(self):
        def entry(state,reason,kind):
            return {'execution':{'state':state,'reason':reason,'statuses':None},
                    'iterations':{'available':False,'kind':kind,'value':None,
                                  'reason':'execution_unknown' if state=='unknown' else 'phase_not_called'},
                    'elapsed':{'available':False,'value':None,'unit':'ns','reason':'not_exposed_by_adapter'}}
        # Literal projections deliberately match the old precedence; hashes cannot
        # turn impossible source branches into legitimate partial observations.
        for index,wrong,states in [
            (0,'linear',[('unknown','no_returned_phase_evidence'),('unknown','no_returned_phase_evidence'),('known_not_called','stopped_before_phase_call')]),
            (4,'feasibility',[('known_not_called','stopped_before_phase_call'),('known_not_called','route_not_selected'),('unknown','no_returned_phase_evidence')]),
            (4,'qp',[('known_not_called','route_not_selected'),('known_not_called','stopped_before_phase_call'),('unknown','no_returned_phase_evidence')])]:
            view=self.fixture();trial=view['payload']['trials'][index]
            trial['validation']={'passed':False,'errors':['retained stop']}
            result=trial['result'];result.update(termination='resource_limit',outcome='undetermined')
            prefix,body=result['raw_diagnostics'].split('\nnative.log:\n',1)
            prefix='\n'.join(line for line in prefix.splitlines() if not line.startswith(('phase.','start.')))
            result['raw_diagnostics']=prefix+'\nphase.'+wrong+'.time_limit=0\nnative.log:\n'+body
            trial['native_phases']={phase:entry(state,reason,'qp' if phase=='qp' else 'simplex')
                                    for phase,(state,reason) in zip(('feasibility','qp','linear'),states)}
            with self.subTest(route=index,wrong=wrong),self.assertRaises(ValueError):data.validate_view(data.seal(view['payload']))
        view=self.fixture();trial=view['payload']['trials'][0]
        trial['validation']={'passed':False,'errors':['contradictory public boundary']}
        trial['public_run_entered']=False
        trial['timings']['public_run']={'available':False,'reason':'not entered'}
        trial['native_phases']['linear']=entry('known_not_called','before_public_entry','simplex')
        with self.assertRaises(ValueError):data.validate_view(data.seal(view['payload']))

    def test_convex_document_and_csv_expose_both_costs_and_native_availability(self):
        import render
        view=self.fixture();page=render.document(view)
        self.assertIn('Registered HiGHS reference convex',page)
        self.assertIn('Observed native return',page)
        fields,rows,_,_=render.csv_projection(view)
        self.assertIn('solver_objective',fields)
        self.assertEqual(rows[2]['solver_objective'],17)
        self.assertEqual(rows[7]['qp_execution_state'],'known_not_called')
        self.assertEqual(rows[7]['qp_iterations_value'],'')
        self.assertEqual(rows[0]['qp_iterations_value'],0)
        self.assertEqual(rows[0]['qp_elapsed_value_ns'],'')
        self.assertIn('not_exposed_by_adapter',page)

    def test_legacy_published_lp_still_validates_without_rewriting(self):
        import site as unused_stdlib_site
        import importlib.util
        spec=importlib.util.spec_from_file_location('report_site',Path(data.__file__).with_name('site.py'))
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        root=Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'
        for bundle in root.glob('lp-*'):
            if bundle.is_dir():
                before={p.name:data.file_digest(p) for p in bundle.iterdir()}
                self.assertEqual(site.validate_bundle(bundle)['schema'],data.SCHEMA)
                self.assertEqual(before,{p.name:data.file_digest(p) for p in bundle.iterdir()})


class ConvexProjectionTests(unittest.TestCase):
    fixture=SavedConvexTests.fixture
    def test_literal_stops_unknown_zero_and_unavailable_survive_csv_html(self):
        import render
        literals=[
            (0,'phase.feasibility.time_limit=0','resource_limit','feasibility','known_not_called','stopped_before_phase_call',None,'phase_not_called'),
            (0,'phase.feasibility.time_limit=1\nphase.feasibility.api_status=0\nphase.feasibility.model_status=7\nphase.feasibility.iterations=0\nstart.valid=true\nstart.default_fallback=false\nphase.qp.time_limit=0','cancelled','qp','known_not_called','stopped_before_phase_call',None,'phase_not_called'),
            (4,'phase.linear.time_limit=0','resource_limit','linear','known_not_called','stopped_before_phase_call',None,'phase_not_called'),
            (4,'phase.linear.time_limit=1\nphase.linear.api_status=0\nphase.linear.model_status=7\nphase.linear.info=unavailable','completed','linear','observed_return','returned_status_pair',None,'native_info_unavailable'),
            (4,'phase.linear.time_limit=1\nphase.linear.api_status=0\nphase.linear.model_status=7\nphase.linear.iterations=0','completed','linear','observed_return','returned_status_pair',0,None),
            (0,None,None,'qp','unknown','exception_boundary_unobserved',None,'execution_unknown')]
        for index,raw,termination,phase,state,reason,count,iteration_reason in literals:
            with self.subTest(state=state,count=count,phase=phase):
                v=self.fixture();p=v['payload'];scenario=p['scenarios'][index];t=p['trials'][index]
                p['scenarios']=[scenario];p['trials']=[t];p['process'].update(expected_trials=1,emitted_trials=1)
                t['sequence']=1;t['validation']={'passed':False,'errors':['literal failure/partial evidence test']}
                if raw is None:t.update(result=None,harness={'status':'exception','error':'literal throw','diagnostics':[]},attempt=None)
                else:
                    common='\n'.join(line for line in t['result']['raw_diagnostics'].split('\nnative.log:\n')[0].splitlines() if not line.startswith(('phase.','start.')))
                    t['result']['raw_diagnostics']=common+'\n'+raw+'\nnative.log:\nLiteral phase test'
                    t['result'].update(termination=termination,outcome='undetermined')
                t['native_phases']=data.convex_native_phases(t,data.convex_route(scenario),scenario['solver']['identity']['program'])
                v=data.validate_view(data.seal(p));entry=t['native_phases'][phase]
                self.assertEqual(entry['execution']['state'],state);self.assertEqual(entry['execution']['reason'],reason)
                self.assertEqual(entry['iterations']['value'],count);self.assertEqual(entry['iterations']['reason'],iteration_reason)
                _,rows,_,_=render.csv_projection(v);row=rows[0]
                self.assertEqual(row[phase+'_execution_state'],state);self.assertEqual(row[phase+'_iterations_value'],'' if count is None else count)
                self.assertEqual(row[phase+'_elapsed_value_ns'],'')
                page=render.document(v);self.assertTrue(('Observed native return' if state=='observed_return' else 'Not called' if state=='known_not_called' else 'Unknown') in page)
                corrupt=copy.deepcopy(p);corrupt['trials'][0]['native_phases'][phase]['execution']['state']='observed_return' if state!='observed_return' else 'unknown'
                with self.assertRaises(ValueError):data.validate_view(data.seal(corrupt))

    def test_partial_counts_bad_intervals_and_wrong_subjects_reject_after_reseal(self):
        changes=[lambda p:p['trials'][0]['timings']['public_run'].update(start_tick='999'),
                 lambda p:p['trials'][0]['result']['dual_residuals']['context']['subject'].update(program='wrong'),
                 lambda p:p['process'].update(expected_trials=5),
                 lambda p:p['process'].update(warmup_failures=1),
                 lambda p:p['trials'].pop(),
                 lambda p:p['trials'][0].update(sequence=2),
                 lambda p:p['provenance']['backend'].update(version='other'),
                 lambda p:p['provenance'].update(native_archive_sha256='f'*64),
                 lambda p:p.update(report_kind='lp'),
                 lambda p:p['scenarios'][2]['solver']['identity'].update(program='norm-positive')]
        for change in changes:
            v=self.fixture();change(v['payload'])
            with self.subTest(change=change),self.assertRaises(ValueError):data.validate_view(data.seal(v['payload']))

    def test_raw_event_and_profile_sidecars_cannot_be_resealed_into_different_results(self):
        import collector_common as collector,importlib.util,json,tempfile
        spec=importlib.util.spec_from_file_location('convex_sidecar_site',Path(data.__file__).with_name('site.py'))
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        original=self.fixture()['payload']
        header={'schema':data.CONVEX_EVENT_SCHEMA,'event':'header','purpose':'test','repetitions':1,'warmups':0,'build':original['provenance']['build'],'clock':original['environment']['clock'],'scenarios':original['scenarios']}
        events=[header]
        for trial in original['trials']:
            t=copy.deepcopy(trial);t.pop('native_phases')
            events.extend([{'schema':data.CONVEX_EVENT_SCHEMA,'event':'trial','trial':t},
                           {'schema':data.CONVEX_EVENT_SCHEMA,'event':'serialization','sequence':t['sequence'],'purpose':'test','duration_ns':1,'scope':'build trial JSON bytes; excludes event framing, write and flush'}])
        events.append({'schema':data.CONVEX_EVENT_SCHEMA,'event':'end','emitted_trials':9,'failures':0,'warmup_failures':0,'complete':True})
        raw=('\n'.join(json.dumps(e) for e in events)+'\n').encode()
        counter={'available':False,'reason':'literal test'}
        body={'schema':data.CONVEX_EVENT_SCHEMA,'event':'profile','purpose':'profile','rounds':1,'trials':9,'failures':0,'observation_token':'1','wall_ns':200,'phase_totals_ns':[10,20,30,40,50,180],'before':{'user_cpu':counter,'kernel_cpu':counter,'peak_resident':counter},'after':{'user_cpu':counter,'kernel_cpu':counter,'peak_resident':counter}}
        profile={'schema':'csl.convex-profile/1','purpose':'profile','return_code':0,'aborted':False,'events':[{**header,'purpose':'profile'},body],'phase_order':list(data.PHASES),'assessment':collector.profile_assessment(body)}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'raw-events.jsonl').write_bytes(raw);(root/'process-stderr.txt').write_bytes(b'')
            (root/'profile.json').write_text(json.dumps(profile),encoding='utf-8')
            pointer={'available':True,'valid':True,'file':'profile.json','sha256':data.file_digest(root/'profile.json'),'scope':'separate profile'}
            p=collector.event_payload(events,0,raw,b'',original['provenance'],original['environment'],pointer)
            view=data.validate_view(data.seal(p));site.validate_convex_sidecars(root,view)
            changed=copy.deepcopy(view['payload']);changed['trials'][0]['timings']['public_run'].update(end_tick='36',duration_ns=6)
            with self.assertRaises(ValueError):site.validate_convex_sidecars(root,data.seal(changed))
            profile['events'][1]['trials']=5;(root/'profile.json').write_text(json.dumps(profile),encoding='utf-8')
            changed=copy.deepcopy(p);changed['profile']['sha256']=data.file_digest(root/'profile.json')
            with self.assertRaises(ValueError):site.validate_convex_sidecars(root,data.seal(changed))
            broken=copy.deepcopy(events);broken[2]['sequence']=99
            with self.assertRaises(ValueError):collector.event_payload(broken,0,raw,b'',original['provenance'],original['environment'],pointer)
            broken=copy.deepcopy(events);broken[-1]['warmup_failures']=1
            with self.assertRaises(ValueError):collector.event_payload(broken,0,raw,b'',original['provenance'],original['environment'],pointer)
            partial=collector.events_from_bytes(raw.rsplit(b'\n',2)[0]+b'\n{"unfinished":',aborted=True)
            self.assertTrue(partial);self.assertEqual(partial[0]['event'],'header')
            with self.assertRaises(ValueError):collector.events_from_bytes(b'{broken}\n',aborted=True)


class ConvexPlotTests(unittest.TestCase):
    def test_pinned_plot_saved_only_regeneration_mixed_site_and_resealed_corruptions(self):
        import importlib.util, tempfile, json, csv, io, os
        from unittest.mock import patch
        if importlib.util.find_spec('matplotlib') is None:self.skipTest('run in the separate pinned reporting environment')
        import matplotlib,plot,render
        self.assertEqual(matplotlib.__version__,'3.11.2')
        # Pinned first-import font discovery may run fc-list on a cold Linux
        # cache. Initialize that dependency before forbidding all subprocesses
        # for the actual saved-data producer/consumer operations below.
        matplotlib.use('Agg')
        import matplotlib.pyplot
        spec=importlib.util.spec_from_file_location('convex_report_site',Path(data.__file__).with_name('site.py'))
        site=importlib.util.module_from_spec(spec);spec.loader.exec_module(site)
        view=data.load_view(Path(__file__).parent/'fixtures'/'convex-view-v2.json')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            with patch('subprocess.Popen',side_effect=AssertionError('saved-only regeneration must not execute a solver')):
                import subprocess
                with self.assertRaisesRegex(AssertionError,'must not execute a solver'):
                    subprocess.run(['csl_convex_report','--smoke'],check=True)
                metadata=plot.plot(view,root/'figures')
                svg=(root/'figures'/'latency.svg').read_bytes()
                self.assertFalse(svg.startswith(b'<?xml'));self.assertNotIn(b'<!DOCTYPE',svg);self.assertNotIn(b'<metadata',svg)
                self.assertEqual(metadata['series']['public_run'][2]['values'],[5])
                bundle=render.render(view,root/view['report_id'],root/'figures')
                self.assertEqual(site.validate_bundle(bundle,allow_test=True),view)
                regenerated=render.render(view,root/'regenerated',root/'figures')
                for name in ('index.html','records.json','scenarios.json','trials.csv','summary.csv','latency.svg','latency.png'):
                    self.assertEqual((bundle/name).read_bytes(),(regenerated/name).read_bytes())
            site.make_zip(bundle,root/(view['report_id']+'.zip'),allow_test=True)
            catalog={'schema':'csl.algorithm-report-catalog/2','reports':[{'report_kind':'convex','report_id':view['report_id'],'payload_sha256':view['payload_sha256'],'source_commit':'0'*40,'zip_sha256':data.file_digest(root/(view['report_id']+'.zip'))}]}
            import shutil
            published=Path(__file__).resolve().parents[2]/'reports'/'algorithm-results'
            old_catalog=data.parse_json((published/'catalog.json').read_text(encoding='utf-8'))
            old=old_catalog['reports'][0];rid=old['source_report_id']
            source_archive=published/(rid+'.source.zip')
            shutil.copytree(published/rid,root/rid);shutil.copyfile(source_archive,root/(rid+'.zip'))
            legacy_old={key:value for key,value in old.items() if key not in ('payload_schema','native_payload_sha256','measured_scope','evidence_limits','source_report_id')}
            legacy_old['report_id']=rid
            source_view=data.parse_json((root/rid/'records.json').read_text(encoding='utf-8'))
            legacy_old['payload_sha256']=source_view['payload_sha256']
            legacy_old['zip_sha256']=data.file_digest(source_archive)
            catalog['reports'].insert(0,{**legacy_old,'report_kind':'lp'})
            self.assertTrue(rid+'/index.html' in site.catalogue_index(catalog))
            (root/'catalog.json').write_text(json.dumps(catalog),encoding='utf-8');(root/'index.html').write_text(site.catalogue_index(catalog),encoding='utf-8')
            site.stage(root/'catalog.json',root/'site',allow_test=True)
            def replace(name,content):
                (bundle/name).write_bytes(content);manifest=data.parse_json((bundle/'manifest.json').read_text(encoding='utf-8'));manifest['files'][name]=data.file_digest(bundle/name);(bundle/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            original=(bundle/'trials.csv').read_bytes()
            for column,value in [('solver_objective','999'),('candidate','[999]'),('complementarity_violation','999'),('stationarity_scale','999'),('qp_execution_state','unknown'),('qp_iterations_value','999'),('qp_elapsed_value_ns','0')]:
                reader=csv.DictReader(io.StringIO(original.decode()));rows=list(reader);rows[0][column]=value
                out=io.StringIO(newline='');writer=csv.DictWriter(out,reader.fieldnames);writer.writeheader();writer.writerows(rows);replace('trials.csv',out.getvalue().encode())
                with self.subTest(column=column),self.assertRaises(ValueError):site.validate_bundle(bundle,allow_test=True)
            replace('trials.csv',original)
            page=(bundle/'index.html').read_bytes();replace('index.html',page.replace(b'Registered HiGHS reference convex',b'False numerical claim',1))
            with self.assertRaises(ValueError):site.validate_bundle(bundle,allow_test=True)
            for unsafe in (b'<!DOCTYPE svg><svg/>',b'<svg xmlns="http://www.w3.org/2000/svg"><use href="https://bad.invalid/a"/></svg>'):
                with self.assertRaises(ValueError):data.validate_svg(unsafe)


def smoke(exe):
    import subprocess
    import collector_common as collector
    described=subprocess.run([str(exe),'--describe'],capture_output=True,check=True,timeout=30)
    header=collector.events_from_bytes(described.stdout)[0]
    expected=data.load_view(Path(__file__).parent/'fixtures'/'convex-view-v2.json')['payload']['scenarios']
    observed=collector.scenarios(header)
    if observed!=expected: raise AssertionError('independently authored complete convex catalogue differs')
    ran=subprocess.run([str(exe),'--smoke'],capture_output=True,timeout=60)
    events=collector.events_from_bytes(ran.stdout,ran.returncode!=0)
    view=collector.test_view(events,exe,ran.returncode,ran.stdout,ran.stderr)
    if ran.returncode or not all(t['validation']['passed'] for t in view['payload']['trials']):raise AssertionError('actual convex smoke failed')
    expected_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],text=True).strip()
    collector.verify_build_identity(events[0],expected_commit,functional=True)
    build=Path(exe).resolve().parent.parent if Path(exe).parent.name in ('Release','Debug','RelWithDebInfo','MinSizeRel') else Path(exe).resolve().parent
    graph=collector.file_api(build,header['build']['configuration'],collector.CONVEX)
    collector.verify_artifact(header,graph,build,exe)
    import tempfile,shutil
    targets={target['name']:target for target in graph['targets']}
    if not targets['highs'].get('compileGroups') or not targets['csl_convex_report'].get('link',{}).get('commandFragments'):raise AssertionError('actual native compile/link graph absent')
    if not any('eigen' in entry['path'].lower() for group in targets['csl_objectives']['compileGroups'] for entry in group.get('includes',[])):raise AssertionError('objective Eigen compile provenance absent')
    def rejected(action):
        try:action()
        except ValueError:return
        raise AssertionError('corrupt artifact provenance accepted')
    for missing in ('highs','csl_convex','csl_objectives','csl_report_runtime'):
        changed=copy.deepcopy(graph);changed['targets']=[t for t in changed['targets'] if t['name']!=missing]
        rejected(lambda:collector.verify_artifact(header,changed,build,exe))
    for field,value in (('compiler','different'),('compiler_version','unknown'),('build_owner_sha256','f'*64),('configured_flags','-a-flag-not-in-build')):
        changed=copy.deepcopy(header);changed['build'][field]=value
        rejected(lambda:collector.verify_artifact(changed,graph,build,exe))
    with tempfile.TemporaryDirectory(dir=build) as temp:
        foreign=Path(temp)/Path(exe).name;shutil.copyfile(exe,foreign)
        rejected(lambda:collector.verify_artifact(header,graph,build,foreign))
    if header['build']['configuration']=='Debug':rejected(lambda:collector.verify_build_identity(events[0],expected_commit))
    for args in (['--profile','--rounds','100001'],['--measure','--repetitions','1'],['--smoke','--rounds','1'],['--unknown']):
        bad=subprocess.run([str(exe),*args],capture_output=True,timeout=10)
        if bad.returncode==0 or bad.stdout:raise AssertionError('bounded CLI admission failed')
    print('Convex functional smoke: 9/9; full independent catalogue, numerical results, phase evidence and actual artifact binding passed.')

if __name__ == '__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--exe': smoke(Path(sys.argv[2]))
    else: unittest.main()
