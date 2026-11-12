import importlib.util
from fractions import Fraction as Q
from pathlib import Path,PureWindowsPath
import unittest
import copy
import json
import sys
import tempfile
import subprocess
import hashlib
import shutil
from unittest import mock

P=Path(__file__).resolve().parents[2]/'scripts/reports/mpc06_online/model.py'
S=importlib.util.spec_from_file_location('mpc06_online_model',P)
M=importlib.util.module_from_spec(S)
S.loader.exec_module(M)


def online_module(name,dependencies=None):
    spec=importlib.util.spec_from_file_location('test_mpc06_online_'+name,P.with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules,dependencies or {}):spec.loader.exec_module(module)
    return module


ONLINE_EVIDENCE=online_module('evidence')
ONLINE_STUDY=online_module('study',{'model':M})
ONLINE_CHECK=online_module('check',{'model':M,'study':ONLINE_STUDY,'evidence':ONLINE_EVIDENCE})
ONLINE_RENDER=online_module('render',{'evidence':ONLINE_EVIDENCE})

class OnlineTubeTests(unittest.TestCase):
    def test_saved_anchor_receipt_uses_its_captured_review_tools(self):
        root=P.parents[3]
        report=root/'reports/algorithm-results/mpc06-online-anchor-portable-v3'
        bundle=report/'checked-inputs/mpc06-online-anchor-v1'
        record,receipt=ONLINE_EVIDENCE.checked_sources(bundle,report/'verification-v2.json')
        self.assertEqual(receipt['source_report_id'],bundle.name)
        self.assertEqual(receipt['verification']['status'],'verified')
        self.assertNotEqual(receipt['checked_sources'],ONLINE_EVIDENCE.tool_bindings())

    def test_saved_anchor_rejects_coordinated_checker_receipt_and_manifest_rewrite(self):
        root=P.parents[3]/'reports/algorithm-results/mpc06-online-anchor-portable-v3'
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/root.name
            shutil.copytree(root,report)
            tool=report/'review-tools/model.py'
            tool.write_bytes(tool.read_bytes()+b'\n# coordinated provenance rewrite\n')
            receipt_path=report/'verification-v2.json'
            receipt=json.loads(receipt_path.read_text())
            receipt['checked_sources']['model.py']=ONLINE_EVIDENCE.digest(tool.read_bytes())
            receipt['receipt_sha256']=ONLINE_EVIDENCE.receipt_id(receipt)
            receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
            files=sorted(path for path in report.rglob('*') if path.is_file() and path!=report/'SHA256SUMS')
            (report/'SHA256SUMS').write_text(''.join(
                f"{ONLINE_EVIDENCE.digest(path.read_bytes())}  {path.relative_to(report).as_posix()}\n"
                for path in files))
            bundle=report/'checked-inputs/mpc06-online-anchor-v1'
            with self.assertRaisesRegex(ValueError,'reviewed report manifest binding'):
                ONLINE_EVIDENCE.checked_sources(bundle,receipt_path)

    def test_terminal_elimination_and_unique_nominal_optimum(self):
        for p,q in [(Q(1,8),Q(0)),(Q(-1,4),Q(1,8)),(Q(0),Q(0))]:
            qp=M.problem((p,q),M.tightenings('polytope'))
            a=M.optimizer(qp)
            states,controls=M.plan((p,q),a)
            self.assertEqual(states[-1],(0,0))
            self.assertGreater(qp['quadratic'],0)
            self.assertTrue(M.feasible_plan(states,controls,M.tightenings('polytope')))
            derivative=2*qp['quadratic']*a+qp['linear']
            self.assertTrue(derivative==0 or (a==qp['lower'] and derivative>=0) or (a==qp['upper'] and derivative<=0))

    def test_finite_error_reference_contains_invariant_tube_feasible_set(self):
        for p in map(lambda x:Q(x,8),range(-4,5)):
            for q in map(lambda x:Q(x,8),range(-4,5)):
                tube=M.problem((p,q),M.tightenings('polytope'))
                exact=M.problem((p,q),M.tightenings('finite-reference'))
                if tube['feasible']:
                    self.assertTrue(exact['feasible'])
                    self.assertLessEqual(exact['lower'],tube['lower'])
                    self.assertGreaterEqual(exact['upper'],tube['upper'])
                    self.assertLessEqual(M.value(exact,M.optimizer(exact)),M.value(tube,M.optimizer(tube)))

    def test_global_error_clock_is_not_reset_by_reoptimization(self):
        self.assertEqual(M.tightenings("finite-reference",2),M.tightenings("polytope"))
        self.assertNotEqual(M.tightenings("finite-reference",1),M.tightenings("finite-reference",0))

    def test_exact_reference_endpoints_replay_all_disturbances_and_exterior_fails(self):
        initial=(Q(1,8),Q(0))
        qp=M.problem(initial,M.tightenings('finite-reference'))
        for a in (qp['lower'],qp['upper']):
            _,controls=M.plan(initial,a)
            self.assertTrue(all(p['safe'] for p in M.replay(initial,controls)['paths']))
        for a in (qp['lower']-Q(1,64),qp['upper']+Q(1,64)):
            _,controls=M.plan(initial,a)
            self.assertTrue(any(not p['safe'] for p in M.replay(initial,controls)['paths']))

    def test_outer_error_enclosure_does_not_imply_rpi(self):
        checks=M.representation_checks()
        for kind in ('polytope','zonotope','parallelotope','inflated-zonotope','ellipsoid-certified'):
            self.assertTrue(checks[kind]['contains_exact_Z'])
            self.assertTrue(checks[kind]['rpi'])
        for kind in ('box','ellipsoid-app04'):
            self.assertTrue(checks[kind]['contains_exact_Z'])
            self.assertFalse(checks[kind]['rpi'])
            self.assertIn('counterexample',checks[kind])
            with self.assertRaises(ValueError):M.tightenings(kind)

    def test_empty_tightening_and_infeasible_anchor_remain_failures(self):
        self.assertFalse(M.problem((Q(2),Q(0)),M.tightenings('polytope'))['feasible'])
        self.assertFalse(M.problem((Q(0),Q(0)),[(-Q(1),-Q(1),-Q(1))]*3)['feasible'])

    def test_exact_vertex_worst_cost_is_policy_specific(self):
        result=M.replay((Q(1,8),Q(0)),[Q(0),Q(1,16),Q(-1,16)])
        self.assertEqual(len(result['paths']),8)
        self.assertEqual(result['worst'],max(row['cost'] for row in result['paths']))
        for row in result['paths']:
            self.assertTrue(row['safe'])
        with self.assertRaises(ValueError):M.replay((Q(0),Q(0)),[Q(0)]*3,policy='measured-state-reset')

