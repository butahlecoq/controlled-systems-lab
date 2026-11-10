from pathlib import Path
from fractions import Fraction as Q
import copy
import unittest
from scripts.reports.mpc06_offline import builder

class OfflineBuilderTests(unittest.TestCase):
    def test_actual_consumer_gets_exact_canonical_bounds(self):
        data=builder.input_record();artifact=builder.construct(data)
        self.assertEqual(artifact['F'],[[Q(1),Q(1)],[Q(-1),Q(-1)]])
        self.assertEqual(artifact['tightenings'],[(Q(7,8),Q(3,4),Q(5,8))]*3)
        self.assertEqual(artifact['terminal'],[Q(0),Q(0)])
        result=builder.verify(data,artifact);self.assertEqual(result['native_input_matches'],3)
    def test_independent_certificate_rejects_changes(self):
        data=builder.input_record();original=builder.construct(data)
        for mode in ('gain','generator','support','terminal'):
            changed=copy.deepcopy(original)
            if mode=='gain':changed['K'][0]=0
            elif mode=='generator':changed['generators'][0][0]+=Q(1,16)
            elif mode=='support':changed['tightenings'][0]=(Q(1),Q(1),Q(1))
            else:changed['terminal'][0]=Q(1)
            with self.subTest(mode=mode),self.assertRaises(ValueError):builder.verify(data,changed)


class TimingBoundaryTests(unittest.TestCase):
    def test_actual_work_failure_and_nested_clock_guards(self):
        from unittest.mock import patch
        from scripts.reports.mpc06_offline import study,check
        data=builder.input_record();row=study.episode(data,0)
        self.assertEqual(check.replay_episode(data,row)['native_input_matches'],3)
        for mode in ('missing','clock','artifact'):
            changed=copy.deepcopy(row)
            if mode=='missing':changed['construction_ns']=None
            elif mode=='clock':changed['construction_ns']=changed['episode_ns']+1
            else:
                import json
                value=json.loads(changed['artifact_json']);value['K'][0]='0';changed['artifact_json']=builder.encoded(value).decode();changed['artifact_sha256']=study.sha(changed['artifact_json'].encode())
            with self.subTest(mode=mode),self.assertRaises(ValueError):check.replay_episode(data,changed)
        with patch.object(builder,'construct',side_effect=ValueError('construction refusal')):failed=study.episode(data,0)
        self.assertEqual(failed['status'],'failed');self.assertIsNone(failed['construction_ns']);self.assertEqual(check.replay_episode(data,failed)['status'],'retained-failed-construction')
    def test_process_contradiction_and_posix_admission_refuse(self):
        import tempfile
        from unittest.mock import patch
        from scripts.reports.mpc06_offline import study,check
        row=dict(status='completed',return_code=0,timed_out=True,whole_process_ns=100,limits=study.LIMITS,user_cpu_seconds=0,system_cpu_seconds=0,peak_rss_kib=1)
        with self.assertRaisesRegex(ValueError,'contradictory'):check.coherent_process(row)
        with tempfile.TemporaryDirectory() as tmp,patch.object(study,'resource',None):
            path=Path(tmp)/'out'
            with self.assertRaisesRegex(ValueError,'POSIX'):study.capture(path)
            self.assertFalse(path.exists())

