# Adapter for the existing PA2 input. Uses Klipper's normal Heater and verifier.
class DetachableHeaterSensor:
    def __init__(self, source, config):
        self.source = source
        self.printer = source.printer
        self.heater = None
        self.callback = None
        self.failed = False
        self.start_time = None
        self.valid_samples = 0
        self.last_active = None
        self.dock_pending = False
        self.reconnect = None
        self.manual_targets = None
        self.manual_parked = False
        source.gcode.register_command("TOOLHEAD_DOCK_HEAT", self.dock_heat)
        source.gcode.register_command("TOOLHEAD_CHECK_DOCK_READY", self.check_dock_before_heat)
        source.gcode.register_command("TOOLHEAD_WAIT_FOR_PRIME", self.wait_for_prime,
                                           desc="Wait for auxiliary toolhead temperature before prime")
        source.gcode.register_command("TOOLHEAD_PARK_OFF", self.park_off)
        self.minimum = 0.
        self.maximum = 60.
        source.heater_adapter = self
        self.printer.register_event_handler('klippy:ready', self.ready)

    def setup_minmax(self, minimum, maximum):
        self.minimum, self.maximum = minimum, maximum

    def get_report_time_delta(self):
        return .1

    def setup_callback(self, callback):
        self.callback = callback
        self.heater = heater = callback.__self__
        original_set_temp = heater.set_temp
        self.original_set_temp = original_set_temp
        original_alter_target = heater.alter_target
        original_status = heater.get_status
        def guarded_set_temp(degrees):
            self.reconnect = None
            if not degrees:
                self.dock_pending = False
            if degrees:
                status = self.source.get_status(self.source.reactor.monotonic())
                if self.failed or status['state'] != 'connected' or self.valid_samples < 9:
                    raise self.printer.command_error('Toolhead sensor is not connected; heating blocked')
            original_set_temp(degrees)
        def guarded_alter_target(degrees):
            self.reconnect = None
            if degrees and (self.failed or self.valid_samples < 9 or self.source.get_status(
                    self.source.reactor.monotonic())['state'] != 'connected'):
                self.fault('Sensor unavailable during heater control')
                return
            original_alter_target(degrees)
        def status(eventtime):
            result = original_status(eventtime)
            sensor = self.source.get_status(eventtime)
            if sensor['state'] != 'connected':
                result['temperature'] = None
            result['sensor_state'] = sensor['state']
            result['reconnect_pending'] = self.reconnect is not None
            return result
        heater.set_temp = guarded_set_temp
        heater.alter_target = guarded_alter_target
        heater.get_status = status

    def check_dock_before_heat(self, gcmd):
        fast = self.printer.lookup_object('fast_cancel')
        if fast.phase != 'docking' or fast.slot not in range(4):
            raise gcmd.error('Dock sensor check requires an active dock slot')
        if self.heater.target_temp or self.heater.last_pwm_value:
            self.fault('Auxiliary heater still active during preheat dock check')
            raise gcmd.error('Unsafe heater state before dock check')
        reactor = self.source.reactor
        for attempt in range(3):
            if self.failed or self.printer.is_shutdown():
                raise gcmd.error('Toolhead safety stop during dock check')
            if fast.stop_wait():
                fast.dock_abort = True
                return
            status = self.source.get_status(reactor.monotonic())
            temp = status['temperature']
            if status['state'] == 'connected' and temp is not None and self.minimum <= temp <= self.maximum and self.valid_samples >= 9:
                return
            if not attempt:
                self.printer.lookup_object('extruder').get_heater().set_temp(0.)
            if attempt == 2:
                break
            if fast.slot in range(4) and status['state'] == 'connected' and temp is not None and temp < self.minimum:
                if not self.retry_at_dock(fast, status):
                    break
            else:
                reactor.pause(reactor.monotonic() + 1.)
        if fast.stop_wait():
            fast.dock_abort = True
            return
        fast.dock_recovery.begin_hold(fast.slot)
        fast.phase = 'dock_sensor_hold'
        fast.critical = True
        fast.message = 'Toolhead sensor check failed; paused without movement'
        try:
            self.printer.lookup_object('pause_resume').cmd_PAUSE(gcmd)
        finally:
            # Let BASE_PAUSE save its position before stopping the dock macro.
            fast.dock_abort = True
        self.source.gcode.respond_info(fast.message + '; inspect the tool and cancel before moving')

    def retry_at_dock(self, fast, status):
        temperature = status['temperature']
        slot = fast.slot
        if (slot not in range(4) or status['state'] != 'connected' or temperature is None
                or temperature >= self.minimum):
            return False
        reactor = self.source.reactor
        now = reactor.monotonic()
        head = self.printer.lookup_object('toolhead').get_status(now)
        move = self.printer.lookup_object('gcode_move').get_status(now)
        stats = self.printer.lookup_object('print_stats').get_status(now)
        xyz = move['gcode_position']
        dock = self.printer.lookup_object('gcode_macro _T%d_RETRY_DOCK_XY' % (slot + 1),
                                          None)
        if dock is None:
            return False
        path = dock.get_status(now)
        if (stats['state'] != 'printing' or set(head['homed_axes']) != set('xyz')
                or not move['absolute_coordinates'] or abs(xyz[0] - path['retry_x']) > .1
                or abs(xyz[1] - path['retry_y']) > .1
                or any(abs(float(head['position'][i]) - xyz[i]) > .1 for i in (0, 1))):
            return False
        nozzle = self.printer.lookup_object('extruder').get_heater()

        def safe_to_move_with_sensor(expected):
            return (not fast.stop_wait() and not self.failed and not self.printer.is_shutdown()
                    and not nozzle.target_temp and not self.heater.target_temp
                    and not self.heater.last_pwm_value
                    and self.source.get_status(reactor.monotonic())['state'] == expected)

        if not safe_to_move_with_sensor('connected'):
            return False
        gcode = self.source.gcode
        gcode.run_script_from_command(
            'G1 X%.1f F700\nG1 X%.1f F700\nG1 X%.1f F1800\nM400' % path['retry_exit'])
        if not safe_to_move_with_sensor('connected'):
            return False
        gcode.run_script_from_command('_T%d_RETRY_PARK_XY' % (slot + 1))
        reactor.pause(reactor.monotonic() + 1.)
        if not safe_to_move_with_sensor('disconnected'):
            return False
        gcode.run_script_from_command('_T%d_RETRY_DOCK_XY' % (slot + 1))
        reactor.pause(reactor.monotonic() + 1.)
        return True

    def dock_heat(self, gcmd):
        self.reconnect = None
        target = gcmd.get_float('TEMP', minval=0., maxval=self.maximum)
        if self.failed:
            raise self.printer.command_error('Toolhead heater safety stop is active')
        self.dock_target = target
        self.dock_deadline = self.source.reactor.monotonic() + 5.
        self.dock_pending = bool(target)

    def wait_for_prime(self, gcmd):
        target = gcmd.get_float('TARGET', above=30., maxval=self.maximum)
        threshold = target - self.source.prime_temperature_margin
        reactor = self.source.reactor
        fast_cancel = self.printer.lookup_object('fast_cancel', None)
        now = reactor.monotonic()
        deadline = now + self.source.prime_timeout
        connected = False
        while True:
            if self.failed or self.printer.is_shutdown():
                raise gcmd.error('Toolhead heater safety stop before prime')
            if fast_cancel and fast_cancel.stop_wait():
                # FAST_CANCEL_PRIME will skip extrusion and run the safe dock exit.
                return
            sensor = self.source.get_status(now)
            state = sensor['state']
            if (state in ('short_circuit', 'invalid', 'stale')
                    or (connected and state == 'disconnected')):
                self.heater.set_temp(0.)
                raise gcmd.error('Toolhead sensor unavailable before prime: ' + state)
            if state == 'connected' and self.valid_samples >= 9:
                connected = True
                if self.heater.target_temp == target and sensor['temperature'] >= threshold:
                    return
            if not self.dock_pending and self.heater.target_temp != target:
                self.heater.set_temp(0.)
                raise gcmd.error('Toolhead heating target changed before prime')
            if now >= deadline:
                self.heater.set_temp(0.)
                raise gcmd.error('Toolhead did not reach %.1f C before prime' % threshold)
            now = reactor.pause(min(now + .1, deadline))

    def park_off(self, gcmd):
        self.manual_parked = True
        self.dock_pending = False
        self.heater.set_temp(0.)
        # Preserve the normal fault guard until queued PWM is physically off.
        reactor = self.source.reactor
        mcu = self.heater.mcu_pwm.get_mcu()
        now = reactor.monotonic()
        print_time = mcu.estimated_print_time(now)
        # Park requires a real zero command even below the PID update deadband.
        with self.heater.lock:
            deadband = self.heater.min_pwm_change
            try:
                self.heater.min_pwm_change = 0.
                self.heater.set_pwm(print_time, 0.)
            finally:
                self.heater.min_pwm_change = deadband
        off_time = print_time + self.heater.get_pwm_delay() + .05
        while mcu.estimated_print_time(reactor.monotonic()) < off_time:
            reactor.pause(reactor.monotonic() + .025)
        if self.failed or self.printer.is_shutdown():
            raise self.printer.command_error('Toolhead heater safety stop during parking')
        if self.heater.target_temp or self.heater.last_pwm_value:
            raise self.printer.command_error('Toolhead heater is not off; parking blocked')
        # This explicit normal-parking command is the only early guard release.
        self.last_active = None

    def fault(self, reason):
        if self.failed:
            return
        self.failed = True
        if self.heater is not None:
            self.heater.set_temp(0.)
        # MCU shutdown cancels queued PWM as well as the current output.
        self.printer.invoke_shutdown('Toolhead heater safety stop: ' + reason)

    def context(self, now):
        tool = self.printer.lookup_object('gcode_macro TOOL_STATE', None)
        stats = self.printer.lookup_object('print_stats', None)
        cancel = self.printer.lookup_object('fast_cancel', None)
        tool_id = tool.get_status(now).get('active_tool', -1) if tool else -1
        state = stats.get_status(now) if stats else {}
        blocked = (self.printer.is_shutdown() or
                   bool(cancel and (cancel.requested or cancel.cleaning)))
        return tool_id, state.get('state', 'standby'), state.get('filename', ''), blocked

    def detached(self, now):
        # Called on the FIRST raw open-circuit sample, before presence debounce.
        target = self.heater.target_temp
        tool, state, filename, blocked = self.context(now)
        if target > 0 and self.reconnect is None and not blocked and tool in (0, 1, 2, 3):
            self.reconnect = (now + 5., target, tool, state, filename)
        self.dock_pending = False
        self.original_set_temp(0.)
        # Schedule zero through the existing MCU heater API, not from stale ADC time.
        print_time = self.heater.mcu_pwm.get_mcu().estimated_print_time(now)
        self.heater.set_pwm(print_time, 0.)
        if target > 0:
            self.source.gcode.respond_info('Toolhead detached: auxiliary heater off; reconnect window 5 seconds')
            if state == 'printing':
                self.source.reactor.register_callback(self.pause_detached_print)

    def pause_detached_print(self, eventtime):
        _, state, _, blocked = self.context(eventtime)
        if state == 'printing' and not blocked:
            pause = self.printer.lookup_object('pause_resume')
            if not pause.is_paused:
                self.source.gcode.run_script('PAUSE')

    def check_reconnect(self, now):
        if self.reconnect is None:
            return
        deadline, target, tool, previous_state, filename = self.reconnect
        current_tool, state, current_filename, blocked = self.context(now)
        allowed_states = ('printing', 'paused') if previous_state == 'printing' else (previous_state,)
        if (now >= deadline or blocked or current_tool != tool or state not in allowed_states
                or current_filename != filename):
            self.reconnect = None
            return
        if self.valid_samples >= 9 and self.source.get_status(now)['state'] == 'connected':
            self.reconnect = None
            self.heater.set_temp(target)
            self.source.gcode.respond_info('Toolhead reconnected: auxiliary preheat restored; print is not automatically resumed')

    def sample(self, read_time, state, temperature):
        if self.heater is None or self.failed:
            return
        now = self.source.reactor.monotonic()
        active = self.heater.target_temp > 0 or self.heater.last_pwm_value > 0
        if active:
            self.last_active = now
        protected = active or (self.last_active is not None and now - self.last_active < 5.)
        # Never suppress a high-temperature reading, even with the heater off.
        if temperature is not None and temperature > self.maximum:
            self.valid_samples = 0
            self.fault('Temperature %.3f above maximum %.3f' % (temperature, self.maximum))
            return
        if state == 'disconnected':
            self.valid_samples = 0
            self.detached(now)
            return
        if state != 'connected' or temperature is None or temperature < self.minimum:
            self.valid_samples = 0
            self.reconnect = None
            if protected:
                self.fault('Sensor %s, temperature %s during heating/cooldown guard' % (state, temperature))
            # Idle detachment/contact transitions must not feed the heater PID.
            return
        self.valid_samples = min(9, self.valid_samples + 1)
        self.callback(read_time, temperature)

    def ready(self):
        self.nozzle_heater = self.printer.lookup_object('extruder').get_heater()
        self.manual_controls = (self.nozzle_heater.control, self.heater.control)
        self.start_time = self.source.reactor.monotonic()
        self.source.reactor.register_timer(self.watchdog, self.source.reactor.NOW)

    def sync_print_target(self, now):
        nozzle = self.printer.lookup_object('extruder', None)
        if nozzle is None:
            return
        target = nozzle.get_heater().target_temp
        tool, state, _, blocked = self.context(now)
        tools = self.printer.lookup_object('gcode_macro TOOL_STATE', None)
        temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
        tool_status = tools.get_status(now) if tools else {}
        changing = bool(tool_status.get('changing', 0))
        changing = changing or bool(temperatures and (
            temperatures.depth or temperatures.changing or temperatures.start_tool is not None))
        if (target == self.heater.target_temp or blocked or changing
                or tool_status.get('is_parked', 0)
                or state != 'printing' or tool not in (0, 1, 2, 3)
                or self.dock_pending or self.reconnect is not None
                or self.heater.target_temp <= 0 or self.valid_samples < 9
                or self.source.get_status(now)['state'] != 'connected'):
            return
        # Never raise an auxiliary limit or re-enable a manually disabled heater.
        if target > self.maximum:
            self.heater.set_temp(0.)
            self.source.gcode.respond_info('Auxiliary heater off: nozzle target exceeds toolhead maximum')
            return
        self.heater.set_temp(target)

    def sync_manual_targets(self, now):
        nozzle, aux = self.nozzle_heater, self.heater
        observed = (nozzle.target_temp, aux.target_temp)
        sensor_state = self.source.get_status(now)['state']
        connected = sensor_state == 'connected' and self.valid_samples >= 9
        _, state, _, blocked = self.context(now)
        tools = self.printer.lookup_object('gcode_macro TOOL_STATE', None)
        temperatures = self.printer.lookup_object('lugo_tool_temperature', None)
        diagnostics = self.printer.lookup_object('lugo_diagnostics', None)
        if sensor_state == 'disconnected':
            self.manual_parked = False
        previous = self.manual_targets
        self.manual_targets = (*observed, connected)
        if (blocked or self.manual_parked or self.dock_pending or self.reconnect is not None
                or state not in ('standby', 'complete', 'cancelled')
                or (tools and tools.get_status(now).get('changing', 0))
                or (temperatures and (temperatures.depth or temperatures.start_tool is not None))
                or (diagnostics and diagnostics.active)
                or (nozzle.control, aux.control) != self.manual_controls):
            return
        if previous is None or not connected:
            return
        n, a = observed
        previous_n, previous_a, was_connected = previous
        if was_connected and a != previous_a and n == previous_n:
            target = a
        elif n != previous_n or not was_connected or a != previous_a:
            target = n
        else:
            return
        if target and not max(nozzle.min_temp, self.minimum) <= target <= min(nozzle.max_temp, self.maximum):
            if a:
                aux.set_temp(0.)
            if n and n != target:
                nozzle.set_temp(0.)
            self.source.gcode.respond_info('Heaters not linked: target outside shared temperature range')
        else:
            if n != target:
                nozzle.set_temp(target)
            if a != target:
                aux.set_temp(target)
        self.manual_targets = (nozzle.target_temp, aux.target_temp, True)

    def watchdog(self, eventtime):
        if not self.failed:
            self.check_reconnect(eventtime)
            self.sync_print_target(eventtime)
            if self.source.sync_manual_preheat:
                self.sync_manual_targets(eventtime)
        if self.dock_pending and not self.failed:
            if (self.valid_samples >= 9 and
                    self.source.get_status(eventtime)['state'] == 'connected'):
                self.dock_pending = False
                self.heater.set_temp(self.dock_target)
            elif eventtime >= self.dock_deadline:
                self.dock_pending = False
                self.fault('Toolhead sensor not ready after docking')
        if (self.source.get_status(eventtime)['state'] == 'stale'
                and (self.source.last is not None or self.start_time is None
                     or eventtime - self.start_time > 3.)):
            self.fault('No recent temperature samples')
        return eventtime + .1
