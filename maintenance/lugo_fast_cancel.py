"""Cooperative cancellation for the audited LUGOWARE M5P toolchange macros."""
import logging


class MeshCancelled(Exception):
    pass


class FastCancel:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object('gcode')
        self.reactor = self.printer.get_reactor()
        self.requested = False
        self.cleaning = False
        self.critical = False
        self.phase = 'normal'
        self.slot = -1
        self.message = ''
        self.mesh_active = False
        self.printer.lookup_object('webhooks').register_endpoint('lugo_fast_cancel/request', self.request)
        self.gcode.register_command('LUGO_CANCEL_PHASE', self.checkpoint)
        self.gcode.register_command('LUGO_CANCEL_WAIT', self.dwell)
        self.printer.register_event_handler('klippy:ready', self.connect)
        self.printer.register_event_handler('klippy:shutdown', self.shutdown)

    def shutdown(self):
        # Emergency shutdown wins over graceful cancellation. Never schedule
        # recovery travel or leave the command filter blocking a restart.
        self.requested = False
        self.critical = False
        self.phase = 'shutdown'
        self.message = 'Emergency shutdown; graceful cancellation abandoned'

    def connect(self):
        self.sd = self.printer.lookup_object('virtual_sdcard')
        self.heaters = self.printer.lookup_object('heaters')
        self.process = self.gcode._process_commands
        self.gcode._process_commands = self.process_commands
        self.old_wait = self.heaters._wait_for_temperature
        self.heaters._wait_for_temperature = self.wait_heater
        self.wait_command = self.gcode.register_command('TEMPERATURE_WAIT', None)
        self.gcode.register_command('TEMPERATURE_WAIT', self.wait_temperature)
        self.dwell_command = self.gcode.ready_gcode_handlers['G4']
        logging.info('Fast cancel: G4 left unchanged (%s); docking uses LUGO_CANCEL_WAIT', self.dwell_command)
        self.connect_mesh()

    def connect_mesh(self):
        mesh = self.printer.lookup_object('bed_mesh')
        self.mesh_helper = mesh.bmc.probe_mgr.probe_helper
        self.mesh_probe = self.printer.lookup_object('probe').probe_session
        self.mesh_start = self.mesh_helper.start_probe
        self.mesh_sample = self.mesh_probe._probe
        self.mesh_next = self.mesh_helper._move_next
        self.mesh_finalize = self.mesh_helper._invoke_callback
        self.mesh_helper.start_probe = self.start_mesh
        self.mesh_probe._probe = self.probe_sample
        self.mesh_helper._move_next = self.mesh_move_next
        self.mesh_helper._invoke_callback = self.finalize_mesh

    def check_mesh_cancel(self):
        if self.mesh_active and self.stop_wait() and not self.printer.is_shutdown():
            raise MeshCancelled()

    def probe_sample(self, cmd):
        self.check_mesh_cancel()
        result = self.mesh_sample(cmd)
        # The MCU homing/probe move and probe deactivation have finished.
        self.check_mesh_cancel()
        return result

    def mesh_move_next(self, point):
        self.check_mesh_cancel()
        return self.mesh_next(point)

    def finalize_mesh(self, results):
        self.check_mesh_cancel()
        return self.mesh_finalize(results)

    def start_mesh(self, cmd):
        if not self.printing() or self.cleaning or cmd.get('METHOD', 'automatic').lower() == 'manual':
            return self.mesh_start(cmd)
        self.mesh_active = True
        try:
            self.check_mesh_cancel()
            return self.mesh_start(cmd)
        except MeshCancelled:
            # Keep probe cleanup scripts enabled until the session is closed.
            try:
                if self.mesh_probe.hw_probe_session is not None and not self.printer.is_shutdown():
                    self.mesh_helper._raise_tool()
                    self.printer.lookup_object('toolhead').wait_moves()
            finally:
                if self.mesh_probe.hw_probe_session is not None:
                    self.mesh_probe.end_probe_session()
            logging.info('Fast cancel: bed mesh stopped; partial results discarded')
        finally:
            self.mesh_active = False

    def printing(self):
        return self.printer.lookup_object('print_stats').get_status(self.reactor.monotonic())['state'] in ('printing', 'paused')

    def checkpoint(self, cmd):
        phase = cmd.get('PHASE')
        slot = cmd.get_int('TOOL', -1, minval=-1, maxval=3)
        if phase not in ('normal', 'docking', 'docked', 'parking', 'empty'):
            raise cmd.error('Unknown cancellation phase')
        if phase in ('docked', 'empty'):
            self.printer.lookup_object('toolhead').wait_moves()
        self.phase, self.slot = phase, slot
        self.critical = phase in ('docking', 'parking')

    def process_commands(self, commands, need_ack=True):
        def filtered():
            for line in commands:
                command = line.split(';', 1)[0].strip().upper().split()
                recovery = command and command[0] in ('M112', 'RESTART', 'FIRMWARE_RESTART')
                if (self.requested and not self.cleaning and not self.critical
                        and not getattr(self, 'mesh_active', False)
                        and not recovery and not self.printer.is_shutdown()):
                    break
                yield line
        return self.process(filtered(), need_ack)

    def stop_wait(self):
        return self.requested and not self.cleaning

    def dwell(self, cmd):
        if not self.printing() or self.cleaning:
            return self.dwell_command(cmd)
        duration = cmd.get_float('P', 0., minval=0.) / 1000.
        toolhead = self.printer.lookup_object('toolhead')
        if self.stop_wait() or self.printer.is_shutdown():
            return
        toolhead.wait_moves()
        deadline = self.reactor.monotonic() + duration
        now = self.reactor.monotonic()
        while now < deadline and not self.stop_wait() and not self.printer.is_shutdown():
            now = self.reactor.pause(min(now + 0.1, deadline))

    def wait_heater(self, heater):
        if self.printer.get_start_args().get('debugoutput') is not None:
            return
        when = self.reactor.monotonic()
        while not self.printer.is_shutdown() and heater.check_busy(when):
            if self.stop_wait():
                return
            self.printer.lookup_object('toolhead').get_last_move_time()
            when = self.reactor.pause(when + 0.1)

    def wait_temperature(self, cmd):
        if not self.printing() or self.cleaning:
            return self.wait_command(cmd)
        if self.printer.get_start_args().get('debugoutput') is not None:
            return
        name = cmd.get('SENSOR')
        low = cmd.get_float('MINIMUM', float('-inf'))
        high = cmd.get_float('MAXIMUM', float('inf'), above=low)
        if low == float('-inf') and high == float('inf'):
            raise cmd.error('TEMPERATURE_WAIT requires MINIMUM or MAXIMUM')
        sensor = self.heaters.heaters.get(name) or self.printer.lookup_object(name)
        temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
        when = self.reactor.monotonic()
        while not self.printer.is_shutdown() and not self.stop_wait():
            shift = 0
            if name == 'heater_bed' and temperatures:
                shift = temperatures.wait_shift(name)
            if name == 'extruder' and temperatures and temperatures.start_tool is not None and not temperatures.changing:
                tool = temperatures.start_tool
                base, override = temperatures.base[tool], temperatures.overrides[tool]
                if base is not None and override is not None:
                    shift = override - base
            value, target = sensor.get_temp(when)
            if low + shift <= value <= high + shift:
                return
            self.printer.lookup_object('toolhead').get_last_move_time()
            when = self.reactor.pause(when + 0.1)

    def request(self, request):
        if self.printer.is_shutdown():
            raise request.error('Printer is shutdown')
        if self.requested:
            request.send({'accepted': True, 'phase': self.phase})
            return
        if not self.printing():
            raise request.error('No active print to cancel')
        self.requested = True
        self.message = 'Cancelling at the next mechanical safe point'
        self.sd.must_pause_work = True
        self.reactor.register_callback(self.finish)
        request.send({'accepted': True, 'phase': self.phase})

    def finish(self, eventtime):
        # Wait for the executing macro stack to unwind before recovery moves.
        with self.gcode.get_mutex():
            if not self.requested or self.printer.is_shutdown():
                return
            while self.sd.work_timer is not None:
                if not self.requested or self.printer.is_shutdown():
                    return
                self.reactor.pause(self.reactor.monotonic() + .01)
            self.cleaning = True
            try:
                if self.printer.is_shutdown():
                    return
                toolhead = self.printer.lookup_object('toolhead')
                toolhead.wait_moves()
                status = toolhead.get_status(self.reactor.monotonic())
                mounted = self.printer.lookup_object('filament_switch_sensor toolhead_sensor').get_status(self.reactor.monotonic())['filament_detected']
                state = self.printer.lookup_object('gcode_macro TOOL_STATE').get_status(self.reactor.monotonic())
                tool = self.slot if self.phase == 'docked' else int(state['active_tool'])
                if self.critical or (mounted and (self.phase == 'empty' or tool not in range(4))):
                    raise self.gcode.error('Tool attachment is uncertain; automatic parking skipped. Inspect the head.')
                if mounted:
                    if set('xyz') - set(status['homed_axes']):
                        raise self.gcode.error('Axes are not homed; automatic parking skipped.')
                    lift = max(0., min(5., status['axis_maximum'][2] - toolhead.get_position()[2]))
                    self.gcode.run_script_from_command(
                        'G91\nG1 Z%.4f F600\nG90\nM83\nM220 S100\nM221 S100\nPARK_TOOL_%d NEXT_TEMP=0\nM400' % (lift, tool))
                    mounted = self.printer.lookup_object('filament_switch_sensor toolhead_sensor').get_status(self.reactor.monotonic())['filament_detected']
                    if mounted:
                        raise self.gcode.error('Tool still detected after parking; inspect the head.')
                self.gcode.run_script_from_command('SET_GCODE_VARIABLE MACRO=TOOL_STATE VARIABLE=active_tool VALUE=-1')
                self.message = 'Print cancelled'
            except Exception as exc:
                logging.exception('Fast cancel parking failed')
                self.message = str(exc)
                self.gcode.respond_info('Cancellation: ' + self.message)
            finally:
                self.heaters.turn_off_all_heaters()
                temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
                if temperatures:
                    temperatures.reset()
                # No extra XY travel, automatic SAVE_CONFIG, or motor release.
                try:
                    self.printer.lookup_object('pause_resume').cmd_CANCEL_PRINT(
                        self.gcode.create_gcode_command('CANCEL_PRINT', '', {}))
                    self.sd.do_cancel()
                finally:
                    self.requested = self.cleaning = self.critical = False
                    self.phase, self.slot = 'normal', -1

    def get_status(self, eventtime):
        return {'requested': self.requested, 'phase': self.phase, 'tool': self.slot, 'message': self.message}


def load_config(config):
    return FastCancel(config)
