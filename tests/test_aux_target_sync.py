import importlib.util
from pathlib import Path
from types import SimpleNamespace as N
import unittest
spec=importlib.util.spec_from_file_location('aux',Path(__file__).resolve().parents[1]/'maintenance/toolhead_variant/detachable_heater_sensor.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class SyncTests(unittest.TestCase):
    def make(self,target=250):
        obj=mod.DetachableHeaterSensor.__new__(mod.DetachableHeaterSensor)
        self.calls=[];obj.maximum=300;obj.dock_pending=False;obj.reconnect=None;obj.valid_samples=9
        obj.failed = False
        obj.dock_exit = None
        obj.print_heat_key = None
        obj.nozzle_heater = N(target_temp=target)
        def set_target(value):
            self.calls.append(value)
            obj.heater.target_temp = value
        obj.heater=N(target_temp=235,set_temp=set_target)
        obj.source=N(get_status=lambda t:{'state':'connected'},gcode=N(respond_info=lambda s:None))
        self.temps=N(depth=0,changing=0,start_tool=None)
        self.tool_status = {'changing': 0, 'is_parked': 0}
        objects={'extruder':N(get_heater=lambda:N(target_temp=target)), 'lugo_tool_temperature':self.temps,
                 'gcode_macro TOOL_STATE':N(get_status=lambda t:self.tool_status)}
        obj.printer=N(lookup_object=lambda name,default=None:objects.get(name,default))
        obj.context=lambda t:(0,'printing','file',False)
        return obj
    def test_update_and_no_repeat(self):
        obj=self.make();obj.sync_print_target(1);obj.sync_print_target(2);self.assertEqual(self.calls,[250])
    def test_off_command(self):
        obj=self.make(0);obj.sync_print_target(1);self.assertEqual(self.calls,[0])
    def test_disabled_stays_off(self):
        obj=self.make();obj.heater.target_temp=0;obj.sync_print_target(1);self.assertEqual(self.calls,[])
    def test_changing_excluded(self):
        obj=self.make();self.temps.changing=1;obj.sync_print_target(1);self.assertEqual(self.calls,[])
    def test_disconnect_excluded(self):
        obj=self.make();obj.source.get_status=lambda t:{'state':'disconnected'};obj.sync_print_target(1);self.assertEqual(self.calls,[])
    def test_idle_excluded(self):
        obj=self.make();obj.context=lambda t:(0,'standby','',False);obj.sync_print_target(1);self.assertEqual(self.calls,[])
    def test_above_limit_switches_off(self):
        obj=self.make(310);obj.sync_print_target(1);self.assertEqual(self.calls,[0])
    def test_cancel_excluded(self):
        obj=self.make();obj.context=lambda t:(0,'printing','file',True);obj.sync_print_target(1);self.assertEqual(self.calls,[])

    def test_catches_up_after_tool_change_without_new_nozzle_command(self):
        obj = self.make()
        self.temps.changing = 1
        obj.sync_print_target(1)
        self.assertEqual(self.calls, [])
        self.temps.changing = 0
        obj.sync_print_target(2)
        self.assertEqual(self.calls, [250])

    def test_parked_target_not_synchronized(self):
        obj = self.make()
        self.tool_status['is_parked'] = 1
        obj.sync_print_target(1)
        self.assertEqual(self.calls, [])

    def test_watchdog_print_sync_ignores_manual_preheat_switch(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                obj = self.make()
                obj.source.sync_manual_preheat = enabled
                obj.check_reconnect = lambda now: None
                manual_ticks = []
                obj.sync_manual_targets = manual_ticks.append
                obj.watchdog(1)
                self.assertEqual(self.calls, [250])
                self.assertEqual(manual_ticks, [1] if enabled else [])

    def test_idle_preheat_can_link_from_either_heater_or_keep_them_separate(self):
        for enabled in (False, True):
            for changed_heater in ('nozzle', 'toolhead'):
                with self.subTest(enabled=enabled, changed_heater=changed_heater):
                    obj = self.make()
                    obj.source.sync_manual_preheat = enabled
                    obj.check_reconnect = lambda now: None
                    obj.context = lambda now: (0, 'standby', '', False)
                    obj.manual_targets = None
                    obj.manual_parked = False
                    obj.minimum = 0.
                    nozzle = N(target_temp=235, min_temp=0., max_temp=300, control=None)
                    nozzle.set_temp = lambda value: setattr(nozzle, 'target_temp', value)
                    obj.nozzle_heater = nozzle
                    obj.heater.control = None
                    obj.manual_controls = (None, None)
                    obj.watchdog(1)
                    changed, other = ((nozzle, obj.heater) if changed_heater == 'nozzle'
                                      else (obj.heater, nozzle))
                    changed.target_temp = 245
                    obj.watchdog(2)
                    self.assertEqual(changed.target_temp, 245)
                    self.assertEqual(other.target_temp, 245 if enabled else 235)
