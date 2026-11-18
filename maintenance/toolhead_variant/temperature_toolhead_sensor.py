# Detachable, unheated thermistor presence input; preserves toolhead_sensor API.
from .filament_switch_sensor import RunoutHelper


class TemperatureToolheadSensor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.sensor = self.printer.load_object(config, 'toolhead_temperature_test')
        self.runout_helper = RunoutHelper(config)
        self.printer.add_object('filament_switch_sensor toolhead_sensor', self)
        self.ready_time = None
        self.failed = False
        self.printer.register_event_handler('klippy:ready', self.ready)

    def ready(self):
        self.ready_time = self.reactor.monotonic()
        self.reactor.register_timer(self.poll, self.ready_time)

    def poll(self, eventtime):
        status = self.sensor.get_status(eventtime)
        state = status['state']
        if state in ('connected', 'disconnected'):
            self.runout_helper.note_filament_present(eventtime, state == 'connected')
        elif state in ('short_circuit', 'invalid', 'stale'):
            if self.sensor.heater_adapter is not None and state != 'stale':
                # Heater adapter owns thermal protection; invalid idle input is absent.
                self.runout_helper.note_filament_present(eventtime, False)
            elif eventtime - self.ready_time > 3. and not self.failed:
                self.failed = True
                self.printer.invoke_shutdown(
                    'Toolhead temperature presence sensor fault: ' + state)
        return eventtime + .1

    def get_status(self, eventtime):
        result = self.runout_helper.get_status(eventtime)
        result.update(self.sensor.get_status(eventtime))
        result['source'] = 'PA2 thermistor'
        return result


def load_config_prefix(config):
    if config.get_name() != 'temperature_toolhead_sensor toolhead_sensor':
        raise config.error('This test supports toolhead_sensor only')
    return TemperatureToolheadSensor(config)
