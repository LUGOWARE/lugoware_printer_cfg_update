import unittest,importlib.util,tempfile,re
from pathlib import Path
from types import SimpleNamespace as NS
spec=importlib.util.spec_from_file_location('guard',__import__('pathlib').Path(__file__).resolve().parents[1] / 'maintenance/print_features/exclude_tool_guard.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Cmd:
 def __init__(self,name):self.name=name
 def get(self,key,default=None):return self.name if key=='NAME' else default
class Tests(unittest.TestCase):
 def guard(self,path):
  r=m.ExcludeToolGuard.__new__(m.ExcludeToolGuard);r.depth=0;r.reset();r.exclude=NS(current_object='A',excluded_objects=['A'])
  self.pos=0;r.sd=NS(file_path=lambda:str(path),get_file_position=lambda:self.pos,is_cmd_from_sd=lambda:True)
  r.original={'EXCLUDE_OBJECT_END':lambda cmd:setattr(r.exclude,'current_object',None)}
  return r
 def check(self,body,expected,name='A',excluded=True):
  with tempfile.NamedTemporaryFile(mode='w',delete=False) as f:f.write(body);p=Path(f.name)
  try:
   r=self.guard(p)
   if not excluded:r.exclude.excluded_objects=[]
   r.end_object(Cmd(name));self.assertEqual(r.filtered_wipe_gaps,expected)
   self.assertEqual(r.exclude.current_object,'A' if expected else None)
  finally:p.unlink()
 def test_wipe_excluded(self):self.check(';WIPE_START\nG1 F6000\nG1 X2 Y3 E-.5\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',1)
 def test_first_layer_temperature_and_retract(self):self.check('M140 S60\nG1 E-.36494 F2100\n;WIPE_START\nG1 F1800\nG1 X113.471 Y72.912 E-.13506\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',1)
 def test_mid_layer_retract(self):self.check('G1 E-.42167 F2100\n;WIPE_START\nG1 F7130.986\nG1 X102 Y69 E-.02\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',1)
 def test_pre_wipe_xyz_rejected(self):self.check('G1 X30 E-.4\n;WIPE_START\nG1 X2 E-.1\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',0)
 def test_active_object_unchanged(self):self.check(';WIPE_START\nG1 X2 E-.5\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',0,excluded=False)
 def test_other_object_not_extended(self):self.check(';WIPE_START\nG1 X2 E-.5\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=B\n',0)
 def test_unknown_macro_not_extended(self):self.check('PARK_CURRENT\n;WIPE_START\nG1 X2 E-.5\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',0)
 def test_positive_extrusion_not_extended(self):self.check(';WIPE_START\nG1 X2 E.5\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',0)
 def test_machine_unnamed_end_unchanged(self):self.check(';WIPE_START\nG1 X2 E-.5\n;WIPE_END\nEXCLUDE_OBJECT_START NAME=A\n',0,name=None)
 def test_end_print_not_extended(self):self.check('END_PRINT\n',0)
 @unittest.skipUnless((__import__('pathlib').Path.home()/'printer_data/gcodes'/'3DBenchy_PLA_7h41m.gcode').exists(), 'Requires printer test G-code')
 def test_actual_benchy(self):
  p=Path.home()/'printer_data/gcodes/3DBenchy_PLA_7h41m.gcode';r=self.guard(p)
  r.exclude.current_object=None
  r.exclude.excluded_objects=['3DBENCHY.DRC_ID_%d_COPY_0'%i for i in (0,2,3)]
  raw_current=None;blocked_gap_moves=0;included_moves=0
  with p.open('rb') as f:
   for raw in f:
    self.pos=f.tell();line=raw.decode(errors='replace').split(';',1)[0].strip()
    if not line:continue
    command=line.split()[0].upper();match=m.NAME.search(line)
    if command=='EXCLUDE_OBJECT_START':raw_current=match.group(1).upper();r.exclude.current_object=raw_current
    elif command=='EXCLUDE_OBJECT_END':raw_current=None;r.end_object(Cmd(match.group(1).upper() if match else None))
    elif command in ('G0','G1'):
     if raw_current and raw_current not in r.exclude.excluded_objects:
      self.assertEqual(r.exclude.current_object,raw_current);included_moves+=1
     if raw_current is None and r.exclude.current_object in r.exclude.excluded_objects:blocked_gap_moves+=1
  self.assertGreater(blocked_gap_moves,0);self.assertGreater(included_moves,0)
  print('BENCHY:',r.filtered_wipe_gaps,'excluded wipe gaps;',blocked_gap_moves,'gap movement/feed commands filtered;',included_moves,'included movement commands preserved')
if __name__=='__main__':unittest.main()
