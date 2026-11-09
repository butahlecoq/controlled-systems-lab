import hashlib
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
try:
    import scipy.linalg
except ModuleNotFoundError as error:
    raise unittest.SkipTest('MPC-11 saved checks require the optional locked environment') from error

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT/'benchmarks/reporting/mpc11'
sys.path.insert(0,str(MODULE_DIR))
import check_affine_saved as CHECKER
from affine import canonical_hash, model, program, condense_program, permute_program, scale_objective

ARCHIVE = MODULE_DIR/'evidence/affine-pilot-b3978a98/capture.zip'


def write(path, value):
    path.write_text(json.dumps(value,indent=2)+'\n')


class SavedAffineTests(unittest.TestCase):
    def test_original_archive_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with zipfile.ZipFile(ARCHIVE) as archive:archive.extractall(root)
            self.assertTrue(all(row['status']=='verified-numerical-witness' for row in CHECKER.check(root/'accepted')))

    def test_rebound_source_offset_row_or_bound_is_rejected(self):
        for mutation in ['offset','row','control-bound']:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                with zipfile.ZipFile(ARCHIVE) as archive:archive.extractall(root)
                bundle=root/'accepted';folder=bundle/'syn-nl-lv-01'
                unscaled=json.loads((folder/'unscaled-program.json').read_text())
                if mutation=='offset':unscaled['offset']+=100
                elif mutation=='row':unscaled['constraints']['values'][0]+=.25
                else:unscaled['variables'][-1][1]+=.25
                unscaled.pop('program_sha256');unscaled['program_sha256']=canonical_hash(unscaled)
                write(folder/'unscaled-program.json',unscaled)
                qp=json.loads((folder/'program.json').read_text());qp['source_unscaled_program_sha256']=unscaled['program_sha256']
                qp.pop('program_sha256');qp['program_sha256']=canonical_hash(qp);write(folder/'program.json',qp)
                result=json.loads((folder/'stdout.json').read_text());result['program_sha256']=qp['program_sha256'];write(folder/'stdout.json',result)
                manifest=json.loads((bundle/'manifest.json').read_text())
                row=next(item for item in manifest['attempts'] if item['case_id']=='SYN-NL-LV-01')
                row['program_sha256']=qp['program_sha256']
                row['program_file_sha256']=hashlib.sha256((folder/'program.json').read_bytes()).hexdigest()
                row['stdout_sha256']=hashlib.sha256((folder/'stdout.json').read_bytes()).hexdigest();write(bundle/'manifest.json',manifest)
                with self.assertRaises(ValueError):CHECKER.check(bundle)

    def test_rebuilt_transforms_reject_mapping_or_scaling_changes(self):
        scenario=json.loads((MODULE_DIR/'scenarios/syn-nl-lv-01.json').read_text())
        coefficients=model(scenario);joint=program(scenario,coefficients)
        n=len(scenario['states'])*(scenario['time']['intervals']+1)
        variants={'permutation':permute_program(joint,[*range(n,len(joint['variables'])),*range(n)]),
                  'condensed':condense_program(scenario,coefficients,joint),
                  'scaled':scale_objective(joint,1000.)}
        for name,qp in variants.items():
            with self.subTest(transform=name), tempfile.TemporaryDirectory() as directory:
                folder=Path(directory);write(folder/'joint-program.json',joint);write(folder/'unscaled-program.json',joint)
                CHECKER.verify_authored_transform(scenario,coefficients,qp,folder)
                bad=copy.deepcopy(qp)
                if name=='permutation':bad['coordinates']['joint_indices'][0]+=1
                elif name=='condensed':bad['joint_reconstruction']['matrix'][0][0]+=.125
                else:bad['q_diagonal'][-1]*=1.25
                bad.pop('program_sha256');bad['program_sha256']=canonical_hash(bad)
                with self.assertRaises(ValueError):CHECKER.verify_authored_transform(scenario,coefficients,bad,folder)

    def test_rebuild_rejects_changed_model_declaration(self):
        scenario=json.loads((MODULE_DIR/'scenarios/syn-nl-lv-01.json').read_text())
        coefficients=model(scenario);qp=program(scenario,coefficients)
        coefficients['physical_coefficients'][0]['jacobian_A'][0][0]+=.1
        qp['model_sha256']=canonical_hash(coefficients);qp.pop('program_sha256');qp['program_sha256']=canonical_hash(qp)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):CHECKER.verify_authored_transform(scenario,coefficients,qp,Path(directory))



if __name__=='__main__':unittest.main()
