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

    def test_malformed_nonfinite_and_empty_relations_are_rejected(self):
        for mutation in ('width','nan','empty'):
            h=relation(2,False)
            if mutation=='width':h['equalities'][0].pop()
            elif mutation=='nan':h['upper_bounds'][0]=float('nan')
            else:h['equality_values'][0]=1
            with self.assertRaises(ValueError):CHECKER.verify_family(h,2,1)

if __name__=='__main__':unittest.main()
