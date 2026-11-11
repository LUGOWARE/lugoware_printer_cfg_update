import ast
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import sys, types
module = types.ModuleType('probe_auto_recovery')
source = (Path(__file__).resolve().parents[1] / 'maintenance/print_features/probe_auto_recovery.py').read_text().replace(
    'from .probe import calc_probe_z_average',
    'calc_probe_z_average = lambda positions, method: tuple(positions)')
exec(compile(source, 'probe_auto_recovery.py', 'exec'), module.__dict__)
sys.modules['probe_auto_recovery'] = module
from probe_auto_recovery import ProbeAutoRecovery, ERROR

@unittest.skipUnless((Path.home()/'klipper/klippy/extras/probe.py').exists(), 'Requires installed Klipper averaging implementation')
class Tests(unittest.TestCase):
 def setUp(self):
  self.r=r=ProbeAutoRecovery.__new__(ProbeAutoRecovery)
  r.attempts=2;r.minimum_clearance=1.;r.offset=.723;r.recoveries=r.reactivations=0;r.trigger_errors=r.tolerance_errors=r.tolerance_retries=0;r.last_samples=[]
  self.pos=[100.,100.,2.,0.]
  r.toolhead=Mock();r.toolhead.get_position.side_effect=lambda:list(self.pos)
  r.toolhead.get_status.return_value={'homed_axes':'xyz','axis_minimum':[-2,-2,-4],'axis_maximum':[277,257,275]}
  r.toolhead.manual_move.side_effect=lambda pos,speed:self.pos.__setitem__(2,pos[2])
  r.fast_cancel=NS(requested=False,cleaning=False,homing_active=False)
  cfg=Mock();cfg.get_status.return_value={'settings':{'bed_mesh':{'horizontal_move_z':2.}}}
  r.printer=Mock(command_error=RuntimeError);r.printer.is_shutdown.return_value=False;r.printer.lookup_object.return_value=cfg
  r.wrapper=Mock();r.wrapper.query_endstop.return_value=False
  # Use the installed Klipper averaging implementation, not a copied loop.
  tree=ast.parse((Path.home()/'klipper/klippy/extras/probe.py').read_text())
  cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='SampleAveragingHelper')
  ns={'calc_probe_z_average':lambda positions,method:tuple(positions)}
  exec(compile(ast.Module(body=[cls],type_ignores=[]),'installed_sample_helper','exec'),ns)
  session=ns['SampleAveragingHelper'].__new__(ns['SampleAveragingHelper'])
  session.hw_probe_session=object();session.printer=Mock();session.printer.lookup_object.return_value=r.toolhead
  session.results=['previous point'];session.param_helper=Mock()
  session.param_helper.get_probe_params.return_value={'samples':3,'sample_retract_dist':1.5,'lift_speed':15,'samples_tolerance':.015,'samples_tolerance_retries':5,'samples_result':'median'}
  r.session=session;r.original=session.run_probe
  self.cmd=Mock();self.cmd.error=RuntimeError;self.cmd.get_command.return_value='BED_MESH_CALIBRATE_BASE';self.cmd.get_float.side_effect=lambda key,default:default
  self.sample=NS(bed_z=0.)
 def feed(self, values):
  seq=iter(values)
  def probe(cmd):
   value=next(seq)
   if isinstance(value,Exception): raise value
   self.pos[2]=.485
   return NS(bed_z=value)
  self.r.session._probe=Mock(side_effect=probe)
 def test_normal_no_extra_wait(self):
  self.feed([0,0,0]);self.r.run_probe(self.cmd)
  self.r.toolhead.dwell.assert_not_called()
  self.assertEqual(self.r.session._probe.call_count,3)
 def test_tolerance_lift_two_wait_one(self):
  self.feed([0,.04,0,0,.04,0]);self.r.run_probe(self.cmd)
  self.assertEqual(self.r.session._probe.call_count,6)
  self.r.toolhead.dwell.assert_called_once_with(1.0)
  self.assertEqual(self.r.toolhead.manual_move.call_args_list[2].args[0],[None,None,2.485])
 def test_all_rounds_and_failure(self):
  self.feed([0,.1,0]*5)
  with self.assertRaisesRegex(RuntimeError,'samples_tolerance'):self.r.run_probe(self.cmd)
  self.assertEqual(self.r.session._probe.call_count,15)
  self.assertEqual(self.r.toolhead.dwell.call_count,4)
  self.assertEqual(self.r.session.results,['previous point'])
 def test_fifth_round_success(self):
  self.feed([0,.04,0,0,.05,0,0,.07,0,0,.08,0,0,.085,0])
  self.r.run_probe(self.cmd)
  self.assertEqual(self.r.session._probe.call_count,15)
  self.assertEqual(len(self.r.session.results),2)
 def test_trigger_two_cycles_reset_tolerance(self):
  # Reach second tolerance, then trigger. New .04 spread must fail .03 again.
  self.feed([0,.04,0,RuntimeError(ERROR),0,.04,0,0,.04,0])
  self.r.run_probe(self.cmd)
  self.assertEqual(self.r.session._probe.call_count,10)
  self.assertEqual(self.r.reactivations,2)
  self.assertEqual(self.r.recoveries,1)
  self.r.wrapper._lower_probe.assert_called_with()
  self.assertEqual(self.r.wrapper._lower_probe.call_count,2)
  delays=[x.args[0] for x in self.r.toolhead.dwell.call_args_list]
  self.assertEqual(delays,[1.0,2.0,.05,.05,.02,1.0])
 def test_trigger_repeated_aborts(self):
  self.feed([RuntimeError(ERROR),RuntimeError(ERROR)])
  with self.assertRaisesRegex(RuntimeError,ERROR):self.r.run_probe(self.cmd)
  self.assertEqual(self.r.reactivations,2)
  self.assertEqual(self.r.session._probe.call_count,2)
 def test_signal_stuck_aborts(self):
  self.feed([RuntimeError(ERROR)]);self.r.wrapper.query_endstop.return_value=True
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.assertEqual(self.r.reactivations,2)
  self.assertEqual(self.r.session._probe.call_count,1)
 def test_g28_stock_first_and_second(self):
  self.cmd.get_command.return_value='G28'
  self.r.session.param_helper.get_probe_params.return_value['samples']=1
  for attempt in (1,2):
   self.cmd.get_int.return_value=attempt
   self.feed([0]);self.r.run_probe(self.cmd)
   self.assertEqual(self.r.session._probe.call_count,1)
  self.r.toolhead.dwell.assert_not_called()
 def test_probe_inside_homing_override_recovers(self):
  self.cmd.get_command.return_value='PROBE';self.r.fast_cancel.homing_active=True
  self.feed([RuntimeError(ERROR),0,0,0]);self.r.run_probe(self.cmd)
  self.assertEqual(self.r.reactivations,2)
 def test_cancel_prevents_lift(self):
  self.r.fast_cancel.requested=True;self.feed([RuntimeError(ERROR)])
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.r.toolhead.manual_move.assert_not_called()
  self.assertEqual(self.r.reactivations,0)
 def test_unknown_axes_prevents_lift(self):
  self.r.toolhead.get_status.return_value['homed_axes']='xy'
  self.feed([RuntimeError(ERROR)])
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.r.toolhead.manual_move.assert_not_called()
 def test_z_limit_prevents_lift(self):
  self.pos[2]=274.;self.feed([RuntimeError(ERROR)])
  with self.assertRaisesRegex(RuntimeError,'clearance'):self.r.run_probe(self.cmd)
  self.r.toolhead.manual_move.assert_not_called()
 def test_calibration_and_leveling(self):
  for name in ('PROBE_CALIBRATE','Z_TILT_ADJUST','QUAD_GANTRY_LEVEL'):
   self.cmd.get_command.return_value=name
   self.feed([0,.04,0,0,.04,0]);self.r.run_probe(self.cmd)
   self.assertEqual(self.r.session._probe.call_count,6)
 def test_next_point_starts_at_three_hundredths(self):
  for i in range(2):
   self.feed([0,.04,0,0,.04,0]);self.r.run_probe(self.cmd)
   self.assertEqual(self.r.session._probe.call_count,6)
 def test_single_sample_accuracy_preserved(self):
  self.cmd.get_command.return_value=''
  self.r.session.param_helper.get_probe_params.return_value['samples']=1
  self.feed([0]);self.r.run_probe(self.cmd)
  self.assertEqual(self.r.session._probe.call_count,1)
  self.r.toolhead.dwell.assert_not_called()
if __name__=='__main__':unittest.main()
