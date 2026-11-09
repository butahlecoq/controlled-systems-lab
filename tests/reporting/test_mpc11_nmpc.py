"""Actual short do-mpc NLP and shrinking-tail behavior."""
import json
from pathlib import Path
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc11'))
try:import do_mpc
except ImportError:raise unittest.SkipTest('optional MPC-11 environment required')
from nmpc import build_controller, initialize_guess, solve_update, direct_tail_cost, execution_integrator

class NMPCTests(unittest.TestCase):
    def scenario(self):return json.loads((ROOT/'benchmarks/reporting/mpc11/scenarios/syn-nl-lv-01.json').read_text())

    def test_short_stationary_nlp_and_tail_cost(self):
        s=self.scenario();s['time']['intervals']=3;s['time']['grid']=[0,.1,.2,.3];s['time']['final']=.3
        s['states'][0]['initial']=100;s['states'][1]['initial']=80
        mpc,meta=build_controller(s,0);guess=initialize_guess(mpc,s,0,np.array([1.,1.]),None)
        r,previous=solve_update(mpc,s,0,np.array([1.,1.]),guess,meta)
        self.assertTrue(r['accepted'],r['status']);self.assertLess(r['objective'],1e-7)
        self.assertLess(r['objective_reconstruction_difference'],1e-9)
        mpc2,meta2=build_controller(s,1);shift=initialize_guess(mpc2,s,1,np.array([1.01,.99]),previous)
        self.assertEqual(len(shift['controls']),2)
        np.testing.assert_allclose(shift['controls'],r['predicted_controls'][1:])
        np.testing.assert_allclose(shift['mesh_scaled'][0],[1.01,.99])
        self.assertEqual(shift['dual_policy'],'zero-every-solve')
        # Stage count shrinks but normalization stays at the original N=3.
        self.assertAlmostEqual(direct_tail_cost(s,1,[100,80],[[.05],[.05]]),.05*2/3)
        for k in range(2):mpc2.opt_x_num['_u',k,0,'u']=[.05]
        for k in range(3):mpc2.opt_x_num['_x',k,0,-1,'z']=[1.,1.]
        # Evaluate do-mpc's expanded objective on supplied values: no dt factor,
        # no remaining-N denominator, and no input-delta penalty.
        self.assertAlmostEqual(float(meta2['objective_function'](mpc2.opt_x_num,mpc2.opt_p_num)),.05*2/3,places=12)
        for c in range(len(mpc2.opt_x_num['_x',2,0])):
            np.testing.assert_allclose(mpc2.lb_opt_x['_x',2,0,c,'z'],[[0.],[0.]])
            np.testing.assert_allclose(mpc2.ub_opt_x['_x',2,0,c,'z'],[[2.],[150/80]])
        held=np.asarray(execution_integrator(s)(x0=[1.,1.],p=[0.])['xf']).T
        np.testing.assert_allclose(held,np.ones_like(held),atol=1e-12)
        self.assertAlmostEqual(meta2['original_interval_count'],3)

    def test_failed_local_solve_is_rejected(self):
        s=self.scenario();s['time']['intervals']=1;s['time']['grid']=[0,.1];s['time']['final']=.1
        s['nmpc']['solver']['max_iter']=0
        mpc,meta=build_controller(s,0);guess=initialize_guess(mpc,s,0,np.array([1.2,.75]),None)
        result,_=solve_update(mpc,s,0,np.array([1.2,.75]),guess,meta)
        self.assertFalse(result['accepted']);self.assertFalse(result['success'])
        self.assertEqual(result['status'],'Maximum_Iterations_Exceeded')

class PrefixReplayTests(unittest.TestCase):
    def test_partial_controls_keep_original_N_and_no_completed_objective(self):
        import os,tempfile
        from run_nmpc import replay_prefix
        from affine import canonical_hash
        bridge=os.environ.get('CSL_MPC11_REPLAY_BRIDGE')
        if not bridge:self.skipTest('CSL_MPC11_REPLAY_BRIDGE required')
        s=NMPCTests().scenario();initial=np.array([1.2,.75]);held=np.asarray(execution_integrator(s)(x0=initial,p=[.02])['xf']).T
        physical=(np.vstack([initial,held])*[100,80]).tolist();controls=[[.02]]
        record={'controls':controls,'physical_states':physical,'witness_sha256':canonical_hash({'controls':controls,'physical_states':physical})}
        with tempfile.TemporaryDirectory() as tmp:
            summary=replay_prefix(s,record,Path(tmp),Path(bridge))
            self.assertEqual(summary['rk4']['status'],'complete');self.assertIsNone(summary['rk4']['completed_objective'])
            request=json.loads((Path(tmp)/'rk4/request.json').read_text())
            self.assertEqual(request['scenario']['time']['intervals'],1)
            self.assertEqual(request['full_original_interval_count'],30)
            self.assertEqual(request['full_scenario_sha256'],canonical_hash(s))
            replay=json.loads((Path(tmp)/'rk4/record.json').read_text())
            self.assertAlmostEqual(replay['running_cost_prefix'],.05/30*(.02/.05)**2)

