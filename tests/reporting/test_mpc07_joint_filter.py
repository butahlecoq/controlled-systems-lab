from pathlib import Path
import importlib.util
from fractions import Fraction as Q
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'benchmarks/reporting/mpc07'))
import joint_filter as J

class JointFilterTests(unittest.TestCase):
    def test_physical_exact_lower_bound_and_filter_gain(self):
        self.assertEqual(J.oracle(2,'joint'),Q(65,64)**2)
        self.assertEqual(J.oracle(8,'joint'),Q(65,64)**14)
        self.assertLess(J.oracle(2,'joint'),Q(9,4))

    def test_canonical_policy_proves_causal_filter_inclusion(self):
        s,h=J.canonical(4)
        checked=J.check_policy(4,'joint',s,h)
        self.assertEqual(checked['virtual_terminal_squared'],J.oracle(4,'joint'))
        self.assertTrue(all(row[0]>=Q(1,1024) for row in s))
        s[1][1]=Q(1)
        with self.assertRaisesRegex(ValueError,'uncertainty'):J.check_policy(4,'joint',s,h)

    def test_noninvertible_and_future_access_refuse(self):
        for mode in ('zero','future'):
            s,h=J.canonical(2)
            if mode=='zero':s[0][0]=0
            else:h[0][3]=1
            with self.assertRaises(ValueError):J.check_policy(2,'joint',s,h)

    def test_joint_filter_has_design_variables_and_fixed_intersection(self):
        p=J.program(2,'joint');f=J.program(2,'fixed-filter')
        self.assertEqual(len(p['coordinates']['filter']),2)
        self.assertNotEqual(p['variables'],f['variables'])
        self.assertEqual(p['profile']['physical_delta_bound'],'1/64')

if __name__=='__main__':unittest.main()
