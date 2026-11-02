import importlib.util, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

def load(name):
 spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'maintenance/print_features/exclude_tool_guard.py')
 mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

class Tests(unittest.TestCase):
 def simulate(self,module,stuck=False):
  guard=module.ExcludeToolGuard.__new__(module.ExcludeToolGuard);guard.depth=0;guard.reset()
  obj=NS(current_object='EXCLUDED_PART',excluded_objects=['EXCLUDED_PART'])
  sd=NS(file_path=lambda:'print.gcode')
  mounted=[True];moves=[]
  def park(cmd):
   # Model exclude_object's movement filter. Real machine movement is never called.
   if obj.current_object not in obj.excluded_objects:
    moves.append('park')
    if not stuck:mounted[0]=False
  def return_head(cmd):
   if mounted[0]:raise RuntimeError('Tool still detected after parking; inspect the head')
   moves.append('return')
  def cancel(cmd):
   handlers['PARK_TOOL_1'](cmd)
   handlers['_FAST_CANCEL_RETURN'](cmd)
  handlers={name:Mock() for name in ('START_PRINT','CHANGE_TOOL','M104','M109','EXCLUDE_OBJECT_END')}
  handlers.update({'EXCLUDE_OBJECT_START':lambda cmd:setattr(obj,'current_object',cmd.params['NAME']),
                   'PARK_TOOL_1':park,'_FAST_CANCEL_MOTION':cancel,'_FAST_CANCEL_RETURN':return_head})
  def register(name,handler):
   old=handlers.pop(name,None)
   if handler is not None:handlers[name]=handler
   return old
  guard.gcode=NS(register_command=register,run_script=Mock(),
    run_script_from_command=lambda line:setattr(obj,'current_object',None),
    create_gcode_command=lambda cmd,line,params:NS(params=params))
  guard.printer=NS(lookup_object=lambda name:sd if name=='virtual_sdcard' else obj, get_reactor=lambda:NS(register_timer=Mock(),monotonic=lambda:0))
  guard.ready()
  error=None
  try:handlers['_FAST_CANCEL_MOTION'](NS())
  except RuntimeError as exc:error=str(exc)
  return moves,error,guard.depth
 def test_full_cancel_movement_is_protected(self):
  moves,error,depth=self.simulate(load('exclude_tool_guard'))
  self.assertEqual(moves,['park','return']);self.assertIsNone(error);self.assertEqual(depth,0)
 def test_real_sensor_failure_still_blocks_return(self):
  moves,error,depth=self.simulate(load('exclude_tool_guard'),stuck=True)
  self.assertEqual(moves,['park']);self.assertIn('Tool still detected',error);self.assertEqual(depth,0)
if __name__=='__main__':unittest.main()
