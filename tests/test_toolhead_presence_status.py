from pathlib import Path
import sys,types,unittest
patched=(Path(__file__).resolve().parents[1]/'maintenance/toolhead_variant/temperature_toolhead_sensor.py').read_text(encoding='utf-8')
pkg=types.ModuleType('cancel14_test');pkg.__path__=[];sys.modules[pkg.__name__]=pkg
stub=types.ModuleType('cancel14_test.filament_switch_sensor');stub.RunoutHelper=object;sys.modules[stub.__name__]=stub
mod=types.ModuleType('cancel14_test.sensor');mod.__package__=pkg.__name__;exec(compile(patched,'sensor.py','exec'),mod.__dict__)
class Tests(unittest.TestCase):
    def status(self,state,previous):
        obj=mod.TemperatureToolheadSensor.__new__(mod.TemperatureToolheadSensor)
        obj.runout_helper=types.SimpleNamespace(get_status=lambda t:dict(filament_detected=previous,enabled=True))
        obj.sensor=types.SimpleNamespace(get_status=lambda t:dict(state=state,temperature=None))
        return obj.get_status(42)
    def test_disconnect_does_not_wait_for_poll(self): self.assertFalse(self.status('disconnected',True)['filament_detected'])
    def test_connected_still_blocks_parking_return(self): self.assertTrue(self.status('connected',True)['filament_detected'])
    def test_reconnect_immediately_visible(self): self.assertTrue(self.status('connected',False)['filament_detected'])
    def test_unknown_state_does_not_clear_attached_guard(self):
        for state in ('stale','invalid','short_circuit'):
            self.assertTrue(self.status(state,True)['filament_detected'])
    def test_enabled_preserved(self): self.assertTrue(self.status('disconnected',True)['enabled'])
if __name__ == '__main__': unittest.main()
