import importlib.util, tempfile, pathlib, re, unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
spec=importlib.util.spec_from_file_location('guard',__import__('pathlib').Path(__file__).resolve().parents[1] / 'maintenance/print_features/exclude_tool_guard.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Cmd:
 def __init__(self,line):
  self.line=line;self.command=line.split()[0].upper();self.params={}
  for token in line.split()[1:]:
   if '=' in token:k,v=token.split('=',1);self.params[k.upper()]=v
   elif token[:1].upper() in ('S','T'):self.params[token[0].upper()]=token[1:]
 def get_command(self):return self.command
 def get_commandline(self):return self.line
 def get_command_parameters(self):return self.params
 def get(self,k):return self.params[k]
 def get_float(self,k,d):return float(self.params.get(k,d))
def make_cmd(command,line,params):
 c=Cmd(command);c.line=line;c.params=params;return c
class Tests(unittest.TestCase):
 def setup_guard(self,path,excluded):
  self.path=str(path);self.pos=0;self.actual_tool=None;self.calls=[]
  r=mod.ExcludeToolGuard.__new__(mod.ExcludeToolGuard);r.depth=0;r.reset()
  r.sd=NS(file_path=lambda:self.path,get_file_position=lambda:self.pos,is_cmd_from_sd=lambda:True)
  r.exclude=NS(current_object=None,excluded_objects=excluded)
  r.gcode=NS(create_gcode_command=make_cmd,run_script_from_command=lambda s:setattr(r.exclude,'current_object',None))
  def change(c):
   self.assertIsNone(r.exclude.current_object,'physical docking inside exclusion')
   self.actual_tool=int(c.params['NEXT_TOOL']);self.calls.append(self.actual_tool)
  r.original={'CHANGE_TOOL':change,'EXCLUDE_OBJECT_START':lambda c:setattr(r.exclude,'current_object',c.get('NAME').upper()),'M104':Mock(),'M109':Mock()}
  return r
 def simulate(self,path,excluded):
  r=self.setup_guard(path,excluded);desired=None;checks=0
  with open(path,'rb') as f:
   for raw in f:
    self.pos=f.tell();line=raw.decode(errors='replace').split(';',1)[0].strip()
    if not line:continue
    c=Cmd(line)
    if c.command=='CHANGE_TOOL':desired=int(c.params['NEXT_TOOL']);r.change_tool(c)
    elif c.command=='EXCLUDE_OBJECT_END':r.exclude.current_object=None
    elif c.command=='EXCLUDE_OBJECT_START':
     r.start_object(c)
     if c.get('NAME').upper() not in excluded:
      self.assertEqual(self.actual_tool,desired,line);checks+=1
    elif c.command in ('M104','M109'):r.temperature(c)
  return r,checks
 @unittest.skipUnless((__import__('pathlib').Path.home()/'printer_data/gcodes'/'obj_1_Body12_PLA_5h29m.gcode').exists(), 'Requires printer test G-code')
 def test_real_file_excluded_pair(self):
  p=pathlib.Path.home()/'printer_data/gcodes/obj_1_Body12_PLA_5h29m.gcode'
  r,checks=self.simulate(p,['OBJ_3_BODY13.STL_ID_2_COPY_0','OBJ_4_BODY6.STL_ID_3_COPY_0'])
  self.assertGreater(r.skipped,0);self.assertGreater(checks,100)
  self.assertNotIn(2,self.calls)
  print('REAL FILE:',checks,'included regions;',r.skipped,'skipped changes;',len(self.calls),'executed changes')
 @unittest.skipUnless((__import__('pathlib').Path.home()/'printer_data/gcodes'/'obj_1_Body12_PLA_5h29m.gcode').exists(), 'Requires printer test G-code')
 def test_real_file_without_exclusions(self):
  p=pathlib.Path.home()/'printer_data/gcodes/obj_1_Body12_PLA_5h29m.gcode'
  r,checks=self.simulate(p,[]);self.assertEqual(r.skipped,0);self.assertGreater(checks,100)
 def test_deferred_tool_replayed_for_next_included(self):
  with tempfile.NamedTemporaryFile(mode='w',delete=False) as f:
   f.write('CHANGE_TOOL NEXT_TOOL=2 TEMP=220\nEXCLUDE_OBJECT_START NAME=A\nEXCLUDE_OBJECT_END NAME=A\nEXCLUDE_OBJECT_START NAME=B\n');p=f.name
  try:
   r,n=self.simulate(p,['A']);self.assertEqual(r.skipped,1);self.assertEqual(r.replayed,1);self.assertEqual(self.calls,[2])
  finally:pathlib.Path(p).unlink()
 def test_hotend_off_always_allowed(self):
  r=self.setup_guard('/tmp/x',['A']);r.exclude.current_object='A'
  r.temperature(Cmd('M104 S0'));r.original['M104'].assert_called_once()
  r.temperature(Cmd('M104 S220'));self.assertEqual(r.original['M104'].call_count,1)
 def test_macro_temperature_not_filtered(self):
  r=self.setup_guard('/tmp/x',['A']);r.exclude.current_object='A';r.depth=1
  r.temperature(Cmd('M109 S220'));r.original['M109'].assert_called_once()
 def test_cancel_does_not_restore_reset_object(self):
  r=self.setup_guard('/tmp/x',['A']);r.exclude.current_object='A'
  r.physical(lambda c:setattr(self,'path',None),Cmd('CANCEL_PRINT'))
  self.assertIsNone(r.exclude.current_object)
 def test_physical_error_does_not_resume_exclusion(self):
  r=self.setup_guard('/tmp/x',['A']);r.exclude.current_object='A'
  def fail(c):raise RuntimeError('fail')
  with self.assertRaises(RuntimeError):r.physical(fail,Cmd('CHANGE_TOOL'))
  self.assertEqual(r.depth,0);self.assertIsNone(r.exclude.current_object)
if __name__=='__main__':unittest.main()
