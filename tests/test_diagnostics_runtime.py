import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as Obj
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('diag', ROOT.parent/'maintenance/diagnostics/lugo_diagnostics.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Lock:
    locked = False
    def test(self): return self.locked
    def __enter__(self):
        assert not self.locked
        self.locked = True
    def __exit__(self, *args): self.locked = False


class Fixture:
    def __init__(self):
        self.now, self.moves, self.scripts = 0., [], []
        self.pos = [100., 100., 10., 0.]
        self.states = {
            'print_stats': {'state': 'standby'}, 'pause_resume': {'is_paused': False},
            'virtual_sdcard': {'is_active': False},
            'toolhead': {'homed_axes': 'xyz', 'axis_minimum': [-2., -2., -4.], 'axis_maximum': [277.,257.,275.]},
            'configfile': {'settings': {'bed_mesh': {'mesh_min':[0,27],'mesh_max':[200,240]}, 'probe': {'x_offset':-30.7,'y_offset':28.5}}},
            'heaters': {'available_heaters': ['extruder', 'heater_bed']},
            'extruder': {'temperature': 25., 'target': 0}, 'heater_bed': {'target': 0},
            'filament_switch_sensor toolhead_sensor': {'filament_detected': False, 'enabled': True},
            'gcode_macro _HEATER_TEST_STATE': {'running': 0},
            'probe': {'last_z_result': .1}, 'fan': {'speed': .2},
            'fan_generic chamber_fan': {'speed': .7}, 'heater_fan Hotend_fan': {'speed': 0},
        }
        self.commands, self.endpoints = {}, {}
        self.lock = Lock()
        self.gcode = Obj(register_command=self.register, register_output_handler=lambda f:None,
                         get_mutex=lambda:self.lock, run_script=self.script,
                         run_script_from_command=self.script)
        self.reactor = Obj(NOW=0, NEVER=1e99, monotonic=lambda:self.now,
                           register_timer=lambda *a:1, update_timer=lambda *a:None, pause=lambda t:None)
        self.kin=Obj(max_z_velocity=40.,max_z_accel=500.)
        self.states['toolhead'].update(max_velocity=1100.,max_accel=16000.)
        self.toolhead = Obj(get_kinematics=lambda:self.kin, get_position=lambda:list(self.pos), manual_move=self.move, wait_moves=lambda:None,
                            get_status=lambda t:self.states['toolhead'].copy())
        self.objects = {'gcode':self.gcode, 'toolhead':self.toolhead,
                        'webhooks':Obj(register_endpoint=lambda n,f:self.endpoints.update({n:f}))}
        self.printer = Obj(get_reactor=lambda:self.reactor, lookup_object=self.lookup,
                           register_event_handler=lambda *a:None)
        config=Obj(get=lambda n,d:d, get_printer=lambda:self.printer, getfloat=lambda n,d,**kw:d)
        self.d = module.Diagnostics(config)
        self.d.ready()

    def register(self,name,cb):
        old = self.commands.pop(name, None)
        if cb is not None:self.commands[name]=cb
        return old
    def lookup(self,name,default=None):
        if name in self.objects:return self.objects[name]
        if name in self.states:return Obj(get_status=lambda t:self.states[name].copy())
        return default
    def script(self,text):
        self.scripts.append(text)
        if text == 'PROBE SAMPLES=1':
            self.states['probe']['last_z_result'] += .001
        elif text == 'HOME_CHECK':self.states['toolhead']['homed_axes']='xyz'
    def move(self,coord,speed):
        self.moves.append((coord,speed))
        for i,v in enumerate(coord):
            if v is not None:self.pos[i]=v
    def tick(self,seconds=1):
        self.now+=seconds
        self.d.tick(self.now)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        (Path(self.tmp.name)/'printer_data/logs').mkdir(parents=True)
        self.patch=patch.object(module.Path,'home',return_value=Path(self.tmp.name));self.patch.start()
        self.f=Fixture()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()

    def test_load_and_status_never_move_or_heat(self):
        self.f.d.get_status(0)
        self.assertFalse(self.f.moves or self.f.scripts)

    def test_interlocks(self):
        for kind in ('heater','motor','probe','fan'):
            self.f.states['print_stats']['state']='paused'
            with self.assertRaises(ValueError):self.f.d.validate(kind)
        self.f.states['print_stats']['state']='standby'
        self.f.states['toolhead']['homed_axes']='xy'
        self.f.d.validate('motor')  # HOME_CHECK is executed after confirmation.
        self.f.states['toolhead']['homed_axes']='xyz'
        self.f.states['filament_switch_sensor toolhead_sensor']['filament_detected']=True
        with self.assertRaises(ValueError):self.f.d.validate('probe')
        self.f.states['extruder']['target']=50
        with self.assertRaises(ValueError):self.f.d.validate('fan')
        self.assertFalse(self.f.moves or self.f.scripts)

    def test_probe_repeatability_no_save_and_stop(self):
        self.f.d.validate('probe');self.f.d.start('probe')
        for _ in range(11):self.f.tick()
        self.assertFalse(self.f.d.active)
        self.assertEqual(len(self.f.d.data['samples']),10)
        self.assertAlmostEqual(self.f.d.data['spread'],.009)
        self.assertEqual(self.f.d.phase,'passed')
        self.assertNotIn('SAVE_CONFIG', '\n'.join(self.f.scripts))
        self.assertEqual(self.f.scripts[-1],'Probe_Stow')
        self.f.d.start('probe');self.f.tick()
        count=len(self.f.moves);self.f.d.stop(None);self.f.tick()
        self.assertEqual(len(self.f.moves),count)
        self.assertEqual(self.f.d.phase,'stopped')

    def test_motor_models_and_restore(self):
        for model,vol in [('M',(230,230,250)),('L',(230,230,350)),('W',(330,230,350))]:
            self.f.d.model=model
            self.f.states['toolhead']['axis_maximum']=[400,300,400]
            plan=self.f.d.motor_plan()
            for axis in ('x','y','diagonal_a','diagonal_b'):
                self.assertEqual(sum(p[2]==axis for p in plan),10)
            self.assertEqual(plan[-1][0],[None,None,20.])
            self.assertEqual(next(p[0][2] for p in plan if p[2]=='z_down'),vol[2])
            self.assertEqual(sum(p[2]=='z_repeat' for p in plan),40)
            self.assertEqual({p[0][2] for p in plan if p[2]=='z_repeat'},{0.,.5})
            activities=[p[2] for p in plan]
            self.assertLess(max(i for i,a in enumerate(activities) if a=='diagonal_a'), min(i for i,a in enumerate(activities) if a=='diagonal_b'))
        self.f.d.start('motor')
        for _ in range(100):self.f.tick(.2)
        self.assertFalse(self.f.d.active)
        self.assertEqual(self.f.kin.max_z_velocity,40.)
        self.assertIn('SET_VELOCITY_LIMIT VELOCITY=1100.000000 ACCEL=16000.000000',self.f.scripts)

    def test_motor_cancel_restores(self):
        waits=[]
        self.f.toolhead.wait_moves=lambda:waits.append(1)
        def interrupt(t):
            if len(self.f.moves)>=4:self.f.d.stop_requested=True
        self.f.reactor.pause=interrupt
        self.f.d.start('motor');self.f.tick();self.f.tick()
        self.assertEqual(len(self.f.moves),4)
        self.assertEqual(len(waits),1)
        self.assertEqual(self.f.kin.max_z_velocity,40.)
        self.assertFalse(self.f.d.active)
        self.assertEqual(self.f.d.result['outcome'],'stopped')

    def test_motor_waits_only_at_end(self):
        waits=[]
        self.f.toolhead.wait_moves=lambda:waits.append(len(self.f.moves))
        self.f.d.start('motor');self.f.tick();self.f.tick()
        self.assertEqual(waits,[len(self.f.d.motor_plan())])
        self.assertFalse(self.f.d.active)

    def test_model_bounds(self):
        self.f.d.model='W'
        with self.assertRaises(ValueError):self.f.d.motor_plan()

    def test_fan_ramps_and_heat(self):
        self.f.d.start('fan')
        for _ in range(23):self.f.tick(2)
        self.assertIn('M104 S50', self.f.scripts[-1])
        self.assertEqual(self.f.d.data['completed'], ['part', 'chamber'])
        for level in range(11):
            self.assertIn('M106 S%d' % round(level*25.5), self.f.scripts)
            self.assertIn('SET_FAN_SPEED FAN=chamber_fan SPEED=%.1f' % (level/10), self.f.scripts)
        self.f.states['extruder']['temperature']=50
        self.f.tick(.2)
        self.f.tick(4.9)
        self.assertTrue(self.f.d.active)
        self.f.tick(.2)
        self.assertFalse(self.f.d.active)
        self.assertIn('M104 S0', self.f.scripts)
        self.assertEqual(self.f.scripts[-2:], ['M106 S0', 'SET_FAN_SPEED FAN=chamber_fan SPEED=0'])

    def test_fan_heat_timeout(self):
        self.f.d.start('fan')
        for _ in range(23):self.f.tick(2)
        self.f.tick(91)
        self.assertFalse(self.f.d.active)
        self.assertEqual(self.f.d.result['outcome'], 'failed')
        self.assertIn('M104 S0', self.f.scripts)

    def test_sensor_is_read_only(self):
        self.assertFalse(self.f.d.get_status(0)['toolhead_sensor'])
        self.f.states['filament_switch_sensor toolhead_sensor']['filament_detected']=True
        self.assertTrue(self.f.d.get_status(0)['toolhead_sensor'])
        self.assertFalse(self.f.scripts or self.f.moves)
        with self.assertRaises(ValueError):self.f.d.validate('sensor')

    def test_heater_stop_turns_off_and_restores_mode(self):
        self.f.d.start('heater');self.f.tick();self.f.d.stop(None);self.f.tick()
        self.assertEqual(self.f.scripts[-2:],['M104 S0','SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0'])
        self.assertNotIn('HEATER_TEST','\n'.join(self.f.scripts))

    def test_heater_thresholds_and_initial_interlocks(self):
        self.assertEqual(self.f.d.heater_grade(4.999),'fault')
        self.assertEqual(self.f.d.heater_grade(5),'degraded')
        self.assertEqual(self.f.d.heater_grade(6.999),'degraded')
        self.assertEqual(self.f.d.heater_grade(7),'normal')
        self.f.states['extruder']['temperature']=50
        with self.assertRaises(ValueError):self.f.d.validate('heater')
        self.f.states['extruder']['temperature']=49.99
        self.f.d.validate('heater')
        self.f.states['filament_switch_sensor toolhead_sensor']['filament_detected']=True
        with self.assertRaises(ValueError):self.f.d.validate('heater')

    def test_heater_two_timed_stages_and_history(self):
        self.f.d.start('heater');self.f.tick()
        self.f.states['extruder']['temperature']=31
        self.f.tick(10)
        self.assertEqual(self.f.d.data['result1'],'degraded')
        self.f.states['extruder']['temperature']=30
        self.f.tick(12)
        self.f.states['extruder']['temperature']=37
        self.f.tick(10)
        self.assertEqual(self.f.d.data['result2'],'normal')
        self.assertEqual(self.f.d.phase,'warning')
        self.assertFalse(self.f.d.active)
        self.assertEqual(self.f.scripts[-2:],['M104 S0','SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0'])
        restored=Fixture()
        self.assertEqual(restored.d.results['heater']['data']['delta2'],7)
        self.assertTrue(restored.d.results['heater']['timestamp'])

    def test_locked_command_defers_test(self):
        self.f.d.start('motor');self.f.lock.locked=True;self.f.tick()
        self.assertFalse(self.f.moves or self.f.scripts)
        self.f.lock.locked=False;self.f.tick()
        self.assertEqual(self.f.scripts,['HOME_CHECK'])
        self.f.tick()
        self.assertEqual(len(self.f.moves),len(self.f.d.motor_plan()))


if __name__=='__main__':unittest.main()
