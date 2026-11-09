import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import copy
import unittest
from types import SimpleNamespace as O
from unittest.mock import Mock
from recovery_objects import capture,restore,FIELDS
from recovery_index import validate_checkpoint
from recovery_execution import RecoveryExecution
from test_recovery_v2 import checkpoint

class ObjectRecoveryTests(unittest.TestCase):
 def fixture(self):
  ex=O(next_transform=object(),last_position=[10,20,3,100],last_position_extruded=[9,19,3,90],last_position_excluded=[10,20,3,100],max_position_extruded=91,max_position_excluded=101,extruder_adj=1,initial_extrusion_moves=0,in_excluded_region=True,extrusion_offsets={'extruder':[1,1,0,10]},_register_transform=Mock())
  guard=O(pending=['CHANGE_TOOL NEXT_TOOL=2 TEMP=240',{'NEXT_TOOL':'2','TEMP':'240'}],pending_temp=['M104','M104 S240',{'S':'240'}],upcoming='B',skipped=3,replayed=1,filtered_wipe_gaps=2,startup_excludes=[],first_object='A',first_tool=1)
  gm=O(saved_states={});th=O(get_position=lambda:[9,19,3,50])
  objs={'exclude_object':ex,'exclude_tool_guard':guard,'toolhead':th,'gcode_move':gm}
  p=O(lookup_object=lambda n,d=None:objs.get(n,d))
  return p,ex,guard
 def test_single_and_all_tools(self):
  for tool in range(4):
   cp=checkpoint();cp['snapshot']['gcode_macro TOOL_STATE']['active_tool']=tool
   self.assertEqual(validate_checkpoint(cp),'')
 def test_excluded_and_deferred_preserved(self):
  p,ex,guard=self.fixture();cp=checkpoint();s=cp['snapshot']
  s['exclude_object']={'objects':[{'name':'A','center':[1,2],'polygon':[[0,0],[1,1]]},{'name':'B'}],'excluded_objects':['B'],'current_object':'B'}
  s['exclude_tool_guard']={'deferred_toolchange':True}
  s['exclusion_internal']=capture(p);s['toolhead']['position'][3]=90
  self.assertEqual(validate_checkpoint(cp),'')
  guard.pending=None;ex.extrusion_offsets={}
  commands=[];r=RecoveryExecution();r.printer=p;r.restore_objects(s,commands.append)
  self.assertIn('EXCLUDE_OBJECT NAME=B',commands)
  self.assertIn('CENTER=1,2',commands[0])
  self.assertEqual(guard.pending[1]['NEXT_TOOL'],'2')
  self.assertEqual(guard.pending_temp[2]['S'],'240')
  self.assertEqual(ex.extrusion_offsets['extruder'][3],50)
  self.assertEqual(ex.initial_extrusion_moves,0)
  self.assertTrue(ex.in_excluded_region)
  self.assertEqual(commands[-1],'RESTORE_GCODE_STATE NAME=_LUGO_RECOVERY MOVE=0')
 def test_old_excluded_record_stays_blocked(self):
  cp=checkpoint();cp['snapshot']['exclude_object']={'excluded_objects':['B']}
  self.assertTrue(validate_checkpoint(cp))

class CheckpointBoundaryTests(unittest.TestCase):
 def test_object_checkpoint_replays_start_with_exact_tool(self):
  import lugo_recovery as journal
  from collections import deque
  r=journal.Recovery.__new__(journal.Recovery)
  r.running=True;r.file_layer=3;r.record={'session':'abc'};r.retract_debt=.5;r.execution_pending=deque()
  r.reactor=O(monotonic=lambda:10)
  cp=checkpoint();cp['snapshot']['gcode_macro TOOL_STATE']['active_tool']=1
  r.snapshot=lambda now:copy.deepcopy(cp['snapshot'])
  th=O(register_lookahead_callback=lambda fn:fn(12))
  r.printer=O(lookup_object=lambda name:th)
  r.observe_object(O(file_position=123,next_file_position=160))
  saved=r.execution_pending[0]
  self.assertEqual(saved['offset'],123)
  self.assertEqual(saved['kind'],'object')
  self.assertEqual(saved['snapshot']['gcode_macro TOOL_STATE']['active_tool'],1)
  self.assertFalse(saved['executed'])
 def test_real_file_only_tools_two_and_three(self):
  import re
  from pathlib import Path
  p=Path(__file__).parent/'multitool_audit/print.gcode'
  if not p.exists():self.skipTest('local reproduction fixture')
  tools=set(int(x) for x in re.findall(r'^CHANGE_TOOL NEXT_TOOL=(\d+)',p.read_text(),re.M))
  self.assertEqual(tools,{1,2})
