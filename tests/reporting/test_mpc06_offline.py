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

if __name__=='__main__':unittest.main()

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
