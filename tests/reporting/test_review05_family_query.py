import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('family_query_checker',ROOT/'benchmarks/reporting/review05/check_family_query.py')
CHECKER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


def relation(horizon,flat):
    width=2*horizon+1
    eq=[]
    row=[0]*width;row[0]=1;eq.append(row)
    for t in range(horizon):
        row=[0]*width;row[t+1]=1;row[t]=-1;row[horizon+1+t]=-1;eq.append(row)
    ine=[];bounds=[]
    for t in range(horizon):
        row=[0]*width;row[horizon+1+t]=1;ine.append(row);bounds.append(1)
        row=[-x for x in row];ine.append(row);bounds.append(0)
    if not flat:
        row=[0]*width;row[horizon]=1;ine.append(row);bounds.append(0)
    return {'dimension':width,'inequalities':ine,'upper_bounds':bounds,'equalities':eq,'equality_values':[0]*len(eq)}

class FamilyQueryTests(unittest.TestCase):
    def test_literal_zero_and_cube_optimizer_faces_both_directions(self):
        for t in (2,4,8):
            for flat in (False,True):
                self.assertTrue(CHECKER.verify_family(relation(t,flat),t,0 if flat else 1))

    def test_omitted_optimal_histories_are_rejected(self):
        h=relation(4,True);h['upper_bounds'][0]=0
        with self.assertRaisesRegex(ValueError,'omits'):
            CHECKER.verify_family(h,4,0)

    def test_included_nonoptimal_histories_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'includes'):
            CHECKER.verify_family(relation(4,True),4,1)

    def test_missing_dynamics_or_control_bound_is_not_coverage(self):
        for kind in ('dynamics','bound'):
            h=relation(2,True)
            if kind=='dynamics':h['equalities'].pop();h['equality_values'].pop()
            else:h['inequalities'].pop();h['upper_bounds'].pop()
            with self.assertRaisesRegex(ValueError,'includes'):
                CHECKER.verify_family(h,2,0)

    def test_redundant_scaled_rows_preserve_exact_coverage(self):
        h=relation(4,True)
        h['equalities']=[[2*x for x in row] for row in h['equalities']]
        h['inequalities'].append([3*x for x in h['inequalities'][0]])
        h['upper_bounds'].append(3)
        self.assertTrue(CHECKER.verify_family(h,4,0))

    def test_direction_minimum_uses_the_associated_control_coordinates(self):
        witness={'states':[[0],[0],[1]],'controls':[[0],[1]],'original_objective':0}
        self.assertTrue(CHECKER.verify_query(witness,[1,-1],2,0))
        with self.assertRaisesRegex(ValueError,'direction'):
            CHECKER.verify_query(witness,[-1,1],2,0)
        witness['controls']=[[1],[0]];witness['states']=[[0],[1],[1]]
        with self.assertRaisesRegex(ValueError,'direction'):
            CHECKER.verify_query(witness,[1,-1],2,0)
        self.assertTrue(CHECKER.verify_query(witness,[0,0],2,0))

    def test_structured_attempt_binds_fixture_family_and_actual_query_span(self):
        scenario={'horizon':2,'model':{'kind':'linear_discrete','A':[[1]],'B':[[1]]},
            'initial_state':[0],'controls':{'kind':'box','lower':[0],'upper':[1]},
            'objective':{'kind':'linear','coefficients':[1]}}
        binding={'problem_id':'p','profile':'strategy-a.nominal-linear-exact-v1',
            'strategy':'csl.synthesis.reach-back','strategy_version':'1','lineage':[]}
        record=dict(binding,schema='csl.review05.family-query/1',scenario_sha256='hash',horizon=2,
            fixture='HORIZON-01',target='exact_optimal_relation',termination='completed',selector_termination='completed',
            family_registry_verified=True,outcome='optimal',objective_lower=0,objective_upper=0,family_binding=binding,
            selector_source_bound=True,compiled_verifier={'id':'csl.verifier.strategy-a.nominal-linear-exact','version':'1'},
            relation=relation(2,False),directions=[[1,0],[-1,0],[0,1],[0,-1]],requested_witnesses=1,
            returned_witnesses=1,distinct_witnesses=1,literal_replay_ok=True,instrumented=True,
            witnesses=[{'problem_id':'p','states':[[0],[0],[0]],'controls':[[0],[0]],'original_objective':0}],
            selector_timing={'spans':[{'operation':'selector.lp.direction-query','completed':True,'query':0,
                'program':'witness-selector-direction/0/4607182418800017408/0','termination':'completed',
                'ticks':10,'input_size':5,'output_size':5}]})
        self.assertEqual(CHECKER.verify_attempt(record,scenario,'hash')['status'],'verified')
        for key,value in [('scenario_sha256','wrong'),('selector_source_bound',False)]:
            bad=copy.deepcopy(record);bad[key]=value
            with self.assertRaisesRegex(ValueError,'binding'):CHECKER.verify_attempt(bad,scenario,'hash')
        for key,value in [('query',1),('input_size',9),('program','wrong')]:
            bad=copy.deepcopy(record);bad['selector_timing']['spans'][0][key]=value
            with self.assertRaisesRegex(ValueError,'observation'):CHECKER.verify_attempt(bad,scenario,'hash')
        bad=copy.deepcopy(record);bad['selector_timing']['spans']=[]
        with self.assertRaisesRegex(ValueError,'span'):CHECKER.verify_attempt(bad,scenario,'hash')

    def test_malformed_nonfinite_and_empty_relations_are_rejected(self):
        for mutation in ('width','nan','empty'):
            h=relation(2,False)
            if mutation=='width':h['equalities'][0].pop()
            elif mutation=='nan':h['upper_bounds'][0]=float('nan')
            else:h['equality_values'][0]=1
            with self.assertRaises(ValueError):CHECKER.verify_family(h,2,1)

if __name__=='__main__':unittest.main()
