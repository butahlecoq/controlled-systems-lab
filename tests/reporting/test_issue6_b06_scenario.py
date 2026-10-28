import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"/"reports"/"issue6"))
sys.path.insert(0,str(ROOT/"scripts"/"reports"))
import scenario_contract
import b06_manifest_correction_registered_reports as correction_publisher

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

    def test_publication_gate_rejects_drift_from_canonical_fixture(self):
        bundle=ROOT/"reports/algorithm-results/b06-manifest-correction-v1"
        correction=json.loads((bundle/"manifest-correction.json").read_text())
        source=correction["measured_driver_snapshot"]
        self.assertEqual(source,"measured-source/b06_finite_minimax.cpp")
        import hashlib
        self.assertEqual(hashlib.sha256((bundle/source).read_bytes()).hexdigest(),
                         correction["measured_driver_sha256"])
        oracle_source=correction["independent_oracle_source_snapshot"]
        self.assertEqual(oracle_source,"measured-source/b06_exact_oracle.cpp")
        self.assertEqual(hashlib.sha256((bundle/oracle_source).read_bytes()).hexdigest(),
                         correction["independent_oracle_sha256"])
        with tempfile.TemporaryDirectory() as temporary:
            canonical=Path(temporary)/"canonical.json"
            canonical.write_bytes(SCENARIO.read_bytes())
            correction_publisher.validate_canonical_fixture(bundle,canonical)
            changed=json.loads(canonical.read_text())
            changed["model"]["A_row_major"][13]="1"
            canonical.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError,"differs from the canonical executable fixture"):
                correction_publisher.validate_canonical_fixture(bundle,canonical)

    def test_publication_gate_rejects_changed_measured_driver_snapshot(self):
        source=ROOT/"reports/algorithm-results/b06-manifest-correction-v1"
        with tempfile.TemporaryDirectory() as temporary:
            bundle=Path(temporary)/source.name
            import shutil
            shutil.copytree(source,bundle)
            driver=bundle/"measured-source/b06_finite_minimax.cpp"
            driver.write_bytes(driver.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError,"source file hash mismatch"):
                correction_publisher.adapt(bundle)

    def test_saved_capture_audit_works_without_repository_history(self):
        source=ROOT/"reports/algorithm-results/b06-owner-confirmed-7df01ba3af5e4c46"
        with tempfile.TemporaryDirectory() as temporary:
            checkout=Path(temporary)/"checkout"
            (checkout/"scripts/reports/issue6").mkdir(parents=True)
            (checkout/"tests/fixtures/reports").mkdir(parents=True)
            (checkout/"benchmarks/scenarios").mkdir(parents=True)
            (checkout/"reports/algorithm-results").mkdir(parents=True)
            for name in ("check_capture.py","scenario_contract.py"):
                shutil.copy2(ROOT/"scripts/reports/issue6"/name,checkout/"scripts/reports/issue6"/name)
            shutil.copytree(ROOT/"tests/fixtures/reports/b06-measured-source",
                            checkout/"tests/fixtures/reports/b06-measured-source")
            shutil.copy2(SCENARIO,checkout/"benchmarks/scenarios"/SCENARIO.name)
            bundle=checkout/"reports/algorithm-results"/source.name
            shutil.copytree(source,bundle)
            for suffix in (".zip",".manifest.sha256"):
                shutil.copy2(source.parent/(source.name+suffix),bundle.parent/(source.name+suffix))
            result=subprocess.run([sys.executable,
                str(checkout/"scripts/reports/issue6/check_capture.py"),str(bundle)],
                cwd=checkout,capture_output=True,text=True,check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('"status": "passed"',result.stdout)


if __name__=="__main__":unittest.main()
