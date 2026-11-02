import importlib.util,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
from contextlib import nullcontext
spec=importlib.util.spec_from_file_location('guard',Path(__file__).resolve().parents[1]/'maintenance/print_features/exclude_tool_guard.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Request:
 def __init__(self,name,action):self.data=dict(name=name,action=action);self.result=None
 def get_str(self,key,default=None):return self.data.get(key,default)
 def error(self,s):return RuntimeError(s)
 def send(self,result):self.result=result
class Tests(unittest.TestCase):
 def setUp(self):
  r=self.r=m.ExcludeToolGuard.__new__(m.ExcludeToolGuard);r.depth=0;r.reset()
  self.stats=NS(state='printing');self.fc=NS(requested=False,cleaning=False)
  r.exclude=NS(objects=[{'name':x} for x in ('A','B','C')],excluded_objects=[],current_object=None)
  self.commands=[]
  def script(line):
   self.commands.append(line);r.exclude.excluded_objects.append(line.split('=',1)[1])
  r.gcode=NS(error=RuntimeError,get_mutex=nullcontext,run_script_from_command=script)
  r.printer=NS(command_error=RuntimeError,is_shutdown=lambda:False,get_reactor=lambda:NS(monotonic=lambda:1),lookup_object=lambda name: self.fc if name=='fast_cancel' else NS(get_status=lambda _:dict(state=self.stats.state)))
  r.original_run_script=Mock()
 def request(self,name,action):
  req=Request(name,action);self.r.handle_request(req);return req.result['state']
 def test_pending_can_be_withdrawn_during_docking(self):
  self.r.depth=1;self.assertEqual(self.request('A','exclude'),'pending');self.r.flush_pending(0);self.assertEqual(self.commands,[])
  self.assertEqual(self.request('A','cancel'),'normal');self.r.depth=0;self.r.flush_pending(1);self.assertEqual(self.commands,[])
 def test_applied_cannot_be_withdrawn(self):
  self.request('A','exclude');self.r.flush_pending(1)
  self.assertEqual(self.request('A','cancel'),'excluded');self.assertEqual(self.r.exclude.excluded_objects,['A']);self.assertEqual(len(self.commands),1)
 def test_duplicate_request_is_idempotent(self):
  for _ in range(3):self.request('A','exclude')
  self.assertEqual(self.r.startup_excludes,['A']);self.r.flush_pending(0);self.assertEqual(len(self.commands),1)
 def test_startup_pending_waits_for_checkpoint(self):
  self.r.startup_active=True;self.request('A','exclude');self.r.flush_pending(0);self.assertEqual(self.commands,[])
  self.r.apply_startup_excludes();self.assertEqual(self.r.exclude.excluded_objects,['A'])
 def test_final_pending_object_rejected(self):
  self.request('A','exclude');self.request('B','exclude')
  with self.assertRaises(RuntimeError):self.request('C','exclude')
 def test_print_cancel_discards_pending(self):
  self.request('A','exclude');self.fc.requested=True;self.r.flush_pending(0);self.assertEqual(self.r.startup_excludes,[]);self.assertEqual(self.commands,[])
 def test_mainsail_request_during_toolchange_is_queued(self):
  self.r.depth=1;self.r.external_script('EXCLUDE_OBJECT NAME=A');self.assertEqual(self.r.startup_excludes,['A']);self.r.original_run_script.assert_not_called()
 def test_withdrawal_while_waiting_for_mutex(self):
  self.request('A','exclude')
  outer=self
  class Lock:
   def __enter__(self):outer.request('A','cancel')
   def __exit__(self,*a):pass
  self.r.gcode.get_mutex=Lock;self.r.flush_pending(0);self.assertEqual(self.commands,[])
if __name__=='__main__':unittest.main()
