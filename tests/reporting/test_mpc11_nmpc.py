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

if __name__=='__main__':unittest.main()
