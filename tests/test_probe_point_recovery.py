import ast
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance/print_features'))
from probe_auto_recovery import ProbeAutoRecovery, ERROR

@unittest.skipUnless((Path.home()/'klipper/klippy/extras/probe.py').exists(), 'Requires installed Klipper averaging implementation')
class Tests(unittest.TestCase):
 def setUp(self):
  self.r=r=ProbeAutoRecovery.__new__(ProbeAutoRecovery)
  r.attempts=2;r.minimum_clearance=1.;r.offset=.723;r.recoveries=r.reactivations=0
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
  self.cmd=Mock();self.cmd.get_command.return_value='BED_MESH_CALIBRATE_BASE';self.cmd.get_float.side_effect=lambda key,default:default
  self.sample=NS(bed_z=0.)
 def test_no_normal_wait_or_query(self):
  self.r.session._probe=Mock(return_value=self.sample)
  self.r.run_probe(self.cmd)
  self.r.toolhead.wait_moves.assert_not_called();self.r.wrapper.query_endstop.assert_not_called()
  self.assertEqual(self.r.session._probe.call_count,3)
 def test_two_old_samples_discarded_and_three_new_samples(self):
  calls=[]
  def measure(cmd):
   calls.append(1);self.pos[2]=.723
   if len(calls)==3: raise RuntimeError(ERROR)
   return self.sample
  self.r.session._probe=measure
  self.r.run_probe(self.cmd)
  self.assertEqual(len(calls),6)
  self.assertEqual(self.r.session.results,['previous point',(self.sample,)*3])
  self.assertEqual(self.r.reactivations,1)
  self.assertEqual(self.r.recoveries,1)
 def test_stuck_no_retry_measurement(self):
  self.r.session._probe=Mock(side_effect=RuntimeError(ERROR))
  self.r.wrapper.query_endstop.return_value=True
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.assertEqual(self.r.reactivations,2);self.assertEqual(self.r.session._probe.call_count,1)
 def test_repeated_error_max_two(self):
  self.r.session._probe=Mock(side_effect=RuntimeError(ERROR))
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.assertEqual(self.r.session._probe.call_count,3);self.assertEqual(self.r.reactivations,2)
 def test_other_error(self):
  self.r.session._probe=Mock(side_effect=RuntimeError('timeout'))
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.assertEqual(self.r.reactivations,0)
 def test_cancel(self):
  self.r.fast_cancel.requested=True
  self.r.session._probe=Mock(side_effect=RuntimeError(ERROR))
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.r.wrapper._lower_probe.assert_not_called()
 def test_home_never_retried(self):
  self.cmd.get_command.return_value='G28';self.r.session._probe=Mock(side_effect=RuntimeError(ERROR))
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.r.wrapper._lower_probe.assert_not_called()
 def test_xy_change_prevents_recovery(self):
  def fail(cmd):self.pos[0]+=1;raise RuntimeError(ERROR)
  self.r.session._probe=fail
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.r.wrapper._lower_probe.assert_not_called()

 def test_high_z_kept_and_three_fresh_samples(self):
  calls=[]
  def measure(cmd):
   calls.append(self.pos[2])
   if len(calls)==1:
    self.pos[2]=3.352244
    raise RuntimeError(ERROR)
   self.pos[2]=.723
   return self.sample
  self.r.session._probe=measure
  self.r.run_probe(self.cmd)
  self.assertEqual(len(calls),4)
  self.assertAlmostEqual(calls[1],5.352244)
  self.assertEqual(self.r.session.results,['previous point',(self.sample,)*3])
  # Only the original sample retractions occurred, never a move back to Z=2.
  self.assertEqual(self.r.toolhead.manual_move.call_count,3)
  for call in self.r.toolhead.manual_move.call_args_list:
   self.assertGreater(call.args[0][2],2.)
 def test_above_axis_maximum_rejected(self):
  def fail(cmd):self.pos[2]=276.;raise RuntimeError(ERROR)
  self.r.session._probe=fail
  with self.assertRaises(RuntimeError):self.r.run_probe(self.cmd)
  self.r.wrapper._lower_probe.assert_not_called()
  self.r.toolhead.manual_move.assert_not_called()

 def test_lift_capped_at_maximum(self):
  self.pos[2]=274.
  self.assertTrue(self.r.recover(self.cmd,[100.,100.,2.,0.]))
  self.assertEqual(self.pos[2],275.)
 def test_each_redeployment_lifts_two(self):
  self.assertTrue(self.r.recover(self.cmd,list(self.pos)))
  self.assertEqual(self.pos[2],4.)
  self.assertTrue(self.r.recover(self.cmd,[100.,100.,2.,0.]))
  self.assertEqual(self.pos[2],6.)

if __name__ == '__main__':
 unittest.main()
