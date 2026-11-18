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
        source.gcode.register_command("TOOLHEAD_DOCK_HEAT", self.dock_heat)
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
        original_alter_target = heater.alter_target
        original_status = heater.get_status
        def guarded_set_temp(degrees):
            if not degrees:
                self.dock_pending = False
            if degrees:
                status = self.source.get_status(self.source.reactor.monotonic())
                if self.failed or status['state'] != 'connected' or self.valid_samples < 9:
                    raise self.printer.command_error('Toolhead sensor is not connected; heating blocked')
            original_set_temp(degrees)
        def guarded_alter_target(degrees):
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
            return result
        heater.set_temp = guarded_set_temp
        heater.alter_target = guarded_alter_target
        heater.get_status = status

    def dock_heat(self, gcmd):
        target = gcmd.get_float('TEMP', minval=0., maxval=self.maximum)
        if self.failed:
            raise self.printer.command_error('Toolhead heater safety stop is active')
        self.dock_target = target
        self.dock_deadline = self.source.reactor.monotonic() + 5.
        self.dock_pending = bool(target)

    def park_off(self, gcmd):
        self.dock_pending = False
        self.heater.set_temp(0.)
        # Preserve the normal fault guard until queued PWM is physically off.
        reactor = self.source.reactor
        mcu = self.heater.mcu_pwm.get_mcu()
        now = reactor.monotonic()
        print_time = mcu.estimated_print_time(now)
        self.heater.set_pwm(print_time, 0.)
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
        if state != 'connected' or temperature is None or temperature < self.minimum:
            self.valid_samples = 0
            if protected:
                self.fault('Sensor %s, temperature %s during heating/cooldown guard' % (state, temperature))
            # Idle detachment/contact transitions must not feed the heater PID.
            return
        self.valid_samples = min(9, self.valid_samples + 1)
        self.callback(read_time, temperature)

    def ready(self):
        self.start_time = self.source.reactor.monotonic()
        self.source.reactor.register_timer(self.watchdog, self.source.reactor.NOW)

    def watchdog(self, eventtime):
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
