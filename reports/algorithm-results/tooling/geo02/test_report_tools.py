"""Focused contract tests for immutable GEO-02 numerical reports."""
import copy, hashlib, json, sys, unittest, tempfile, subprocess, zipfile
from unittest import mock
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import collect,render,provenance
class ContractTests(unittest.TestCase):
 def test_signed_payload_hash_and_tamper_detection(self):
  p=collect.fixture_payload('20261013T000000Z');self.assertEqual(p['schema'],'csl.geo02-affine-sum-report/1');render.validate(p)
  q=copy.deepcopy(p);q['trials'][0]['operation_ns']+=1
  with self.assertRaisesRegex(ValueError,'digest mismatch'):render.validate(q)
 def test_summaries_recompute_from_all_trials_and_fail_closed(self):
  rows=[{'scenario':'scalar_interval_affine_image','repetition':i,'status':'passed','oracle_passed':True,'setup_ns':i+1,'operation_ns':10+i,'oracle_ns':2,'total_ns':20+i} for i in range(7)]
  got=collect.summarize(rows,True)['scalar_interval_affine_image']['phases']['operation_ns'];self.assertEqual((got['median'],got['min'],got['max'],got['range']),(13,10,16,6))
  rows[0]['status']='oracle_failed';self.assertIsNone(collect.summarize(rows,True)['scalar_interval_affine_image']['phases']['operation_ns']['median'])
 def test_independent_oracle_pins_literal_points_and_supports(self):
  self.assertTrue(render.check_oracle('scalar_interval_affine_image',[[-2.0],[0.0],[2.0]]));self.assertFalse(render.check_oracle('scalar_interval_affine_image',[[-2.0],[2.1]]))
  self.assertTrue(render.check_oracle('singular_map_box_segment',[[0,0],[1,2],[1,2],[2,4]]));self.assertFalse(render.check_oracle('singular_map_box_segment',[[0,0],[1,2],[2,3],[2,4]]))
  self.assertTrue(render.check_supports('scalar_interval_affine_image',[2,2]));self.assertFalse(render.check_supports('scalar_interval_affine_image',[2,1.999]))
 def test_safe_render_escapes_untrusted_driver_detail(self):
  p=collect.fixture_payload('20261013T000000Z');p['trials'][0]['detail']='<script>alert(1)</script>';collect.finalize(p,'20261013T000000Z')
  page=render.render_html(p);self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>alert',page);self.assertIn('retains the full candidate cloud',page)
 def test_resigned_fabricated_summary_and_wrong_inputs_are_rejected(self):
  p=collect.fixture_payload('test');p['summary']['scalar_interval_affine_image']['phases']['total_ns']['median']=999;collect.finalize(p,'test')
  with self.assertRaisesRegex(ValueError,'phase summaries'):render.validate(p)
  p=collect.fixture_payload('test');p['trials'][0]['input_sha256']='0'*64;collect.finalize(p,'test')
  with self.assertRaisesRegex(ValueError,'input hash'):render.validate(p)
 def test_bundle_manifest_and_deterministic_offline_zip(self):
  payload=collect.fixture_payload('20261013T000000Z')
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);collection=root/'collection';collection.mkdir();(collection/'records.json').write_text(json.dumps(payload),encoding='utf8')
   for name in ('collection-status.json','raw-events.jsonl','summary.csv','raw-driver-output.csv','build-provenance.txt','measurement-command.txt','environment.json','scenarios.json','profile-evidence.txt','process-stderr.txt','concurrent-work.txt'):(collection/name).write_text('fixture\n',encoding='utf8')
   output=root/'bundle';subprocess.run([sys.executable,str(HERE/'render.py'),'--collection',str(collection),'--out',str(output)],check=True)
   manifest=json.loads((output/'manifest.json').read_text(encoding='utf8'))
   self.assertEqual(manifest['schema'],'csl.geo02-bundle/1')
   self.assertTrue(all(hashlib.sha256((output/name).read_bytes()).hexdigest()==digest for name,digest in manifest['files'].items()))
   archive=root/(payload['report_id']+'.zip')
   with zipfile.ZipFile(archive) as z:self.assertEqual(set(z.namelist()),{x.name for x in output.iterdir()})
 def test_provenance_allows_only_pinned_report_paths_and_cmake_delta(self):
  provenance.validate_harness_paths(['reports/algorithm-results/tooling/geo02/collect.py','scripts/reports/site.py'])
  with self.assertRaisesRegex(ValueError,'allowlist'):provenance.validate_harness_paths(['src/geometry/affine_sum.cpp'])
  source='\n'.join((provenance.GEO04_OPTION,provenance.CMAKE_CONFLICT,provenance.GEO04_TARGET,''))
  expected=provenance.expected_harness_cmake(source)
  provenance.validate_harness_cmake(source,expected)
  with self.assertRaisesRegex(ValueError,'CMakeLists.txt'):provenance.validate_harness_cmake(source,expected+'\nadd_library(unreviewed x.cpp)')
 def test_collector_rejects_unknown_commit_before_build_validation(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary);concurrent=root/'concurrent.txt';profile=root/'profile.txt';concurrent.write_text('none\n',encoding='utf8');profile.write_text('none\n',encoding='utf8')
   args=['collect.py','--exe',str(root/'missing.exe'),'--build-dir',str(root/'build'),'--source-commit','0'*40,'--harness-commit','0'*40,'--concurrent-work',str(concurrent),'--profile-evidence',str(profile),'--out',str(root/'collection'),'--reviewed']
   with mock.patch.object(sys,'argv',args),self.assertRaises(SystemExit) as raised:collect.main()
   self.assertEqual(raised.exception.code,2)
if __name__=='__main__':unittest.main()
