import copy
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('build_phase_checker',ROOT/'benchmarks/reporting/review05/check_build_phases.py')
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class BuildPhaseChecks(unittest.TestCase):
    def record(self):
        spans=[]
        names=('strategy-b/program-build','strategy-b/joint-h-assembly','strategy-b/objective-lift','strategy-b/program-freeze')
        for i,(name,start,end) in enumerate(zip(names,(0,1,4,7),(10,3,6,9))):
            spans.append({'id':2 if i==0 else i+3,'parent':0 if i==0 else 2,'operation':name,
                'completed':True,'termination':'completed','start_tick':start,'end_tick':end,'ticks':end-start,
                'input_size':5 if i==1 else 1 if i==2 else 11 if i==3 else None,
                'output_size':11 if i==1 else 5 if i else None})
        return {'strategy':'csl.synthesis.strategy-b','horizon':2,'instrumented':True,'termination':'completed',
            'synthesis_timing':{'period_numerator':1,'period_denominator':1000000000,'spans':spans}}

    def test_observed_nested_build_phases_have_explicit_residual(self):
        result=MODULE.check_phases(self.record())
        self.assertEqual(result['build_ticks'],10)
        self.assertEqual(result['joint_h_assembly_ticks'],2)
        self.assertEqual(result['program_freeze_ticks'],2)
        self.assertEqual(result['build_residual_ticks'],4)

    def test_declared_but_uncalled_or_overlapping_phases_are_not_measurements(self):
        for kind in ('uncalled','overlap','wrong_size','wrong_parent'):
            record=self.record()
            if kind=='uncalled':record['synthesis_timing']['spans'][1]['completed']=False
            elif kind=='overlap':record['synthesis_timing']['spans'][2]['start_tick']=2
            elif kind=='wrong_size':record['synthesis_timing']['spans'][1]['output_size']=1
            else:record['synthesis_timing']['spans'][3]['parent']=0
            with self.assertRaises(ValueError):MODULE.check_phases(record)

    def test_disabled_collection_and_resource_stops_remain_explicit(self):
        record=self.record();record['instrumented']=False;record['synthesis_timing']=None
        self.assertEqual(MODULE.check_phases(record)['status'],'unobserved')
        record=self.record();record['termination']='resource_limit'
        result=MODULE.check_phases(record)
        self.assertEqual(result['status'],'observed-build-with-later-stop')

if __name__=='__main__':unittest.main()
