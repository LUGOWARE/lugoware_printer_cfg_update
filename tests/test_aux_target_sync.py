import importlib.util
from pathlib import Path
from types import SimpleNamespace as N
import unittest
spec=importlib.util.spec_from_file_location('aux',Path(__file__).resolve().parents[1]/'maintenance/toolhead_variant/detachable_heater_sensor.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class SyncTests(unittest.TestCase):
    def make(self,target=250):
        obj=mod.DetachableHeaterSensor.__new__(mod.DetachableHeaterSensor)
        self.calls=[];obj.last_nozzle_target=235;obj.maximum=300;obj.dock_pending=False;obj.reconnect=None;obj.valid_samples=9
        obj.heater=N(target_temp=235,set_temp=self.calls.append)
        obj.source=N(get_status=lambda t:{'state':'connected'},gcode=N(respond_info=lambda s:None))
        self.temps=N(depth=0,changing=0,start_tool=None)
        objects={'extruder':N(get_heater=lambda:N(target_temp=target)), 'lugo_tool_temperature':self.temps,
                 'gcode_macro TOOL_STATE':N(get_status=lambda t:{'changing':0})}
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
