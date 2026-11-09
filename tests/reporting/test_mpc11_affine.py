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


    def test_condensed_program_preserves_joint_cost_dynamics_and_bounds(self):
        scenario = json.loads((ROOT/'benchmarks/reporting/mpc11/scenarios/syn-nl-lv-01.json').read_text())
        data = MODULE.model(scenario); joint = MODULE.program(scenario, data)
        result = MODULE.condense_program(scenario, data, joint)
        u = np.linspace(.1, .9, len(result['variables']))
        x = np.array(result['joint_reconstruction']['matrix'])@u+result['joint_reconstruction']['offset']
        original_cost = .5*np.dot(joint['q_diagonal'],x**2)+np.dot(joint['linear'],x)+joint['offset']
        reduced_cost = .5*u@np.array(result['q_matrix'])@u+np.dot(result['linear'],u)+result['offset']
        self.assertAlmostEqual(original_cost,reduced_cost,places=12)
        self.assertGreater(np.linalg.eigvalsh(result['q_matrix'])[0],0)
        row=joint['constraints']
        for i, bound in enumerate(joint['rows']):
            value=sum(row['values'][k]*x[row['column_indices'][k]] for k in range(row['row_offsets'][i],row['row_offsets'][i+1]))
            self.assertAlmostEqual(value,bound[0],places=12)
        self.assertEqual(result['joint_reconstruction']['variables'],joint['variables'])


    def test_uniform_objective_scaling_preserves_constraints_and_cost_map(self):
        original = {'program_id':'small','program_sha256':'old','q_diagonal':[2.,4.],
                    'linear':[-3.,1.],'offset':5.,'variables':[[0,1],[0,2]],'rows':[],
                    'constraints':{'rows':0,'cols':2,'row_offsets':[0],'column_indices':[],'values':[]}}
        result = MODULE.scale_objective(original,1000.)
        point = np.array([.25,1.25])
        cost = lambda q: .5*np.dot(q['q_diagonal'],point**2)+np.dot(q['linear'],point)+q['offset']
        self.assertAlmostEqual(cost(result)/result['objective_multiplier'],cost(original))
        self.assertEqual(result['constraints'],original['constraints'])
        self.assertEqual(result['variables'],original['variables'])
        for invalid in [0.,-1.,float('inf')]:
            with self.assertRaises(ValueError):MODULE.scale_objective(original,invalid)



if __name__ == '__main__':
    unittest.main()
