import importlib.util, tempfile, unittest, re
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
spec=importlib.util.spec_from_file_location('guard',Path(__file__).resolve().parents[1]/'maintenance/print_features/exclude_tool_guard.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.gcode'
  self.r=r=m.ExcludeToolGuard.__new__(m.ExcludeToolGuard);r.depth=0;r.reset();r.startup_active=True
  r.exclude=NS(objects=[{'name':x} for x in ('A','B','C')],excluded_objects=['A'],current_object=None)
  r.sd=NS(file_path=lambda:str(self.path),get_file_position=lambda:0,is_cmd_from_sd=lambda:True)
  r.original_run_script=Mock();r.printer=Mock();r.printer.is_shutdown.return_value=False
  self.fc=NS(requested=False,cleaning=False);self.heaters=Mock();r.printer.lookup_object.side_effect=lambda name: self.heaters if name=='heaters' else self.fc
  self.calls=[];self.docked=[]
  def script(s):
   self.calls.append(s)
   if s.startswith('EXCLUDE_OBJECT NAME='):r.exclude.excluded_objects.append(s.split('=',1)[1])
  r.gcode=NS(run_script_from_command=script,create_gcode_command=lambda c,l,p:NS(line=l,params=p))
  r.original={'CHANGE_TOOL':lambda c:self.docked.append(c.params.copy())}
  self.defaults={'NEXT_TOOL':'0','TEMP':'220','MVS':'12','PRIME_TYPE':'normal','P1':'6'}
  self.cmd=Mock();self.cmd.get_float.side_effect=lambda key,default,**kw:float(self.defaults.get(key,default));self.cmd.error=RuntimeError;self.cmd.get_command_parameters.return_value=self.defaults
 def tearDown(self):self.tmp.cleanup()
 def write(self,text):self.path.write_text(text)
 def test_select_exact_material_not_initial_defaults(self):
  self.write('CHANGE_TOOL NEXT_TOOL=0 TEMP=220 MVS=12 PRIME_TYPE=normal\nEXCLUDE_OBJECT_START NAME=A\nCHANGE_TOOL NEXT_TOOL=2 TEMP=245 MVS=8 PRIME_TYPE=foam FP0=25 FILAMENT_DIAMETER=2.85 TC_RETRACT_LEN=4 H_D=1\nT2\nM104 S250\nEXCLUDE_OBJECT_START NAME=B\n')
  self.r.prepare_first(self.cmd)
  self.assertEqual(self.r.first_object,'B');p=self.docked[0]
  self.assertEqual(p,dict(NEXT_TOOL='2',TEMP='250',MVS='8',PRIME_TYPE='foam',FP0='25',FILAMENT_DIAMETER='2.85',TC_RETRACT_LEN='4',H_D='1'))
  self.assertIn('M104 S250\nTEMPERATURE_WAIT SENSOR=extruder MINIMUM=245 MAXIMUM=270',self.calls)
  self.assertEqual(self.calls[-1], 'G1 X230 F9000')
 def test_no_exclusions_preserves_initial_parameters(self):
  self.r.exclude.excluded_objects=[];self.r.prepare_first(self.cmd)
  self.assertEqual(self.docked,[self.defaults]);self.assertFalse(self.r.startup_active)
 def test_request_queued_before_checkpoint(self):
  self.r.exclude.excluded_objects=[]
  self.write('EXCLUDE_OBJECT_START NAME=A\nCHANGE_TOOL NEXT_TOOL=1 TEMP=230\nEXCLUDE_OBJECT_START NAME=B\n')
  self.r.external_script('EXCLUDE_OBJECT NAME=A')
  self.r.original_run_script.assert_not_called();self.assertEqual(self.r.exclude.excluded_objects,[])
  self.r.prepare_first(self.cmd);self.assertEqual(self.docked[0]['NEXT_TOOL'],'1')
 def test_new_request_during_heating_reselects(self):
  self.write('EXCLUDE_OBJECT_START NAME=A\nCHANGE_TOOL NEXT_TOOL=1 TEMP=230\nEXCLUDE_OBJECT_START NAME=B\nCHANGE_TOOL NEXT_TOOL=3 TEMP=260 PRIME_TYPE=foam\nEXCLUDE_OBJECT_START NAME=C\n')
  original=self.r.gcode.run_script_from_command
  def script(s):
   original(s)
   if s.startswith('M104 S230'):self.r.external_script('EXCLUDE_OBJECT NAME=B')
  self.r.gcode.run_script_from_command=script
  self.r.prepare_first(self.cmd);self.assertEqual(len(self.docked),1);self.assertEqual(self.docked[0]['NEXT_TOOL'],'3');self.assertEqual(self.docked[0]['TEMP'],'260')
 def test_no_object_or_missing_material_never_docks(self):
  for text in ('EXCLUDE_OBJECT_START NAME=A\nEND_PRINT\n','CHANGE_TOOL NEXT_TOOL=2\nEXCLUDE_OBJECT_START NAME=B\n','T2\nEXCLUDE_OBJECT_START NAME=B\n'):
   self.write(text)
   with self.assertRaises(RuntimeError):self.r.prepare_first(self.cmd)
   self.assertEqual(self.docked,[])
 def test_requests_outside_startup_and_arbitrary_scripts_not_intercepted(self):
  for script in ('G1 X100','EXCLUDE_OBJECT RESET=1','EXCLUDE_OBJECT NAME=UNKNOWN','EXCLUDE_OBJECT NAME=A\nG28'):
   self.r.external_script(script);self.r.original_run_script.assert_called_with(script)
  self.r.startup_active=False;self.r.external_script('EXCLUDE_OBJECT NAME=A');self.r.original_run_script.assert_called_with('EXCLUDE_OBJECT NAME=A')
 def test_cancel_during_heat_never_docks(self):
  self.r.exclude.excluded_objects=[]
  self.r.gcode.run_script_from_command=lambda s:setattr(self.fc,'requested',True)
  self.r.prepare_first(self.cmd)
  self.heaters.turn_off_all_heaters.assert_called_once()
  self.assertEqual(self.docked,[])
 def test_start_finally_clears_requests_on_error(self):
  self.r.original['START_PRINT']=Mock(side_effect=RuntimeError('cancel'))
  with self.assertRaises(RuntimeError):self.r.start_print(self.cmd)
  self.assertFalse(self.r.startup_active);self.assertEqual(self.r.startup_excludes,[])
 def test_real_benchy_all_possible_first_remaining_parts(self):
  path=Path.home()/'printer_data/gcodes/3DBenchy_PLA_7h41m.gcode'
  if not path.exists():self.skipTest('Printer fixture')
  with path.open('rb') as f:
   while True:
    line=f.readline()
    if line.startswith(b'START_PRINT '):position=f.tell();break
  self.r.sd.file_path=lambda:str(path);self.r.sd.get_file_position=lambda:position
  for first in (1,2,3):
   self.r.exclude.excluded_objects=['3DBENCHY.DRC_ID_%d_COPY_0'%i for i in range(first)]
   name,p=self.r.select_first(self.defaults,self.cmd)
   self.assertEqual(name,'3DBENCHY.DRC_ID_%d_COPY_0'%first);self.assertEqual(p['NEXT_TOOL'],str(first));self.assertIn('TC_DERETRACT_EXTRA',p)
if __name__=='__main__':unittest.main()
