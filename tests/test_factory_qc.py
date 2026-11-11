import configparser
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).parents[1]/'maintenance/diagnostics'))
from lugo_factory_qc import FactoryQC, route

class Fake:
    def __init__(self):
        self.clock=0.;self.active=True;self.stop_requested=False;self.started=0.;self.phase='';self.data={};self.commands=[];self.model='M'
        self.reactor=SimpleNamespace(monotonic=lambda:self.clock,pause=lambda _:None,NOW=0.)
        self.toolhead=SimpleNamespace(manual_move=lambda xyz,speed:self.advance(),wait_moves=lambda:None,
          get_kinematics=lambda:SimpleNamespace(max_z_velocity=40),dwell=lambda t:None,get_last_move_time=lambda:0)
        self.printer=SimpleNamespace(lookup_object=lambda _:SimpleNamespace(mcu_probe=SimpleNamespace(query_endstop=lambda _:False)))
    def advance(self):self.clock+=.01
    def validate(self,kind):pass
    def motor_geometry(self):return 230,230,270
    def status(self,name):
        if name=='filament_switch_sensor toolhead_sensor':return {'filament_detected':False}
        if name=='extruder':return {'temperature':25}
        if name=='configfile':return {'settings':self.cfg}
        if name=='toolhead':return {'axis_minimum':[-10,-10,-10],'axis_maximum':[280,270,270],'max_velocity':300,'max_accel':5000,'homed_axes':'xyz'}
        if name=='probe_auto_recovery':return {'last_samples':[.1,.101,.102]}
        return {}
    def start(self,kind):self.kind=kind;self.active=True
    def script(self,cmd):self.commands.append(cmd)
    def move(self,*a):pass
    def geometry(self):return 100,100,20
    def printing(self):return False
    def finish(self,outcome,message):self.outcome=outcome;self.active=False;self.factory.cleanup()

class TimedTests(unittest.TestCase):
    def setUp(self):
        cfg=configparser.RawConfigParser(strict=False)
        cfg.read(Path(__file__).parent/'fixtures/factory_qc_routes.cfg',encoding='utf8')
        self.h=Fake();self.h.cfg={s.lower():dict(cfg[s]) for s in cfg.sections()}
        self.h.cfg['extruder']['max_temp']=350;self.h.cfg['heater_bed']['max_temp']=130
        self.f=FactoryQC(self.h);self.h.factory=self.f
    def test_routes_all_tools_no_extrusion(self):
        for n in range(4):
            d=route(self.h.cfg[f'gcode_macro dock_{n}']['gcode'])
            p=route(self.h.cfg[f'gcode_macro park_{n}']['gcode'],True)
            self.assertGreater(len(d),20);self.assertGreater(len(p),5)
            self.assertTrue(all(len(xyz)==3 and xyz[2] is None for xyz,_ in d+p))
    def test_bad_route_rejected(self):
        with self.assertRaises(ValueError):route('G1 X{x} F6000')
        with self.assertRaises(ValueError):route('G1 X1 F6000',True)
    def test_each_duration_and_cleanup(self):
        for minutes in (5,30,60):
            self.f.begin(minutes,'a'*32);self.f.cleanup()
            self.assertIn('TURN_OFF_HEATERS',self.h.commands)
            self.h.active=False
    def test_home_heats_without_wait(self):
        self.f.begin(5,'a'*32);self.f.tick(0)
        commands='\n'.join(self.h.commands)
        self.assertIn('G28',commands);self.assertIn('M104 S250',commands);self.assertIn('M140 S60',commands)
        self.assertNotIn('TEMPERATURE_WAIT',commands)
    def test_lease_expiry(self):
        self.f.begin(5,'a'*32);self.h.clock=46
        with self.assertRaisesRegex(ValueError,'connection lost'):self.f.tick(46)
    def test_wrong_heartbeat_rejected(self):
        self.f.begin(5,'a'*32)
        with self.assertRaises(ValueError):self.f.heartbeat('b'*32)
    def test_three_rounds_in_five_minute_mode(self):
        self.f.begin(5,'a'*32);self.f.phase='docking';self.f.test_start=-1000
        for n in range(12):
            self.f.heartbeat('a'*32);self.f.tick(self.h.clock)
            if n<11:self.assertEqual(self.f.phase,'docking')
        self.assertEqual(self.f.phase,'motor');self.assertEqual(self.f.rounds,3)
    def test_long_modes_keep_five_rounds(self):
        for minutes in (30,60):
            self.h.active=False
            self.f.begin(minutes,'a'*32);self.f.phase='docking';self.f.test_start=-10000
            for n in range(20):
                self.f.heartbeat('a'*32);self.f.tick(self.h.clock)
                if n<19:self.assertEqual(self.f.phase,'docking')
            self.assertEqual(self.f.phase,'motor');self.assertEqual(self.f.rounds,5)

    def test_parking_detected_stops(self):
        self.f.begin(5,'a'*32);self.f.current_tool=0
        old=self.h.status
        self.h.status=lambda n:{'filament_detected':True} if n=='filament_switch_sensor toolhead_sensor' else old(n)
        with self.assertRaisesRegex(ValueError,'still detected'):self.f.park()
    def test_finish_at_probe_phase(self):
        self.f.begin(5,'a'*32);self.f.phase='probe';self.f.test_start=-400;self.f.deploys=10;self.f.probe_sets=9;self.f.probe_z=20
        self.f.tick(0);self.assertEqual(self.h.outcome,'review');self.assertFalse(self.h.active)



if __name__=='__main__':unittest.main()