class SavedEvidenceTests(unittest.TestCase):
    def test_saved_work_and_forged_source_process_clock_inputs(self):
        import hashlib,json,subprocess,tempfile,zipfile
        from scripts.reports.mpc06_offline import check
        artifact=Path(__file__).resolve().parents[2]/'reports/algorithm-results/mpc06-offline-costs-8f58473d-20261110'
        for mode in ('original','source-map','source-bytes','inputs','clock','process','resource'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(artifact/'capture.zip') as z:z.extractall(tmp)
                root=Path(tmp)/'capture'
                if mode=='source-map':
                    p=root/'environment.json';r=json.loads(p.read_bytes());r['source_sha256']={};p.write_text(json.dumps(r))
                elif mode=='source-bytes':
                    name='scripts/reports/mpc06_offline/builder.py';p=root/'source'/name;p.write_bytes(p.read_bytes()+b'\n# renewed source\n');e=root/'environment.json';r=json.loads(e.read_bytes());r['source_sha256'][name]=hashlib.sha256(p.read_bytes()).hexdigest();e.write_text(json.dumps(r))
                elif mode=='inputs':
                    p=root/'inputs.json';p.write_bytes(p.read_bytes()+b'\n');e=root/'environment.json';r=json.loads(e.read_bytes());r['input_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();e.write_text(json.dumps(r))
                elif mode=='clock':
                    p=root/'measured/stdout.jsonl';rows=[json.loads(line) for line in p.read_text().splitlines()];rows[1]['construction_ns']=rows[1]['episode_ns']+1;p.write_text(''.join(json.dumps(v)+'\n' for v in rows));e=root/'measured/process.json';r=json.loads(e.read_bytes());r['stdout_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();e.write_text(json.dumps(r))
                elif mode=='process':
                    p=root/'measured/process.json';r=json.loads(p.read_bytes());r['timed_out']=True;p.write_text(json.dumps(r))
                if mode=='resource':
                    p=root/'measured/stdout.jsonl';p.write_bytes(b'partial worker output');e=root/'measured/process.json';r=json.loads(e.read_bytes());r.update(status='failed',return_code=-9,timed_out=False,stdout_sha256=hashlib.sha256(p.read_bytes()).hexdigest());e.write_text(json.dumps(r))
                (root/'SHA256SUMS').write_text(''.join(h+'  '+n+'\n' for n,h in check.inventory(root).items()))
                if mode=='original':self.assertEqual(check.checked_receipt(root,artifact/'verification.json')['status'],'verified')
                elif mode=='resource':self.assertEqual(check.check(root)['status'],'inconclusive')
                else:
                    with self.assertRaises(ValueError):check.check(root)

class PublicationTests(unittest.TestCase):
    def test_checked_extension_and_outside_checkout_source_proof(self):
        import json,subprocess,sys,tempfile,zipfile,os
        from scripts.reports import stage_mpc06_offline_costs as publication
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);site=root/'site';(site/'examples').mkdir(parents=True)
            for p in (site/'index.html',site/'examples/index.html'):p.write_text('<html><body>existing</body></html>')
            route=publication.stage(site)
            self.assertIn(route+'/index.html#offline-example',(site/'examples/index.html').read_text())
            with zipfile.ZipFile(site/(route+'.zip')) as z:z.extractall(root/'outside')
            offline=root/'outside'/route
            environment={k:v for k,v in os.environ.items() if k not in ('GIT_DIR','GIT_WORK_TREE','GIT_OBJECT_DIRECTORY','GIT_ALTERNATE_OBJECT_DIRECTORIES')};environment.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_NOSYSTEM='1')
            result=subprocess.run([sys.executable,'-B','offline_check.py'],cwd=offline,env=environment,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['status'],'verified')
            proof=next((offline/'source-root/.git/objects').glob('*/*'));proof.write_bytes(proof.read_bytes()+b'changed')
            refused=subprocess.run([sys.executable,'-B','offline_check.py'],cwd=offline,capture_output=True,text=True,timeout=30);self.assertNotEqual(refused.returncode,0)
    def test_changed_report_refuses_before_writes(self):
        import shutil,tempfile
        from scripts.reports import stage_mpc06_offline_costs as publication
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/publication.SOURCE.name;shutil.copytree(publication.SOURCE,source);p=source/'verification.json';p.write_bytes(p.read_bytes()+b' ')
            site=root/'site';(site/'examples').mkdir(parents=True)
            for p in (site/'index.html',site/'examples/index.html'):p.write_text('<html><body>existing</body></html>')
            before=(site/'index.html').read_bytes()
            with self.assertRaises(ValueError):publication.stage(site,source=source)
            self.assertEqual((site/'index.html').read_bytes(),before);self.assertEqual(len(list(site.iterdir())),2)

if __name__=='__main__':unittest.main()
