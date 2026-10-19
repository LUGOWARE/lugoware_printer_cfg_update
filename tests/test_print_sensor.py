import unittest
import sys
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance/print_features'))
from print_sensor import PrintSensor

class Gcmd:
    def __init__(self, enabled): self.enabled=enabled
    def get_int(self,*args,**kwargs):return self.enabled

class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.stats={'state':'printing'}
        self.paused=NS(is_paused=False)
        self.callbacks=[]
        self.resets=[]
        self.helper=NS(sensor_enabled=False,filament_present=False,event_delay=3,min_event_systime=0)
        self.objects={'print_stats':NS(get_status=lambda t:self.stats),'pause_resume':self.paused,
                      'toolhead':NS(register_lookahead_callback=self.callbacks.append),
                      'mcu':NS(estimated_print_time=lambda t:t)}
        self.p=PrintSensor.__new__(PrintSensor)
        self.p.printer=NS(lookup_object=lambda n:self.objects[n])
        self.p.reactor=NS(monotonic=lambda:10)
        self.p.enabled=True;self.p.pending=None;self.p.in_job=True
        self.p.gate=False;self.p.generation=0;self.p.arm_at=None
        self.p.helper=self.helper
        self.p.sensor=NS(_update_filament_runout_pos=self.resets.append)
        self.p.original_runout=lambda t:self.fail('Unexpected runout')

    def test_off_survives_docking(self):
        self.p.enabled=False
        self.p.set_gate(Gcmd(1));self.callbacks.pop()(20)
        self.p.tick(20)
        self.assertFalse(self.helper.sensor_enabled)
        self.p.runout(20)

    def test_native_switch_shares_policy_but_respects_gate(self):
        self.p.legacy_set(Gcmd(1))
        self.assertTrue(self.p.enabled)
        self.assertFalse(self.helper.sensor_enabled)
        self.p.gate=True;self.p.tick(20)
        self.assertTrue(self.helper.sensor_enabled)
        self.p.legacy_set(Gcmd(0))
        self.assertFalse(self.p.enabled)
        self.assertFalse(self.helper.sensor_enabled)

    def test_native_status_reports_policy_and_actual_separately(self):
        self.p.original_status=lambda t: {'enabled':False,'filament_detected':True}
        self.assertTrue(self.p.sensor_status(20)['enabled'])
        self.assertFalse(self.p.sensor_status(20)['detection_active'])

    def test_enable_only_after_motion_and_reset_encoder(self):
        self.p.set_gate(Gcmd(1));self.callbacks.pop()(20)
        self.p.tick(19);self.assertFalse(self.helper.sensor_enabled)
        self.p.tick(20);self.assertTrue(self.helper.sensor_enabled)
        self.assertEqual(self.resets,[20])
        self.p.tick(21);self.assertEqual(self.resets,[20])

    def test_stale_callback_does_not_reenable(self):
        self.p.set_gate(Gcmd(1));callback=self.callbacks.pop()
        self.p.close_gate();callback(20);self.p.tick(30)
        self.assertFalse(self.helper.sensor_enabled)

    def test_pause_resume_preserves_off(self):
        self.p.enabled=False;self.p.gate=True
        self.paused.is_paused=True;self.p.tick(20)
        self.paused.is_paused=False;self.p.tick(21)
        self.assertFalse(self.helper.sensor_enabled)

    def test_next_job_defaults_on_and_pending_off_consumed_once(self):
        self.p.pending=False;self.p.begin(None)
        self.assertFalse(self.p.enabled)
        self.p.finish();self.p.begin(None)
        self.assertTrue(self.p.enabled)

    def test_terminal_disables_and_resets(self):
        for state in ('complete','cancelled','error'):
            self.p.in_job=True;self.p.gate=True;self.p.enabled=False
            self.stats['state']=state;self.p.tick(10)
            self.assertFalse(self.p.in_job)
            self.assertFalse(self.helper.sensor_enabled)
            self.assertTrue(self.p.enabled)

if __name__=='__main__':unittest.main()
