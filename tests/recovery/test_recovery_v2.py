import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import copy
from collections import deque
import json
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import Mock
import lugo_recovery as journal
from recovery_index import analyze, locate, validate_checkpoint
from recovery_execution import RecoveryExecution


def checkpoint():
    return {'executed': True, 'offset': 15, 'layer': 3, 'retract_debt': .5,
        'snapshot': {
            'gcode_macro TOOL_STATE': {'active_tool': 1, 'changing': 0, 'toolchange_retract': .5, 'extrude_factor': 1},
            'fast_cancel': {'phase': 'docked'}, 'exclude_object': {},
            'gcode_internal': {'absolute_coord': True, 'allow_absolute_extrude': False,
                'last_position': [100, 100, 4, 0], 'base_position': [0,0,0,0], 'homing_position': [0,0,0,0]},
            'extruder_rotation_distance': 7.1, 'active_mesh': {'points': [[0,0],[0,0]], 'params': {}},
            'extruder': {'target': 220}, 'heater_bed': {'target': 60},
            'toolhead': {'position': [100,100,4,0], 'max_velocity': 300, 'max_accel': 5000,
                        'square_corner_velocity': 5, 'minimum_cruise_ratio': .5}}}


class Tests(unittest.TestCase):
    def test_display_layer_and_execution_offset_share_checkpoint(self):
        r=RecoveryExecution();r.record={'checkpoint':{'offset':112,'layer':999}}
        r.analysis={'layers':[{'offset':0,'layer':1,'height':.25},
                              {'offset':100,'layer':2,'height':.45},
                              {'offset':200,'layer':3,'height':.65}]}
        self.assertEqual(r.resume_point(),{'offset':100,'execution_offset':112,'layer':2,'height':.45})

    def test_auto_z_uses_live_machine_not_layer_or_queued_target(self):
        r=RecoveryExecution();r.record={'snapshot':{
            'motion_report':{'live_position':[0,0,1.237,0]},
            'toolhead':{'homed_axes':'xyz','position':[0,0,9,0]},
            'gcode_move':{'gcode_position':[0,0,1.45,0]},'recorded_at':100}}
        self.assertEqual(r.estimated_stop()['z'],1.237)
        self.assertEqual(r.estimated_stop()['save_interval'],5.)
        r.record['stop_position']={'z':1.038,'recorded_at':104}
        self.assertEqual(r.estimated_stop()['z'],1.038)
        r.record['stop_position']['z']=float('nan')
        self.assertIsNone(r.estimated_stop())

    def test_auto_prepare_ignores_client_supplied_height(self):
        r=RecoveryExecution();r.record={'session':'test','stop_position':{'z':1.2}}
        r.reactor=Obj(monotonic=lambda:10)
        r.validate_resume=Mock(return_value=6.2);r.proposal=lambda:{}
        req=Obj(get_int=lambda name,default=0:1 if name=='checks' else 999,
                get_float=Mock(side_effect=AssertionError('must not read user Z')),
                send=Mock(),error=ValueError)
        r.prepare_resume(req)
        r.validate_resume.assert_called_once_with(-1,1.2)
        self.assertEqual(r.resume_token['physical_z'],1.2)

    def test_position_sampling_is_bounded_async_and_skips_unhomed(self):
        r=journal.Recovery.__new__(journal.Recovery);r.record={};r.submit=Mock()
        homed=['xyz']
        r.status=lambda n,t: {'homed_axes':homed[0]} if n=='toolhead' else {'live_position':[1,2,t,0]}
        for t in (10.,10.25,10.5,10.75):r.observe_position(t)
        self.assertEqual(r.submit.call_count,1)
        self.assertEqual(r.record['stop_position']['z'],10.75)
        r.observe_position(11.);self.assertEqual(r.submit.call_count,2)
        homed[0]='xy';r.observe_position(12.)
        self.assertEqual(r.record['stop_position']['z'],11.)

    def test_real_file_layer_and_identity(self):
        path = Path(__file__).with_name('sample.gcode')
        if not path.exists(): self.skipTest('local sample')
        result = analyze(path)
        self.assertEqual(len(result['layers']), 240)
        self.assertEqual(locate(result['layers'],153797)['layer'],4)
        self.assertEqual(locate(result['layers'],153797)['height'],.85)
        self.assertIsNone(locate(result['layers'],0))

    def test_byte_offsets_crlf_unicode(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sample.gcode'
            raw=';한글\r\n;LAYER_CHANGE\r\n;Z:0.2\r\nG1 X1\r\n;LAYER_CHANGE\r\n;Z:0.4\r\n'.encode()
            path.write_bytes(raw);result=analyze(path)
            self.assertEqual(result['layers'][0]['offset'],len(';한글\r\n'.encode()))
            self.assertEqual(locate(result['layers'],len(raw))['layer'],2)

    def test_incomplete_and_unsafe_checkpoints(self):
        self.assertTrue(validate_checkpoint(None))
        cp=checkpoint();self.assertEqual(validate_checkpoint(cp),'')
        variants=[('executed',False)]
        cp['executed']=False;self.assertTrue(validate_checkpoint(cp))
        cp=checkpoint();cp['snapshot']['exclude_object']['excluded_objects']=['A'];self.assertTrue(validate_checkpoint(cp))
        cp=checkpoint();cp['snapshot']['gcode_macro TOOL_STATE']['changing']=1;self.assertTrue(validate_checkpoint(cp))
        cp=checkpoint();cp['snapshot']['gcode_internal']['last_position'][2]=float('nan');self.assertTrue(validate_checkpoint(cp))

    def test_status_never_motion_and_legacy_not_executable(self):
        r=RecoveryExecution();r.record={'snapshot':{'virtual_sdcard':{'file_position':20}}};r.analysis=None
        self.assertFalse(r.proposal()['can_prepare'])
        self.assertTrue(r.proposal()['legacy'])

    def test_setup_order_no_z_home_or_start_print(self):
        r=RecoveryExecution();cp=checkpoint();calls=[]
        gm=Obj(saved_states={})
        th=Obj(manual_move=lambda p,s:calls.append(('move',p,s)),wait_moves=lambda:calls.append(('wait',)))
        macros={n:Obj(variables=dict(cp['snapshot'].get('gcode_macro '+n,{}))) for n in ('TOOL_STATE','FIRSTDOCK_STATE','Z_OFFSET_TRACKER')}
        objects={'gcode_move':gm,'toolhead':th,'bed_mesh':Obj(set_mesh=lambda m:calls.append(('mesh',)))}
        objects.update({'gcode_macro '+n:v for n,v in macros.items()})
        r.printer=Obj(lookup_object=lambda name,default=None:objects.get(name,default))
        r.reactor=Obj(monotonic=lambda:0)
        r.station_approach=lambda:(230.,9000.)
        r.status=lambda name,t: {'settings':{'printer':{'max_velocity':500,'max_z_velocity':30}}} if name=='configfile' else {'filament_detected':True}
        r.make_mesh=lambda saved:'mesh'
        r.execute_setup(cp,{'physical_z':4,'clearance':9},lambda s:calls.append(s))
        lines='\n'.join(v for v in calls if isinstance(v,str)).splitlines()
        self.assertNotIn('G28',lines);self.assertNotIn('G28 Z',lines)
        self.assertNotIn('START_PRINT',lines)
        self.assertIn('SET_EXTRUDER_ROTATION_DISTANCE EXTRUDER=extruder DISTANCE=7.10000000', lines)
        self.assertLess(lines.index('G1 Z9.000000 F600'),lines.index('G28 X'))
        self.assertLess(lines.index('G28 X'),lines.index('G28 Y'))
        self.assertTrue(any(v.startswith('DOCK_TOOL_1 ') for v in lines))
        dock = next(i for i, v in enumerate(lines) if v.startswith('DOCK_TOOL_1 '))
        post_waits = [v for v in lines[dock+1:] if v.startswith('TEMPERATURE_WAIT')]
        self.assertEqual(post_waits, ['TEMPERATURE_WAIT SENSOR=extruder MINIMUM=218.000'])
        moves=[v for v in calls if isinstance(v,tuple) and v[0]=='move']
        self.assertEqual(moves[0][1],[100,100,None])
        self.assertEqual(moves[1][1],[None,None,4])
        self.assertEqual(moves[0][2],500.)
        self.assertEqual(moves[1][2],30.)
        self.assertIn('G1 X230.000000 F9000.000000',lines)
        self.assertEqual(gm.saved_states['_LUGO_RECOVERY'],cp['snapshot']['gcode_internal'])

    def test_checkpoint_waits_for_mcu_time(self):
        r=journal.Recovery.__new__(journal.Recovery)
        r.reactor=Obj(monotonic=lambda:10.)
        cp=checkpoint();cp.update(executed=False,print_time=50)
        r.printer=Obj(is_shutdown=lambda:False)
        r.execution_pending=deque([cp]);r.record={'session':'test','history':[]};r.running=True
        r.last_save=10;r.last_layer=None;r.pending=queue.Queue(1)
        estimated=[49]
        r.status=lambda name,t:({'estimated_print_time':estimated[0]} if name=='toolhead' else {'state':'printing','info':{}})
        r.tick(10);self.assertNotIn('checkpoint',r.record)
        estimated[0]=50.2;r.tick(10.1)
        self.assertTrue(r.record['checkpoint']['executed'])
        self.assertEqual(r.pending.qsize(),1)

    def test_shutdown_cannot_replace_checkpoint_with_empty_session(self):
        r=journal.Recovery.__new__(journal.Recovery)
        r.printer=Obj(is_shutdown=lambda:True)
        r.record={'session':'original','checkpoint':checkpoint(),'status':'interrupted'}
        r.running=False
        r.status=Mock(return_value={'state':'printing','info':{}})
        r.begin=Mock()
        before=copy.deepcopy(r.record)
        self.assertEqual(r.tick(42),43)
        r.begin.assert_not_called()
        r.status.assert_not_called()
        self.assertEqual(r.record,before)

    def test_observer_failure_does_not_abort_print(self):
        r=journal.Recovery.__new__(journal.Recovery)
        r.recovering=False;r.retract_debt=0
        calls=[];gm=Obj(last_position=[0,0,0,0])
        handlers={'TEMPERATURE_WAIT':lambda cmd:None}
        def register(name,fn):
            old=handlers.get(name);handlers[name]=fn;return old
        gcode=Obj(run_script=lambda s:calls.append(s),register_command=register,_process_commands=lambda cmds,ack:None)
        sd=Obj(is_cmd_from_sd=lambda:True)
        r.printer=Obj(lookup_object=lambda name:{'gcode':gcode,'virtual_sdcard':sd,'gcode_move':gm}[name])
        r.observe_layer=Mock(side_effect=ValueError('bad journal'))
        r.install_observer()
        with self.assertLogs(level='ERROR'):gcode.run_script(';LAYER_CHANGE')
        self.assertEqual(calls,[';LAYER_CHANGE'])

    def test_invalid_token_cannot_move(self):
        r=RecoveryExecution();r.resume_token=None
        cmd=Obj(error=ValueError)
        with self.assertRaises(ValueError):r.resume_command(cmd)

    def test_abort_signal(self):
        r=RecoveryExecution();r.abort_requested=True
        r.printer=Obj(lookup_object=lambda name,default=None:Obj(error=ValueError) if name=='gcode' else None,is_shutdown=lambda:False)
        with self.assertRaisesRegex(ValueError,'cancelled'):r.check_recovery_abort()

    def test_preflight_rejects_changed_file_config_sensor_and_height(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'print.gcode';path.write_text(';LAYER_CHANGE\n;Z:4\nG1 X100\n')
            r=RecoveryExecution();r.analysis=analyze(path)
            r.record={'filename':path.name,'checkpoint':checkpoint(),'config_signature':'same',
                      'stop_position':{'z':10.,'recorded_at':100.}}
            r.config_hash=lambda:'same';r.make_mesh=Mock();r.station_approach=lambda:(230.,9000.)
            sensor=[False]
            r.reactor=Obj(monotonic=lambda:10)
            r.printer=Obj(is_shutdown=lambda:False,lookup_object=lambda name:Obj(sdcard_dirname=folder))
            r.status=lambda name,t: {'filament_detected':sensor[0]} if name.startswith('filament') else (
                {'axis_minimum':[-2,-2,-4], 'axis_maximum':[277,257,275]} if name=='toolhead' else
                {'settings':{'homing_override':{'axes':'z'}}})
            self.assertEqual(r.validate_resume(-1,10),15)
            sensor[0]=True
            with self.assertRaises(ValueError):r.validate_resume(-1,10)
            sensor[0]=False
            for z in (float('nan'), float('inf'), 274, -5):
                with self.assertRaises(ValueError):r.validate_resume(-1,z)
            r.config_hash=lambda:'changed'
            with self.assertRaisesRegex(ValueError,'configuration'):r.validate_resume(-1,10)
            r.config_hash=lambda:'same';path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'file has changed'):r.validate_resume(-1,10)


if __name__=='__main__':unittest.main()