class SavedNMPCTests(unittest.TestCase):
    def test_rebound_objective_normalization_metadata_rejects(self):
        import os,shutil,tempfile,hashlib
        from check_nmpc_saved import check
        from affine import canonical_hash
        source=os.environ.get('CSL_MPC11_NMPC_BUNDLE')
        if not source:self.skipTest('CSL_MPC11_NMPC_BUNDLE required')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'bundle';shutil.copytree(source,root)
            path=root/'syn-nl-lv-01/update-000/result.json';r=json.loads(path.read_text());r['original_interval_count']=1
            r.pop('solve_sha256');r['solve_sha256']=canonical_hash(r);path.write_text(json.dumps(r))
            attempt_path=root/'syn-nl-lv-01/attempt.json';attempt=json.loads(attempt_path.read_text());attempt['updates'][0]['solve_sha256']=r['solve_sha256'];attempt_path.write_text(json.dumps(attempt))
            hp=root/'file-hashes.json';hashes=json.loads(hp.read_text())
            for changed in [path,attempt_path]:hashes[str(changed.relative_to(root))]=hashlib.sha256(changed.read_bytes()).hexdigest()
            hp.write_text(json.dumps(hashes))
            with self.assertRaisesRegex(ValueError,'original_interval_count'):check(root)

