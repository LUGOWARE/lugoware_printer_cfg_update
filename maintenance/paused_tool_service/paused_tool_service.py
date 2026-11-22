"""Service a selected tool while an SD print remains parked and paused."""
import math


SERVICE_X = 0.
SERVICE_Y = 125.
SERVICE_TRAVEL_FEED = 20000


class PausedToolService:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.session = None
        self.phase = 'idle'
        self.slot = None
        self.z = None
        self.position = None
        self.restore_switch = False
        self.gcode.register_command('PAUSED_TOOL_DOCK', self.dock)
        self.gcode.register_command('PAUSED_TOOL_PARK', self.park)
        self.printer.register_event_handler('klippy:ready', self.ready)

    def ready(self):
        self.reactor.register_timer(self.watchdog, self.reactor.NOW)

    def watchdog(self, eventtime):
        if self.service_attached() and not self.printer.is_shutdown():
            head = self.printer.lookup_object('toolhead').get_status(eventtime)
            if (set(head['homed_axes']) != set('xyz')
                    or any(abs(a - b) > .12 for a, b in zip(self.position, head['position']))
                    or self.sensor_status(eventtime)['state'] != 'connected'):
                self.fault()
        return eventtime + .25

    def present(self):
        sd = self.printer.lookup_object('virtual_sdcard', None)
        return self.session is not None and sd is not None and sd.current_file is self.session

    def service_attached(self):
        return self.present() and self.phase == 'attached'

    def motion_locked(self):
        return self.present() and self.phase in ('docking', 'parking', 'attached')

    def get_status(self, _eventtime):
        phase = self.phase if self.present() else 'idle'
        return {'phase': phase, 'tool': self.slot if self.present() else None,
                'blocks_resume': phase != 'idle'}

    def assert_paused(self, gcmd):
        fast = self.printer.lookup_object('fast_cancel')
        pause = self.printer.lookup_object('pause_resume')
        sd = self.printer.lookup_object('virtual_sdcard')
        now = self.reactor.monotonic()
        if (self.printer.is_shutdown() or not pause.is_paused or not pause.sd_paused
                or sd.current_file is None or sd.is_active() or fast.requested or fast.cleaning
                or fast.phase == 'dock_sensor_hold'
                or self.printer.lookup_object('print_stats').get_status(now)['state'] != 'paused'):
            raise gcmd.error('일반 출력 일시정지 상태에서만 툴을 가져오거나 거치할 수 있습니다.')
        return sd

    def heaters(self):
        nozzle = self.printer.lookup_object('extruder').get_heater()
        auxiliary = self.printer.lookup_object('heater_generic Toolhead', None)
        return (nozzle,) if auxiliary is None else (nozzle, auxiliary)

    def manual_heat(self, gcmd, original):
        self.assert_paused(gcmd)
        target = gcmd.get_float('S', 0., minval=0.)
        nozzle, *auxiliary = self.heaters()
        if not math.isfinite(target) or (target and not nozzle.min_temp <= target <= nozzle.max_temp):
            raise gcmd.error('허용 온도 범위 안에서 노즐 목표를 설정해 주세요.')
        if target:
            self.require_position(gcmd)
            self.wait_sensor(gcmd, 'connected')
        source = self.auxiliary_sensor()
        if auxiliary and source is not None and source.sync_manual_preheat:
            aux = auxiliary[0]
            aux.set_temp(target if target <= aux.max_temp else 0.)
        return original(gcmd)

    def auxiliary_sensor(self):
        return self.printer.lookup_object('toolhead_auxiliary', None)

    def sensor_status(self, now):
        source = self.auxiliary_sensor()
        if source is not None:
            return source.get_status(now)
        switch = self.printer.lookup_object('filament_switch_sensor toolhead_sensor')
        return {'state': 'connected' if switch.get_status(now)['filament_detected'] else 'disconnected'}

    def wait_sensor(self, gcmd, expected):
        source = self.auxiliary_sensor()
        deadline = self.reactor.monotonic() + 3.
        stable_since = None
        while True:
            self.assert_paused(gcmd)
            now = self.reactor.monotonic()
            status = self.sensor_status(now)
            state = status['state']
            if state == expected:
                if source is None:
                    stable_since = now if stable_since is None else stable_since
                    if now - stable_since >= .2:
                        return
                else:
                    if state == 'disconnected':
                        return
                    adapter = source.heater_adapter
                    temperature = status['temperature']
                    if (adapter and not adapter.failed and adapter.valid_samples >= 9
                            and temperature is not None and adapter.minimum <= temperature <= adapter.maximum):
                        return
            else:
                stable_since = None
            if state in ('short_circuit', 'invalid', 'stale') or now >= deadline:
                raise gcmd.error('툴 센서 상태를 확인할 수 없습니다. 툴 체결 상태를 확인해 주세요.')
            self.reactor.pause(now + .1)

    def pose(self, gcmd):
        now = self.reactor.monotonic()
        head = self.printer.lookup_object('toolhead').get_status(now)
        move = self.printer.lookup_object('gcode_move').get_status(now)
        if (set(head['homed_axes']) != set('xyz')
                or any(abs(head['position'][i] - move['gcode_position'][i]) > .1 for i in (0, 1))):
            raise gcmd.error('원점 또는 XY 좌표가 달라져 툴 이동을 시작할 수 없습니다.')
        if not (head['axis_minimum'][0] <= SERVICE_X <= head['axis_maximum'][0]
                and head['axis_minimum'][1] <= SERVICE_Y <= head['axis_maximum'][1]):
            raise gcmd.error('정비 위치가 기기 XY 범위를 벗어났습니다.')
        return tuple(head['position'][:3])

    def require_position(self, gcmd):
        position = self.pose(gcmd)
        if self.position is not None and any(abs(a - b) > .12 for a, b in zip(self.position, position)):
            raise gcmd.error('툴을 가져온 뒤 헤드 위치가 변경됐습니다. 자동 파킹을 시작할 수 없습니다.')

    def ensure_off(self, gcmd, turn_off):
        heaters = self.heaters()
        nozzle, *auxiliary = heaters
        if turn_off:
            nozzle.set_temp(0.)
            if auxiliary:
                self.gcode.run_script_from_command('TOOLHEAD_PARK_OFF')
        deadline = self.reactor.monotonic() + 3.
        while True:
            self.assert_paused(gcmd)
            now = self.reactor.monotonic()
            if not any(h.target_temp or h.last_pwm_value for h in heaters):
                if turn_off:
                    self.reactor.pause(now + nozzle.get_pwm_delay() + .05)
                    self.assert_paused(gcmd)
                    if any(h.target_temp or h.last_pwm_value for h in heaters):
                        raise gcmd.error('히터 출력을 끈 뒤 파킹해 주세요.')
                return
            if not turn_off or now >= deadline:
                raise gcmd.error('노즐과 툴헤드 히터를 끈 뒤 다시 시도해 주세요.')
            self.reactor.pause(now + .05)

    def run_motion(self, gcmd, script):
        self.assert_paused(gcmd)
        self.pose(gcmd)
        mover = self.printer.lookup_object('gcode_move')
        if (abs(mover.position_with_transform()[2] - self.z) > .15
                or abs(mover.get_status(self.reactor.monotonic())['position'][2] - self.z) > .15):
            raise gcmd.error('정비 높이가 변경되어 이동을 중단했습니다.')
        if any(h.target_temp or h.last_pwm_value for h in self.heaters()):
            raise gcmd.error('히터 출력이 켜져 있어 이동을 중단했습니다.')
        self.gcode.run_script_from_command(script + '\nM400')

    def route(self, gcmd, slot):
        now = self.reactor.monotonic()
        dock_name = '_TOOL_RETRY_DOCK_XY_T%d' % (slot + 1)
        park_name = '_TOOL_RETRY_PARK_XY_T%d' % (slot + 1)
        dock = self.printer.lookup_object('gcode_macro ' + dock_name, None)
        park = self.printer.lookup_object('gcode_macro ' + park_name, None)
        route = dock.get_status(now) if dock is not None else {}
        if (park is None or not {'retry_x', 'retry_y', 'retry_exit'} <= route.keys()
                or dock_name not in self.gcode.gcode_handlers or park_name not in self.gcode.gcode_handlers):
            raise gcmd.error('정비용 툴 거치대 매크로를 확인할 수 없습니다.')
        return route

    def return_to_service(self, gcmd, state):
        self.wait_sensor(gcmd, state)
        self.run_motion(gcmd, f'G1 X{SERVICE_X:g} F{SERVICE_TRAVEL_FEED}')
        self.wait_sensor(gcmd, state)
        self.run_motion(gcmd, f'G1 Y{SERVICE_Y:g} F{SERVICE_TRAVEL_FEED}')
        self.wait_sensor(gcmd, state)
        self.position = self.pose(gcmd)

    def fault(self):
        for heater in self.heaters():
            heater.set_temp(0.)
        self.phase = 'fault'
        fast = self.printer.lookup_object('fast_cancel')
        fast.phase = 'dock_sensor_hold'
        fast.critical = True
        fast.message = '정비 중 툴 상태를 확인할 수 없어 일시정지를 유지합니다.'

    def dock(self, gcmd):
        sd = self.assert_paused(gcmd)
        if self.present() and self.phase != 'idle':
            raise gcmd.error('먼저 가져온 툴을 파킹해 주세요.')
        slot = gcmd.get_int('TOOL', minval=0, maxval=3)
        route = self.route(gcmd, slot)
        position = self.pose(gcmd)
        move = self.printer.lookup_object('gcode_move')
        saved = move.saved_states.get('PAUSE_STATE')
        if (abs(position[0] - SERVICE_X) > .25 or not saved
                or move.get_status(self.reactor.monotonic())['position'][2] - saved['last_position'][2] < 3.):
            raise gcmd.error('일반 일시정지 대기 위치와 Z 여유 높이가 확인돼야 툴을 가져올 수 있습니다.')
        self.ensure_off(gcmd, False)
        self.wait_sensor(gcmd, 'disconnected')
        self.session, self.slot = sd.current_file, slot
        self.z = move.get_status(self.reactor.monotonic())['position'][2]
        self.position, self.phase = None, 'docking'
        run = self.gcode.run_script_from_command
        self.restore_switch = False
        try:
            if self.auxiliary_sensor() is None:
                switch = self.printer.lookup_object('filament_switch_sensor toolhead_sensor')
                self.restore_switch = switch.get_status(self.reactor.monotonic())['enabled']
                if self.restore_switch:
                    run('SET_FILAMENT_SENSOR SENSOR=toolhead_sensor ENABLE=0')
            run('SAVE_GCODE_STATE NAME=LUGO_PAUSED_TOOL\nG90')
            self.run_motion(gcmd, f'_TOOL_RETRY_DOCK_XY_T{slot + 1} APPROACH_F={SERVICE_TRAVEL_FEED} SERVICE=1')
            self.wait_sensor(gcmd, 'connected')
            x, y, _ = self.pose(gcmd)
            if abs(x - route['retry_x']) > .12 or abs(y - route['retry_y']) > .12:
                raise gcmd.error('툴 거치대 위치를 확인할 수 없습니다.')
            exit_feed = route.get('service_exit_feed')
            feeds = (exit_feed,) * len(route['retry_exit']) if exit_feed is not None else (700, 700, 1800)
            for x, feed in zip(route['retry_exit'], feeds):
                self.wait_sensor(gcmd, 'connected')
                self.run_motion(gcmd, 'G1 X%g F%d' % (x, feed))
            self.return_to_service(gcmd, 'connected')
            run('RESTORE_GCODE_STATE NAME=LUGO_PAUSED_TOOL MOVE=0')
        except Exception:
            self.fault()
            raise
        self.phase = 'attached'

    def park(self, gcmd):
        self.assert_paused(gcmd)
        if not self.service_attached():
            raise gcmd.error('파킹할 정비용 툴이 없습니다.')
        self.route(gcmd, self.slot)
        self.require_position(gcmd)
        self.wait_sensor(gcmd, 'connected')
        self.phase = 'parking'
        run = self.gcode.run_script_from_command
        try:
            self.ensure_off(gcmd, True)
            run('SAVE_GCODE_STATE NAME=LUGO_PAUSED_TOOL\nG90')
            self.run_motion(gcmd, f'_TOOL_RETRY_PARK_XY_T{self.slot + 1} APPROACH_F={SERVICE_TRAVEL_FEED} SERVICE=1')
            self.return_to_service(gcmd, 'disconnected')
            run('RESTORE_GCODE_STATE NAME=LUGO_PAUSED_TOOL MOVE=0')
            if self.restore_switch:
                run('SET_FILAMENT_SENSOR SENSOR=toolhead_sensor ENABLE=1')
                self.restore_switch = False
        except Exception:
            self.fault()
            raise
        self.phase, self.slot = 'idle', None


def load_config(config):
    return PausedToolService(config)