class OnlineCaptureTests(unittest.TestCase):
    @unittest.skipIf(sys.platform=="win32","POSIX subprocess fixture; native smoke separately exercises Windows")
    def test_saved_native_protocol_is_bound_and_replay_detects_corruption(self):
        study,check,evidence=ONLINE_STUDY,ONLINE_CHECK,ONLINE_EVIDENCE
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);driver=folder/'fixture-driver'
            driver.write_text("""#!/usr/bin/env python3
import json,math,sys
print(json.dumps(dict(schema='csl.mpc06-online-approximation/1',direction='outer',radii=[math.sqrt(2)/8]*2,center=[0,0],orientation=[[1,0],[1,1]],construction_ns=1)),flush=True)
for i,line in enumerate(sys.stdin):
 a,b,c,lo,hi=map(float,line.split());x=min(hi,max(lo,-b/(2*a)))
 print(json.dumps(dict(schema='csl.mpc06-online-qp/1',status='completed',backend='csl.convex.highs',backend_version='test-protocol',program='nominal-qp/'+str(i),requested_threads=1,a=x,objective=a*x*x+b*x+c,prepare_ns=1,setup_ns=1,solve_ns=1)),flush=True)
""")
            driver.chmod(0o700)
            path_type=type(folder);relative_to=path_type.relative_to
            def windows_relative(path,*arguments):
                return PureWindowsPath(relative_to(path,*arguments))
            with mock.patch.object(path_type,'relative_to',windows_relative):
                result=study.run(driver,folder/'capture',1)
            self.assertFalse((folder/'capture/source/README.md').exists())
            evidence.load_sources(folder/'capture')
            frozen=json.loads(json.dumps(result,default=study.encode))
            self.assertEqual(check.verify(frozen)['status'],'verified')
            self.assertEqual(check.verify(frozen)['completed_native_qps'],36)
            bundle=folder/'capture'
            (bundle/'verification.json').write_text(json.dumps(check.verify(frozen)))
            files=sorted(p for p in bundle.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
            (bundle/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(bundle).as_posix()}\n' for p in files))
            before=(bundle/'verification.json').read_bytes()
            for _ in range(2):
                subprocess.run([sys.executable,str(P.with_name('check.py')),str(bundle)],check=True,capture_output=True)
            self.assertEqual((bundle/'verification.json').read_bytes(),before)

            corrupt=copy.deepcopy(frozen);corrupt['attempts'][0]['steps'][0]['native']['a']=10
            with self.assertRaisesRegex(ValueError,'optimum'):check.verify(corrupt)
            corrupt=copy.deepcopy(frozen);corrupt['attempts'][0]['steps'][0]['native']['program']='wrong'
            with self.assertRaisesRegex(ValueError,'binding'):check.verify(corrupt)
            corrupt=copy.deepcopy(frozen);corrupt['policy']['kind']='measured-state-reset'
            with self.assertRaisesRegex(ValueError,'policy'):check.verify(corrupt)
            corrupt=copy.deepcopy(frozen);corrupt['attempts'][0]['actual']['worst']='0'
            with self.assertRaisesRegex(ValueError,'cost'):check.verify(corrupt)

class EvidenceBindingTests(unittest.TestCase):
    source=P.parents[3]/'reports/algorithm-results/mpc06-online-anchor-v1'

    def clone(self,folder):
        bundle=Path(folder)/'bundle';shutil.copytree(self.source,bundle);return bundle

    def refresh_manifest(self,bundle):
        files=sorted(p for p in bundle.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
        (bundle/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(bundle).as_posix()}\n' for p in files))

    def receipt(self,bundle,folder):
        path=Path(folder)/'verification-v2.json'
        result=subprocess.run([sys.executable,str(P.with_name('check.py')),str(bundle),'--receipt-output',str(path)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        return path

    def renderer(self,bundle,receipt,output):
        return subprocess.run([sys.executable,str(P.with_name('render.py')),str(bundle),'--receipt',str(receipt),'--output',str(output)],capture_output=True,text=True)

    def test_fixture_checksum_paths_remain_posix_with_windows_relative_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder)
            path_type=type(bundle);relative_to=path_type.relative_to
            def windows_relative(path,*arguments):
                return PureWindowsPath(relative_to(path,*arguments))
            with mock.patch.object(path_type,'relative_to',windows_relative):
                self.refresh_manifest(bundle)
            names=[line.split('  ',1)[1] for line in (bundle/'SHA256SUMS').read_text().splitlines()]
            self.assertIn('source/driver.cpp',names)
            self.assertTrue(all('\\' not in name for name in names))

    def test_rendered_manifest_paths_remain_posix_with_windows_relative_paths(self):
        render=ONLINE_RENDER
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder);receipt=self.receipt(bundle,folder)
            path_type=type(bundle);relative_to=path_type.relative_to
            def windows_relative(path,*arguments):
                return PureWindowsPath(relative_to(path,*arguments))
            output=Path(folder)/'rendered'
            with mock.patch.object(path_type,'relative_to',windows_relative):
                render.render(bundle,receipt,output)
            names=[line.split('  ',1)[1] for line in (output/'SHA256SUMS').read_text().splitlines()]
            self.assertIn('checked-inputs/bundle/source/driver.cpp',names)
            self.assertTrue(all('\\' not in name for name in names))

    def test_replaced_native_stream_is_rejected_even_with_updated_checksums(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder)
            (bundle/'repetition-00/stdout.txt').write_text('NO NATIVE RESPONSES\n')
            self.refresh_manifest(bundle)
            result=subprocess.run([sys.executable,str(P.with_name('check.py')),str(bundle)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0,result.stdout)

    def test_native_app04_response_count_and_order_are_not_inferred_from_labels(self):
        for mutation in ('APP04','order','extra','missing'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                bundle=self.clone(folder);path=bundle/'repetition-00/stdout.txt'
                lines=path.read_text().splitlines()
                if mutation=='APP04':
                    response=json.loads(lines[0]);response['construction_ns']+=1;lines[0]=json.dumps(response)
                elif mutation=='order':lines[1],lines[2]=lines[2],lines[1]
                elif mutation=='extra':lines.append(lines[-1])
                else:lines.pop()
                path.write_text('\n'.join(lines)+'\n');self.refresh_manifest(bundle)
                result=subprocess.run([sys.executable,str(P.with_name('check.py')),str(bundle)],capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('native response stream differs',result.stderr)

    def test_renderer_rejects_changed_timing_without_blessing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder)
            receipt=self.receipt(bundle,folder)
            record=json.loads((bundle/'result.json').read_text())
            record['attempts'][0]['steps'][0]['native']['solve_ns']=10**18
            (bundle/'result.json').write_text(json.dumps(record))
            before=(bundle/'SHA256SUMS').read_bytes()
            output=Path(folder)/'rendered'
            result=self.renderer(bundle,receipt,output)
            self.assertNotEqual(result.returncode,0,result.stdout)
            self.assertFalse(output.exists())
            self.assertEqual((bundle/'SHA256SUMS').read_bytes(),before)

    def test_valid_versioned_render_preserves_original_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder);before={p.relative_to(bundle):p.read_bytes() for p in bundle.rglob('*') if p.is_file()}
            receipt=self.receipt(bundle,folder);receipt_before=receipt.read_bytes()
            output=Path(folder)/'rendered';result=self.renderer(bundle,receipt,output)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue((output/'verification-v2.json').exists())
            captured=(output/'checked-inputs'/bundle.name/'source/README.md').read_bytes()
            self.assertEqual(captured,before[Path('source/README.md')])
            self.assertIn('checked-inputs/'+bundle.name+'/source/README.md',(output/'index.html').read_text())
            subprocess.run([sys.executable,str(output/'review-tools/check.py'),str(output/'checked-inputs'/bundle.name),'--receipt-output',str(output/'verification-v2.json')],check=True,capture_output=True)
            self.assertEqual({p.relative_to(bundle):p.read_bytes() for p in bundle.rglob('*') if p.is_file()},before)
            subprocess.run([sys.executable,str(P.with_name('check.py')),str(bundle),'--receipt-output',str(receipt)],check=True,capture_output=True)
            self.assertEqual(receipt.read_bytes(),receipt_before)

    def test_updated_raw_and_result_timing_still_need_new_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder);receipt=self.receipt(bundle,folder)
            record=json.loads((bundle/'result.json').read_text());native=record['attempts'][0]['steps'][0]['native']
            native['solve_ns']+=1
            (bundle/'result.json').write_text(json.dumps(record))
            path=bundle/'repetition-00/stdout.txt';lines=path.read_text().splitlines()
            lines[1]=json.dumps(native);path.write_text('\n'.join(lines)+'\n');self.refresh_manifest(bundle)
            result=self.renderer(bundle,receipt,Path(folder)/'rendered')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('receipt input binding',result.stderr)

    def test_receipt_count_and_script_binding_are_checked(self):
        evidence=ONLINE_EVIDENCE
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder);receipt=self.receipt(bundle,folder)
            body=json.loads(receipt.read_text());body['verification']['completed_native_qps']+=1
            receipt.write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError,'content binding'):evidence.checked_sources(bundle,receipt)
            body['receipt_sha256']=evidence.receipt_id(body);receipt.write_text(json.dumps(body))
            with self.assertRaisesRegex(ValueError,'disposition binding'):evidence.checked_sources(bundle,receipt)
            body['verification']['completed_native_qps']-=1;body['receipt_sha256']=evidence.receipt_id(body);receipt.write_text(json.dumps(body))
            altered=dict(evidence.tool_bindings());altered['model.py']='0'*64
            with mock.patch.object(evidence,'tool_bindings',return_value=altered):
                with self.assertRaisesRegex(ValueError,'script binding'):evidence.checked_sources(bundle,receipt)

    def test_capture_source_snapshot_is_not_just_a_checksum_label(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle=self.clone(folder);source=bundle/'source/driver.cpp';source.write_text(source.read_text()+'\n// changed\n')
            self.refresh_manifest(bundle)
            result=subprocess.run([sys.executable,str(P.with_name('check.py')),str(bundle)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('source snapshot binding',result.stderr)

if __name__=='__main__':unittest.main()
