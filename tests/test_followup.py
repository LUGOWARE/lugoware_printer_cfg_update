import importlib.util,json,unittest,tempfile,io
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]/'maintenance'
spec=importlib.util.spec_from_file_location('eta',ROOT/'print_features/exclusion_eta.py');eta=importlib.util.module_from_spec(spec);spec.loader.exec_module(eta)
spec=importlib.util.spec_from_file_location('followup',ROOT/'followup_features.py');follow=importlib.util.module_from_spec(spec);spec.loader.exec_module(follow)
class FollowupTests(unittest.TestCase):
 def test_slow_first_layer_does_not_triple_eta(self):
  for dt,work in [(31,7),(62,16),(92,53)]:self.assertEqual(eta.warmup_ratio(dt,work),1)
  self.assertEqual(eta.warmup_ratio(460,450),460/450)
  self.assertEqual(eta.warmup_ratio(900,890),900/890)
 def test_explicit_tool_time_not_acceleration_is_removed(self):
  index={'total':856.64,'tool_seconds':28,'events':[[n,n%2,'A' if n%2==0 else 'B'] for n in range(137)],'records':[[0,50,'A',428.32],[50,100,'B',428.32]]}
  self.assertAlmostEqual(eta.work_left(index,['A'],0,5765),992.5)
 def test_model_approach_preserved_and_idempotent(self):
  for x in (230,310,420):
   text='[gcode_macro START_PRINT]\ngcode:\n    M104 S{target_EXTRUDER}\n    TEMPERATURE_WAIT SENSOR=extruder MINIMUM={target_EXTRUDER - 5} MAXIMUM={target_EXTRUDER + 20}\n    G1 X%d F8200\n    CHANGE_TOOL {ct}\n[gcode_macro END_PRINT]\ngcode:\n    M84\n'%x
   out=follow.first_tool(text);self.assertIn('APPROACH_X=%d APPROACH_F=8200'%x,out);self.assertEqual(follow.first_tool(out),out)
 def test_all_locales_cover_new_ui(self):
  paths=list((ROOT/'screen_locales').glob('*.json'));self.assertEqual(len(paths),32)
  for p in paths:
   d=json.loads(p.read_text());self.assertTrue(d['Calculating print time']);self.assertTrue(d['Cancelling'])
   d.update(json.loads((ROOT/'printer_locales'/p.name).read_text()));self.assertTrue(d['Exclusion pending'])
 def test_restart_restores_same_job_and_new_job_resets(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'test.gcode').write_text('G1 X1')
   idx={'total':100,'tool_seconds':28,'events':[[0,0,'A'],[50,1,'B']],'records':[[0,50,'A',50],[50,100,'B',50]]}
   job={'job_id':'1','filename':'test.gcode','status':'in_progress'}
   def response(*a,**kw):return io.BytesIO(json.dumps({'result':{'jobs':[job]}}).encode())
   with patch.object(Path,'home',return_value=root),patch.object(eta,'index_file',return_value=idx),patch('urllib.request.urlopen',side_effect=response):
    for elapsed,pos in [(30,60),(60,70)]:eta.calculate(d,'test.gcode',['A'],pos,256,elapsed)
    state=root/'.cache/KlipperScreen/exclusion_eta/active-v3.json';self.assertEqual(len(json.loads(state.read_text())['samples']),2)
    # calculate has no in-memory observation state: disk is authoritative.
    eta.calculate(d,'test.gcode',['A'],80,256,90);self.assertEqual(len(json.loads(state.read_text())['samples']),3)
    job['job_id']='2';eta.calculate(d,'test.gcode',['A'],60,256,30);self.assertEqual(len(json.loads(state.read_text())['samples']),1)
    state.write_text('broken');self.assertIsNotNone(eta.calculate(d,'test.gcode',['A'],60,256,31))
if __name__=='__main__':unittest.main()
