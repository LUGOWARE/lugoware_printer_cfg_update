"""Bounded, user-started appliance diagnostics. No test runs on load."""
import json
import logging
import math
import statistics
import time
from pathlib import Path


class Diagnostics:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.xy_speed = config.getfloat('xy_speed', 200., minval=10., maxval=200.)
        self.z_speed = config.getfloat('z_speed', 5., minval=1., maxval=5.)
        self.model = config.get('model', 'M').upper()
        if self.model not in ('M', 'L', 'W'):
            raise config.error('Diagnostic model must be M, L or W')
        self.active = False
        self.kind = ''
        self.phase = 'idle'
        self.serial = 0
        self.result = {}
        self.stop_requested = False
        self.saved = {}
        self.samples = []
        self.raw = []
        self.results = {}
        self._owns_mutex = False
        self.printer.register_event_handler('klippy:ready', self.ready)
        self.printer.register_event_handler('klippy:shutdown', self.shutdown)
        self.gcode.register_output_handler(self.output)
        hooks = self.printer.lookup_object('webhooks')
        hooks.register_endpoint('lugo_diagnostics/control', self.control)
        self.gcode.register_command('LUGO_DIAGNOSTICS_STOP', self.stop)
        self.gcode.register_command('HEATER_TEST', self.heater_command)
        self.gcode.register_command('HEATER_TEST_OFF', self.stop)
        self.gcode.register_command('HEATER_TEST_POPUP_CLOSE', self.close_prompt)

    def status(self, name):
        obj = self.printer.lookup_object(name, None)
        return obj.get_status(self.reactor.monotonic()) if obj else {}

    def ready(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.load_results()
        self.timer = self.reactor.register_timer(self.tick, self.reactor.NEVER)
        # Refuse SD print starts while a physical diagnostic owns the machine.
        for name in ('SDCARD_PRINT_FILE', 'M24'):
            original = self.gcode.register_command(name, None)
            if original is not None:
                def guarded(gcmd, original=original):
                    if self.active:
                        raise gcmd.error('Stop diagnostics before starting a print')
                    return original(gcmd)
                self.gcode.register_command(name, guarded)

    def printing(self):
        return (self.status('print_stats').get('state') in ('printing', 'paused')
                or self.status('pause_resume').get('is_paused', False)
                or self.status('virtual_sdcard').get('is_active', False))

    def validate(self, kind, from_command=False):
        if kind not in ('heater', 'motor', 'probe', 'fan'):
            raise ValueError('Unknown diagnostic')
        if self.active or self.printing():
            raise ValueError('Diagnostics require an idle printer')
        if not from_command and self.gcode.get_mutex().test():
            raise ValueError('Wait for the current command to finish')
        for name in self.status('heaters').get('available_heaters', []):
            if self.status(name).get('target', 0) > 0:
                raise ValueError('Turn off heater targets before diagnostics')
        if kind == 'heater' and self.status('extruder').get('temperature', 999) >= 50:
            raise ValueError('Remove the toolhead and wait until the nozzle is below 50°C.')
        if kind in ('motor', 'probe', 'heater', 'fan'):
            sensor = self.status('filament_switch_sensor toolhead_sensor')
            if not sensor or sensor.get('filament_detected', True):
                raise ValueError('Park and remove the toolhead before this test')
            if kind == 'motor':
                self.motor_geometry()
            if kind == 'probe' and set(self.status('toolhead').get('homed_axes', '')) == set('xyz'):
                self.geometry()

    def heater_command(self, gcmd):
        try:
            self.validate('heater', from_command=True)
        except ValueError as exc:
            raise gcmd.error(str(exc))
        self.start('heater')

    def close_prompt(self, gcmd):
        self.gcode.respond_raw('action:prompt_end')

    def load_results(self):
        path = Path.home()/'printer_data/logs/lugoware_diagnostics.jsonl'
        if not path.is_file():
            return
        try:
            # Bounded read; retain complete newest records after a partial tail.
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 1024*1024))
                lines = stream.read().decode('utf-8', errors='replace').splitlines()
            for line in lines:
                try:
                    result = json.loads(line)
                    if result.get('kind') in ('heater', 'motor', 'probe', 'fan'):
                        self.results[result['kind']] = result
                        self.serial = max(self.serial, result.get('serial', 0))
                except (ValueError, TypeError):
                    continue
        except OSError:
            logging.exception('Unable to load diagnostic history')

    def geometry(self):
        st = self.status('toolhead')
        cfg = self.status('configfile')['settings']
        mesh, probe = cfg['bed_mesh'], cfg['probe']
        mn, mx = mesh['mesh_min'], mesh['mesh_max']
        x = (mn[0] + mx[0]) / 2 - probe.get('x_offset', 0)
        y = (mn[1] + mx[1]) / 2 - probe.get('y_offset', 0)
        z = max(10., self.toolhead.get_position()[2])
        lower, upper = st['axis_minimum'], st['axis_maximum']
        if not (lower[0] + 30 < x < upper[0] - 30
                and lower[1] + 30 < y < upper[1] - 30
                and z + 2 < upper[2] - 1):
            raise ValueError('Insufficient clearance for diagnostic movement')
        return x, y, z

    def control(self, request):
        action = request.get_str('action', 'status')
        if action == 'sensor':
            request.send({'detected': self.status('filament_switch_sensor toolhead_sensor').get('filament_detected')})
            return
        if action == 'start':
            kind = request.get_str('kind')
            try:
                self.validate(kind)
            except (ValueError, KeyError) as exc:
                raise request.error(str(exc))
            self.start(kind)
        elif action == 'stop':
            self.stop_requested = True
        elif action != 'status':
            raise request.error('Unknown diagnostic action')
        request.send(self.get_status(self.reactor.monotonic()))

    def start(self, kind):
        self.kind, self.phase = kind, 'starting'
        self.serial += 1
        self.active, self.stop_requested = True, False
        self.started = self.reactor.monotonic()
        self.step = 0
        self.home_checked = False
        self.samples, self.raw, self.saved = [], [], {}
        self.result = {}
        self.data = {}
        self.reactor.update_timer(self.timer, self.reactor.NOW)

    def stop(self, gcmd):
        self.stop_requested = True

    def output(self, line):
        if self.active and self.kind == 'motor':
            self.raw.append(str(line)[:500])
            self.raw = self.raw[-60:]

    def move(self, xyz, speed):
        self.toolhead.manual_move(list(xyz), speed)
        self.toolhead.wait_moves()

    def drivers(self):
        cfg = self.status('configfile')['settings']
        return {name: self.status(name) for name in cfg
                if name.startswith(('tmc5160 stepper_', 'tmc2209 stepper_'))}

    def tick(self, eventtime):
        if not self.active:
            return self.reactor.NEVER
        if self.gcode.get_mutex().test():
            return eventtime + .2
        try:
            with self.gcode.get_mutex():
                self._owns_mutex = True
                try:
                    if self.printing():
                        self.finish('failed', 'A print started; diagnostics interrupted', cleanup=False)
                    elif self.stop_requested:
                        self.finish('stopped', 'Diagnostic stopped')
                    elif eventtime - self.started > (300 if self.kind == 'motor' else 180 if self.kind == 'fan' else 120):
                        self.finish('failed', 'Diagnostic timeout')
                    elif self.kind in ('motor', 'probe', 'heater', 'fan') and self.status(
                            'filament_switch_sensor toolhead_sensor').get('filament_detected', True):
                        self.finish('failed', 'Park and remove the toolhead before this test')
                    elif self.kind in ('motor', 'probe') and not self.home_checked:
                        self.phase = 'homing'
                        self.script('HOME_CHECK')
                        if set(self.status('toolhead').get('homed_axes', '')) != set('xyz'):
                            raise ValueError('HOME_CHECK did not complete XYZ homing')
                        self.home_checked = True
                    else:
                        getattr(self, 'test_' + self.kind)(eventtime)
                finally:
                    self._owns_mutex = False
        except Exception as exc:
            logging.exception('LUGO diagnostic failed')
            self.finish('failed', str(exc))
        return self.reactor.monotonic() + .2 if self.active else self.reactor.NEVER

    def script(self, text):
        if self._owns_mutex:
            self.gcode.run_script_from_command(text)
        else:
            self.gcode.run_script(text)

    def test_heater(self, now):
        if self.step == 0:
            self.saved['heater'] = True
            self.data = {'reference': {'normal': 7., 'degraded': 5.}, 'schema': 2}
            self.script('M104 S0\nSET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=1')
            self.heater_start = float(self.status('extruder')['temperature'])
            self.script('M104 S200')
            self.heater_due = self.reactor.monotonic() + 10.
            self.step = 1
        self.phase = 'heater_running' if self.step != 2 else 'heater_cooling'
        self.data['temperature'] = self.status('extruder').get('temperature')
        self.data['nozzle_fan'] = self.status('heater_fan Hotend_fan')
        self.data['stage'] = self.step
        if now < self.heater_due:
            return
        if self.step in (1, 3):
            heater = 1 if self.step == 1 else 2
            delta = float(self.status('extruder')['temperature']) - self.heater_start
            self.data['delta%d' % heater] = delta
            self.data['result%d' % heater] = self.heater_grade(delta)
            self.script('M104 S0\nSET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0')
        if self.step == 1:
            self.step = 2
            self.phase = 'heater_cooling'
            self.heater_due = self.reactor.monotonic() + 12.
        elif self.step == 2:
            self.heater_start = float(self.status('extruder')['temperature'])
            self.script('SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=2\nM104 S200')
            self.step = 3
            self.heater_due = self.reactor.monotonic() + 10.
        else:
            grades = [self.data['result1'], self.data['result2']]
            outcome = 'failed' if 'fault' in grades else 'warning' if 'degraded' in grades else 'passed'
            self.finish(outcome, 'Heater test complete')

    @staticmethod
    def heater_grade(delta):
        return 'normal' if delta >= 7. else 'degraded' if delta >= 5. else 'fault'

    def motor_geometry(self):
        size = {'M': (230.,230.,250.), 'L': (230.,230.,350.), 'W': (330.,230.,350.)}[self.model]
        limits = self.status('toolhead')
        if any(lo > 0 or hi < target for lo, hi, target in zip(
                limits['axis_minimum'], limits['axis_maximum'], size)):
            raise ValueError('Insufficient clearance for diagnostic movement')
        return size

    def motor_plan(self):
        x,y,z = self.motor_geometry()
        plan = [([None,None,20.], self.z_speed, 'position', 0),
                ([0,y/2,20.], 100., 'position', 0)]
        for cycle in range(1,6):
            plan += [([x,y/2,20.],500.,'x',cycle),([0,y/2,20.],500.,'x',cycle)]
        plan.append(([x/2,0,20.],100.,'position',0))
        for cycle in range(1,6):
            plan += [([x/2,y,20.],500.,'y',cycle),([x/2,0,20.],500.,'y',cycle)]
        plan.append(([0,0,20.],100.,'position',0))
        for cycle in range(1,6):
            plan += [([x,y,20.],500.,'diagonal_a',cycle),([0,0,20.],500.,'diagonal_a',cycle)]
        plan.append(([0,y,20.],100.,'position',0))
        for cycle in range(1,6):
            plan += [([x,0,20.],500.,'diagonal_b',cycle),([0,y,20.],500.,'diagonal_b',cycle)]
        plan.append(([x/2,y/2,20.],100.,'position',0))
        for height in range(0, int(z) + 1, 50):
            plan.append(([None,None,float(height)],40.,'z_up' if height == 0 else 'z_down',1))
            # At the lower travel limit, oscillate inward instead of exceeding it.
            other = height + .5 if height + .5 <= z else height - .5
            for cycle in range(1,21):
                plan += [([None,None,other],40.,'z_repeat',cycle),
                         ([None,None,float(height)],40.,'z_repeat',cycle)]
        plan.append(([None,None,20.],40.,'z_finish',1))
        return plan

    def test_motor(self, now):
        if self.step == 0:
            self.moves = self.motor_plan()
            kin = self.toolhead.get_kinematics()
            if not hasattr(kin, 'max_z_velocity'):
                raise ValueError('Unknown diagnostic')
            limits = self.status('toolhead')
            self.saved['motion_limits'] = (limits['max_velocity'], limits['max_accel'])
            self.script('Probe_Stow')
            self.script('SET_VELOCITY_LIMIT VELOCITY=500 ACCEL=16000')
            self.data = {'model':self.model, 'volume':self.motor_geometry(), 'xy_speed':500.,
                         'xy_accel':16000., 'z_speed':min(40.,kin.max_z_velocity), 'z_accel':kin.max_z_accel,
                         'before':self.drivers(), 'segments':len(self.moves), 'segment':0}
            self.step = 1
        self.phase = 'motor_running'
        while self.step - 1 < len(self.moves):
            if not self.active:
                return
            if self.stop_requested:
                break
            if self.status('filament_switch_sensor toolhead_sensor').get('filament_detected', True):
                self.toolhead.wait_moves()
                self.finish('failed', 'Park and remove the toolhead before this test')
                return
            if self.reactor.monotonic() - self.started > 300:
                self.toolhead.wait_moves()
                self.finish('failed', 'Diagnostic timeout')
                return
            index = self.step - 1
            xyz,speed,activity,cycle = self.moves[index]
            self.data.update(activity=activity, cycle=cycle)
            # Feed Klipper lookahead continuously. Its queue backpressure yields
            # to the reactor, so UI status and stop requests remain serviceable.
            self.toolhead.manual_move(list(xyz), speed)
            self.data['segment'] = index + 1
            self.step += 1
            self.reactor.pause(self.reactor.NOW)
        # Drain only once; never force a stop between individual test moves.
        self.toolhead.wait_moves()
        if not self.active:
            return
        if self.stop_requested:
            self.finish('stopped', 'Diagnostic stopped')
        else:
            self.data['after'] = self.drivers()
            for driver in self.data['after']:
                self.script('DUMP_TMC STEPPER=' + driver.split()[1])
            self.data['registers'] = list(self.raw)
            faults = ('ot', 'otpw', 's2ga', 's2gb', 's2vsa', 's2vsb', 'uv_cp')
            self.data['driver_warnings'] = {name: {k:v for k,v in (state.get('drv_status') or {}).items()
                                                 if k in faults and v}
                                            for name,state in self.data['after'].items()}
            self.finish('warning' if any(self.data['driver_warnings'].values()) else 'review',
                        'Motion finished; inspect noise and missed steps')

    def test_probe(self, now):
        if self.step == 0:
            x, y, z = self.geometry()
            self.saved['probe'] = True
            self.data = {'center': [x, y], 'samples': []}
            self.lift_z = z
            self.move([None, None, z], self.z_speed)
            self.move([x, y, None], 50.)
            self.step = 1
        self.phase = 'probe_running'
        self.script('PROBE SAMPLES=1')
        value = float(self.status('probe')['last_z_result'])
        if not math.isfinite(value):
            raise ValueError('Invalid probe sample')
        self.samples.append(value)
        self.data['samples'] = list(self.samples)
        self.move([None, None, self.toolhead.get_position()[2] + 1.5], self.z_speed)
        if len(self.samples) == 10:
            spread = max(self.samples) - min(self.samples)
            self.data.update(minimum=min(self.samples), maximum=max(self.samples),
                             mean=statistics.mean(self.samples), median=statistics.median(self.samples),
                             stddev=statistics.pstdev(self.samples), spread=spread, reference=.03)
            self.move([None, None, self.lift_z], self.z_speed)
            self.finish('passed' if spread <= .03 else 'warning', 'Probe repeatability test complete')

    def test_fan(self, now):
        if not self.saved.get('fan_test'):
            self.saved['fan_test'] = True
            self.data = {'schema': 3, 'completed': [], 'stage': 0}
            self.script('M106 S0\nSET_FAN_SPEED FAN=chamber_fan SPEED=0')
            self.fan_due = now
        if now < self.fan_due:
            return
        if self.step < 22:
            group, level = divmod(self.step, 11)
            if self.step == 11:
                self.script('M106 S0')
                self.data['completed'].append('part')
            if group == 0:
                self.script('M106 S%d' % round(level * 25.5))
            else:
                self.script('SET_FAN_SPEED FAN=chamber_fan SPEED=%.1f' % (level / 10.))
            self.data.update(stage=group + 1, percent=level * 10)
            self.phase = 'fan_running'
            self.step += 1
            self.fan_due = self.reactor.monotonic() + 2.
        elif self.step == 22:
            self.script('SET_FAN_SPEED FAN=chamber_fan SPEED=0')
            self.data['completed'].append('chamber')
            self.saved['heater'] = True
            self.script('SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0\nM104 S50')
            self.data.update(stage=3, temperature=self.status('extruder')['temperature'])
            self.phase = 'fan_heating'
            self.heat_deadline = now + 90.
            self.step = 23
        elif self.step == 23:
            temperature = self.status('extruder')['temperature']
            self.data['temperature'] = temperature
            if temperature >= 50.:
                self.phase = 'fan_nozzle'
                self.fan_due = self.reactor.monotonic() + 5.
                self.step = 24
            elif now >= self.heat_deadline:
                self.finish('failed', 'Diagnostic timeout')
        else:
            self.data['completed'].append('nozzle')
            self.finish('review', 'Please check that the fans are actually running.')

    def cleanup(self):
        saved, self.saved = self.saved, {}
        scripts = []
        if 'motion_limits' in saved:
            velocity,accel = saved['motion_limits']
            scripts.append('SET_VELOCITY_LIMIT VELOCITY=%.6f ACCEL=%.6f' % (velocity,accel))
        if saved.get('heater'):
            scripts.extend(['M104 S0', 'SET_MULTI_PIN_MODE PIN=dual_hotend_heater MODE=0'])
        if saved.get('probe'):
            scripts.append('Probe_Stow')
        if saved.get('fan_test'):
            scripts += ['M106 S0', 'SET_FAN_SPEED FAN=chamber_fan SPEED=0']
        if 'fans' in saved:
            a, b = saved['fans']
            scripts += ['M106 S%d' % round(a*255), 'SET_FAN_SPEED FAN=chamber_fan SPEED=%.5f' % b]
        for script in scripts:
            try:
                self.script(script)
            except Exception:
                logging.exception('Diagnostic cleanup failed: %s', script)
                self.data.setdefault('cleanup_errors', []).append(script)

    def finish(self, outcome, message, cleanup=True):
        if cleanup:
            self.cleanup()
        self.active = False
        self.phase = outcome
        self.result = {'serial': self.serial, 'kind': self.kind, 'outcome': outcome,
                       'message': message, 'data': self.data,
                       'duration': round(self.reactor.monotonic()-self.started, 2),
                       'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')}
        self.results[self.kind] = self.result
        try:
            path = Path.home()/'printer_data/logs/lugoware_diagnostics.jsonl'
            if path.exists() and path.stat().st_size > 1024*1024:
                path.replace(path.with_suffix('.previous.jsonl'))
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(self.result, ensure_ascii=False) + '\n')
        except Exception:
            logging.exception('Unable to save diagnostic result')

    def shutdown(self):
        if self.active:
            self.finish('failed', 'Printer shutdown; inspect before retrying', cleanup=False)

    def get_status(self, eventtime):
        return {'active': self.active, 'kind': self.kind, 'phase': self.phase,
                'serial': self.serial, 'data': getattr(self, 'data', {}),
                'elapsed': round(eventtime-self.started, 1) if self.active else 0,
                'result': self.result, 'results': self.results,
                'toolhead_sensor': self.status('filament_switch_sensor toolhead_sensor').get('filament_detected')}


def load_config(config):
    return Diagnostics(config)
