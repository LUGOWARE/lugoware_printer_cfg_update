"""Per-print encoder policy, independent of tool attachment detection."""


class PrintSensor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.enabled = True
        self.pending = None
        self.in_job = False
        self.gate = False
        self.generation = 0
        self.arm_at = None
        self.sensor = None
        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command('PRINT_SENSOR_BEGIN', self.begin)
        self.gcode.register_command('PRINT_SENSOR_END', self.end)
        self.gcode.register_command('PRINT_SENSOR_GATE', self.set_gate)
        self.printer.lookup_object('webhooks').register_endpoint(
            'print_sensor/policy', self.policy)
        self.printer.register_event_handler('klippy:ready', self.ready)

    def ready(self):
        self.sensor = self.printer.lookup_object('filament_motion_sensor encoder_sensor')
        self.helper = self.sensor.runout_helper
        self.original_status = self.sensor.get_status
        self.sensor.get_status = self.sensor_status
        # Guard slicer/native SET_FILAMENT_SENSOR calls as well as our macros.
        handlers = self.gcode.mux_commands['SET_FILAMENT_SENSOR'][1]
        self.original_set = handlers['encoder_sensor']
        handlers['encoder_sensor'] = self.legacy_set
        self.original_runout = self.helper._runout_event_handler
        self.helper._runout_event_handler = self.runout
        self.helper.sensor_enabled = False
        self.reactor.register_timer(self.tick, self.reactor.NOW)

    def legacy_set(self, gcmd):
        # Native Mainsail switch and touch UI share the user's policy.
        value = bool(gcmd.get_int('ENABLE', 1, minval=0, maxval=1))
        self.enabled = value
        if not self.in_job:
            self.pending = value
        self.apply(self.reactor.monotonic())

    def sensor_status(self, eventtime):
        status = dict(self.original_status(eventtime))
        status['enabled'] = self.get_status(eventtime)['enabled']
        status['detection_active'] = bool(self.helper.sensor_enabled)
        return status

    def allowed(self, now):
        stats = self.printer.lookup_object('print_stats').get_status(now)
        paused = self.printer.lookup_object('pause_resume').is_paused
        return (self.in_job and self.enabled and self.gate
                and stats['state'] == 'printing' and not paused)

    def apply(self, now):
        allowed = self.allowed(now)
        if allowed and not self.helper.sensor_enabled:
            # Re-arm from the current E position, not a stale pre-docking value.
            self.sensor._update_filament_runout_pos(now)
            self.helper.filament_present = True
        self.helper.sensor_enabled = bool(allowed)

    def runout(self, eventtime):
        # A callback queued just before OFF/docking must not pause afterwards.
        if not self.allowed(eventtime):
            self.helper.min_event_systime = eventtime + self.helper.event_delay
            return
        self.original_runout(eventtime)

    def tick(self, now):
        if self.arm_at is not None:
            if self.printer.lookup_object('mcu').estimated_print_time(now) >= self.arm_at:
                self.arm_at = None
                self.gate = True
        if self.in_job:
            state = self.printer.lookup_object('print_stats').get_status(now)['state']
            if state in ('complete', 'cancelled', 'error'):
                self.finish()
        self.apply(now)
        return now + .1

    def begin(self, gcmd):
        self.enabled = self.pending if self.pending is not None else True
        self.pending = None
        self.in_job = True
        self.close_gate()

    def close_gate(self):
        self.generation += 1
        self.gate = False
        self.arm_at = None
        if self.sensor is not None:
            self.helper.sensor_enabled = False

    def set_gate(self, gcmd):
        if not gcmd.get_int('ENABLE', 0, minval=0, maxval=1):
            self.close_gate()
            return
        generation = self.generation
        def arm(print_time):
            if generation == self.generation and self.in_job:
                self.arm_at = print_time
        # No M400/dwell: do not pause the toolhead on exit from docking.
        self.printer.lookup_object('toolhead').register_lookahead_callback(arm)

    def finish(self):
        self.close_gate()
        self.in_job = False
        self.enabled = True

    def end(self, gcmd):
        self.finish()

    def policy(self, request):
        value = request.get_int('enabled')
        scope = request.get_str('scope', 'current')
        if value not in (0, 1) or scope not in ('next', 'current'):
            raise request.error('Invalid filament sensor policy')
        now = self.reactor.monotonic()
        state = self.printer.lookup_object('print_stats').get_status(now)['state']
        if scope == 'next':
            if state in ('printing', 'paused'):
                raise request.error('A print is already active')
            self.pending = bool(value)
        else:
            if not self.in_job or state not in ('printing', 'paused'):
                raise request.error('No active print')
            self.enabled = bool(value)
            self.apply(now)
        request.send(self.get_status(now))

    def get_status(self, eventtime):
        active = bool(self.sensor and self.helper.sensor_enabled)
        enabled = self.pending if not self.in_job and self.pending is not None else self.enabled
        return {'enabled': enabled, 'active': active, 'in_job': self.in_job,
                'state': 'off' if not enabled else ('on' if active else 'waiting')}


def load_config(config):
    return PrintSensor(config)