class PublicationTests(unittest.TestCase):
    def test_redaction_receipts_reject_changed_native_outcomes(self):
        import os,shutil,tempfile,hashlib
        from check_nmpc_saved import check_publication_redactions
        source=os.environ.get('CSL_MPC11_NMPC_PORTABLE_BUNDLE')
        if not source:self.skipTest('CSL_MPC11_NMPC_PORTABLE_BUNDLE required')
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle';shutil.copytree(source,bundle);check_publication_redactions(bundle)
            receipt_path=bundle/'publication-redactions.json';receipt=json.loads(receipt_path.read_text())
            entry=receipt['files'][0];path=bundle/entry['path'];data=path.read_bytes()
            self.assertIn(b'EXIT: Optimal Solution Found.',data)
            path.write_bytes(data.replace(b'EXIT: Optimal Solution Found.',b'EXIT: Forged Solver Outcome.'))
            entry['published_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'original warning stream recovery'):check_publication_redactions(bundle)

class InventoryTests(unittest.TestCase):
    def test_complete_inventory_mutations_reject(self):
        from check_nmpc_saved import check_update_inventory
        good={'status':'complete','completed_holds':3,'failure':None,'updates':[{'index':j,'accepted':True,'status':'Solve_Succeeded'} for j in range(3)]}
        check_update_inventory(good,3)
        import copy
        for indices in [[],[0,2],[0,1,1],[1,0,2]]:
            bad=copy.deepcopy(good);bad['updates']=[good['updates'][j] for j in indices]
            with self.subTest(indices=indices),self.assertRaises(ValueError):check_update_inventory(bad,3)

    def test_consistent_failed_prefix_inventory(self):
        from check_nmpc_saved import check_update_inventory
        prefix={'status':'incomplete','completed_holds':1,'failure':{'kind':'solve-rejected','update':1},'updates':[
            {'index':0,'accepted':True,'status':'Solve_Succeeded'},{'index':1,'accepted':False,'status':'Maximum_Iterations_Exceeded'}]}
        check_update_inventory(prefix,3)
        prefix['updates'][1]['accepted']=True
        with self.assertRaises(ValueError):check_update_inventory(prefix,3)
        prefix['failure']={'kind':'execution-model-domain-error','update':1}
        check_update_inventory(prefix,3)
        prefix['updates'].append({'index':2,'accepted':False})
        with self.assertRaises(ValueError):check_update_inventory(prefix,3)

    def test_empty_inventory_rebound_saved_attempt_rejects(self):
        import os,shutil,tempfile,hashlib
        from check_nmpc_saved import check
        source=os.environ.get('CSL_MPC11_NMPC_BUNDLE')
        if not source:self.skipTest('CSL_MPC11_NMPC_BUNDLE required')
        with tempfile.TemporaryDirectory() as tmp:
            bundle=Path(tmp)/'bundle';shutil.copytree(source,bundle)
            hashes=json.loads((bundle/'file-hashes.json').read_text())
            for case in ['lv','fuel']:
                path=bundle/f'syn-nl-{case}-01/attempt.json';r=json.loads(path.read_text());r['updates']=[];path.write_text(json.dumps(r))
                hashes[str(path.relative_to(bundle))]=hashlib.sha256(path.read_bytes()).hexdigest()
            (bundle/'file-hashes.json').write_text(json.dumps(hashes))
            with self.assertRaisesRegex(ValueError,'coverage'):check(bundle)

class NativeOutcomeTests(unittest.TestCase):
    def test_native_exit_iterations_and_valid_failure(self):
        from check_nmpc_saved import check_native_solver_log
        r={'status':'Solve_Succeeded','success':True,'iteration_count':9}
        good='Number of Iterations....: 9\nEXIT: Optimal Solution Found.\n'
        check_native_solver_log(good,r)
        for bad in [good.replace('Optimal Solution Found.','Maximum Number of Iterations Exceeded.'),good.replace(': 9',': 8'),'']:
            with self.assertRaises(ValueError):check_native_solver_log(bad,r)
        check_native_solver_log('Number of Iterations....: 0\nEXIT: Maximum Number of Iterations Exceeded.\n',{'status':'Maximum_Iterations_Exceeded','success':False,'iteration_count':0})

    def test_native_rows_and_exposed_iteration_series(self):
        from check_nmpc_saved import check_native_solver_log
        keys=['alpha_du','alpha_pr','d_norm','inf_du','inf_pr','mu','obj','regularization_size']
        r={'status':'Solve_Succeeded','success':True,'iteration_count':1,'solver_iterations':{key:[0.,0.] for key in keys}}
        log=' 0 0.0\n 1 0.0\nNumber of Iterations....: 1\nEXIT: Optimal Solution Found.\n'
        check_native_solver_log(log,r)
        with self.assertRaises(ValueError):check_native_solver_log(log.replace(' 1 0.0',' 8 0.0'),r)
        r['solver_iterations']['obj']=[]
        with self.assertRaises(ValueError):check_native_solver_log(log,r)

    def test_complete_process_and_manifest_bindings(self):
        from check_nmpc_saved import check_process_outcome
        attempt={'case_id':'LV','status':'complete','completed_holds':3}
        process={'process_status':'completed','return_code':0,'whole_process_seconds':1.}
        case={'case_id':'LV','status':'complete','completed_holds':3,'process':process.copy()}
        check_process_outcome(attempt,process,case)
        import copy
        for target in ['process','manifest']:
            bad_process=copy.deepcopy(process);bad_case=copy.deepcopy(case)
            if target=='process':bad_process.update(process_status='timed_out',return_code=None)
            else:bad_case['status']='incomplete'
            with self.assertRaises(ValueError):check_process_outcome(attempt,bad_process,bad_case)
        prefix={'case_id':'LV','status':'incomplete','completed_holds':1,'failure':{'kind':'solve-rejected','update':1}}
        failed={'process_status':'failed','return_code':1,'whole_process_seconds':1.}
        check_process_outcome(prefix,failed,{'case_id':'LV','status':'incomplete','completed_holds':1,'process':failed})

class SavedNativeOutcomeTests(unittest.TestCase):
    def test_rebound_native_process_manifest_mutations_reject(self):
        import os,shutil,tempfile,hashlib
        from check_nmpc_saved import check
        source=os.environ.get('CSL_MPC11_NMPC_BUNDLE')
        if not source:self.skipTest('CSL_MPC11_NMPC_BUNDLE required')
        for mutation in ['process','native-exit','iterations','manifest']:
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)/'bundle';shutil.copytree(source,root)
                if mutation=='process':
                    path=root/'syn-nl-lv-01/process.json';r=json.loads(path.read_text());r.update(process_status='timed_out',return_code=None);path.write_text(json.dumps(r))
                elif mutation=='manifest':
                    path=root/'manifest.json';r=json.loads(path.read_text());r['cases'][0]['status']='incomplete';path.write_text(json.dumps(r))
                else:
                    path=root/'syn-nl-lv-01/update-000/solver.log';text=path.read_text()
                    if mutation=='native-exit':text=text.replace('EXIT: Optimal Solution Found.','EXIT: Maximum Number of Iterations Exceeded.')
                    else:
                        import re
                        text=re.sub(r'(Number of Iterations\.*:)\s*\d+',r'\g<1> 999',text)
                    path.write_text(text)
                hp=root/'file-hashes.json';hashes=json.loads(hp.read_text());hashes[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest();hp.write_text(json.dumps(hashes))
                with self.assertRaises(ValueError):check(root)

if __name__=='__main__':unittest.main()
