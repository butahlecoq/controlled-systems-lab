import importlib.util
from pathlib import Path
import unittest
import json
try:
    import numpy as np
    import scipy.linalg
except ModuleNotFoundError as error:
    raise unittest.SkipTest("MPC-11 affine tests require the optional locked NumPy/SciPy environment") from error

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('mpc11_affine', ROOT / 'benchmarks/reporting/mpc11/affine.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AffineTests(unittest.TestCase):
    def test_constant_integrator_exact_discretization(self):
        a, b, c = MODULE.discretize(np.zeros((1, 1)), np.ones((1, 1)), np.array([2.]), .5)
        np.testing.assert_allclose(a, [[1.]])
        np.testing.assert_allclose(b, [[.5]])
        np.testing.assert_allclose(c, [1.])

    def test_authored_quadratic_keeps_running_penalty_and_half_convention(self):
        q, linear, offset = MODULE.tracking_quadratic(3, [1], [2.], [1.], [1.],
                                                     [2], [0.], [1.], [1.], 1., 1)
        self.assertAlmostEqual(.5*np.array([0, 1, 1])@q@np.array([0, 1, 1])+linear@np.array([0, 1, 1])+offset, 2.)
        self.assertAlmostEqual(.5*np.array([0, 2, 2])@q@np.array([0, 2, 2])+linear@np.array([0, 2, 2])+offset, 4.)

    def test_fuel_discrete_offset_reproduces_reference_endpoints(self):
        scenario = json.loads((ROOT/'benchmarks/reporting/mpc11/scenarios/syn-nl-fuel-01.json').read_text())
        data = MODULE.model(scenario)
        for k, stage in enumerate(data['physical_coefficients']):
            next_state = np.array(stage['A'])@data['reference_states'][k]+np.array(stage['B'])@data['reference_commands'][k]+stage['c']
            np.testing.assert_allclose(next_state, data['reference_states'][k+1], atol=1e-12)

    def test_full_joint_program_matches_literal_authored_cost(self):
        for name in ['syn-nl-lv-01', 'syn-nl-fuel-01']:
            scenario = json.loads((ROOT/f'benchmarks/reporting/mpc11/scenarios/{name}.json').read_text())
            data = MODULE.model(scenario)
            qp = MODULE.program(scenario, data)
            n, m, count = len(scenario['states']), len(scenario['controls']), scenario['time']['intervals']
            states = np.tile(scenario['objective']['terminal_target'], (count+1, 1))
            controls = np.array(data['reference_commands'])+.01
            point = np.concatenate([(states/data['state_scale']).reshape(-1), (controls/data['control_scale']).reshape(-1)])
            expanded = .5*np.dot(qp['q_diagonal'], point**2)+np.dot(qp['linear'], point)+qp['offset']
            expected = scenario['objective']['running_weight']/count*np.sum(((controls-data['reference_commands'])/scenario['objective']['running_scale'])**2)
            self.assertGreater(expected, 0)
            self.assertAlmostEqual(expanded, expected, places=12)
            self.assertEqual(len(qp['rows']), n*count)
            self.assertEqual(qp['constraints']['cols'], n*(count+1)+m*count)


    def test_variable_permutation_preserves_cost_bounds_and_rows(self):
        qp = {'q_diagonal':[0.,2.,4.], 'linear':[0.,-4.,1.], 'offset':4.,
              'variables':[[0,0],[-10,10],[-2,2]], 'program_id':'tiny',
              'constraints':{'rows':1,'cols':3,'row_offsets':[0,3], 'column_indices':[0,1,2], 'values':[-1.,1.,-1.]},
              'coordinates':{}, 'program_sha256':'old'}
        result = MODULE.permute_program(qp, [2,0,1])
        old = np.array([0.,1.,1.]); native = old[[2,0,1]]
        np.testing.assert_allclose(native[result['coordinates']['joint_indices']],old)
        def cost(data, point):
            return .5*np.dot(data['q_diagonal'],point**2)+np.dot(data['linear'],point)+data['offset']
        self.assertAlmostEqual(cost(qp,old),cost(result,native))
        row=result['constraints']
        self.assertAlmostEqual(sum(a*native[j] for a,j in zip(row['values'],row['column_indices'])),0.)



if __name__ == '__main__':
    unittest.main()
