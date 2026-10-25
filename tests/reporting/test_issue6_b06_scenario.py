import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"/"reports"/"issue6"))
import scenario_contract

SCENARIO=ROOT/"benchmarks/scenarios/b06-owner-confirmed-disturbance-v1.json"


class B06ScenarioContractTests(unittest.TestCase):
    def setUp(self):
        self.document=json.loads(SCENARIO.read_text())

    def test_declared_model_dimensions_and_payloads_match_execution_shapes(self):
        model=scenario_contract.validate(self.document)
        self.assertEqual(model["dimensions"],(4,1,2))
        self.assertEqual(model["horizon"],5)
        self.assertEqual(len(model["A"]),16)
        self.assertEqual(len(model["B"]),4)
        self.assertEqual(len(model["D"]),8)
        self.assertEqual(len(model["initial"]),4)

    def test_rejects_the_published_fifteen_entry_matrix_and_each_wrong_payload_shape(self):
        malformed=json.loads(json.dumps(self.document))
        malformed["model"]["A_row_major"].pop(13)
        with self.assertRaisesRegex(ValueError,"A_row_major.*16"):
            scenario_contract.validate(malformed)
        for field,index in (("B",0),("D_row_major",0),("initial_state",0),("offset",0)):
            malformed=json.loads(json.dumps(self.document))
            malformed["model"][field].pop(index)
            with self.assertRaises(ValueError, msg=field):
                scenario_contract.validate(malformed)
        malformed=json.loads(json.dumps(self.document))
        malformed["objective"]["quadratic_terminal"]["Q_row_major"].pop()
        with self.assertRaisesRegex(ValueError,"Q_row_major"):
            scenario_contract.validate(malformed)

    def test_state_transition_matches_the_independent_integer_oracle_recurrence(self):
        model=scenario_contract.validate(self.document)
        n, m, d=model["dimensions"]
        A=[model["A"][i*n:(i+1)*n] for i in range(n)]
        B=[model["B"][i*m:(i+1)*m] for i in range(n)]
        D=[model["D"][i*d:(i+1)*d] for i in range(n)]
        expected_A=[[1,0,0,0],[-2,1,0,0],[0,0,1,0],[0,0,-2,1]]
        expected_B=[[Fraction(7,10)],[0],[Fraction(-1,3)],[0]]
        expected_D=[[Fraction(1,20),0],[0,0],[0,Fraction(-1,25)],[0,0]]
        self.assertEqual(A,expected_A)
        self.assertEqual(B,expected_B)
        self.assertEqual(D,expected_D)
        self.assertEqual(model["offset"],[0,0,0,0])

    def test_canonical_correction_is_only_the_source_verified_missing_zero(self):
        corrected=json.loads(SCENARIO.read_text())["model"]["A_row_major"]
        source_bundle=ROOT/"reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46"
        historical=json.loads((source_bundle/"scenario.json").read_text())["model"]["A_row_major"]
        self.assertEqual(len(historical),15)
        self.assertEqual(corrected[:13],historical[:13])
        self.assertEqual(corrected[14:],historical[13:])
        self.assertEqual(corrected[13],"0")


if __name__=="__main__":unittest.main()
