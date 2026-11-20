# Detachable thermistor with guarded heater adapter.
from math import isfinite

from . import thermistor
from .detachable_heater_sensor import DetachableHeaterSensor


class ToolheadAuxiliary:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.heater_adapter = None
        self.sync_manual_preheat = config.getboolean('sync_manual_preheat', True)
        self.prime_temperature_margin = config.getfloat(
            'prime_temperature_margin', 15., minval=0., maxval=20.)
        self.prime_timeout = config.getfloat('prime_timeout', 60., above=0., maxval=180.)
        self.park_nozzle_preheat_offset = config.getfloat(
            'park_nozzle_preheat_offset', 5., minval=0., maxval=40.)
        if not all(map(isfinite, (self.prime_temperature_margin, self.prime_timeout,
                                 self.park_nozzle_preheat_offset))):
            raise config.error('Toolhead tuning values must be finite')
        self.printer.load_object(config, 'heaters').add_sensor_factory(
            'DetachableToolhead', lambda cfg: DetachableHeaterSensor(self, cfg))
        self.converter = thermistor.Thermistor(
            config.getfloat('pullup_resistor', 4700., above=0.), 0.)
        self.converter.setup_coefficients_beta(25., 100000., 3950.)
        self.adc = self.printer.lookup_object('pins').setup_pin(
            'adc', config.get('sensor_pin'))
        # Idle open circuit allowed; adapter enforces heater limits and shutdown.
        self.adc.setup_adc_sample(.1, sample_time=.001, sample_count=8)
        self.adc.setup_adc_callback(self._sample)
        self.state = 'unknown'
        self.candidate = None
        self.count = 0
        self.temperature = None
        self.raw = None
        self.last = None
        self.gcode.register_command('QUERY_TOOLHEAD_TEMP', self.query)

    def _sample(self, samples):
        read_time, raw = samples[-1]
        self.last = self.reactor.monotonic()
        self.raw = raw
        temperature = None
        if raw >= .995:
            state = 'disconnected'
        elif raw <= .001:
            state = 'short_circuit'
        else:
            temperature = self.converter.calc_temp(raw)
            state = 'connected' if -20. <= temperature <= 350. else 'invalid'
        if self.heater_adapter is not None:
            self.heater_adapter.sample(read_time, state, temperature)
        # Immediately invalidate a suspect measurement; debounce presence only.
        self.temperature = temperature if state == 'connected' else None
        self.count = self.count + 1 if state == self.candidate else 1
        self.candidate = state
        if self.count >= 3 and state != self.state:
            self.state = state
            self.gcode.respond_info(self._message())

    def get_status(self, eventtime):
        state = self.state
        if self.last is None or eventtime - self.last > 2.:
            state = 'stale'
        elif self.candidate != self.state:
            state = 'checking'
        return {'state': state, 'sensor_connected': state == 'connected',
                'temperature': self.temperature if state == 'connected' else None,
                'adc': self.raw, 'diagnostic_only': self.heater_adapter is None,
                'park_nozzle_preheat_offset': self.park_nozzle_preheat_offset}

    def _message(self):
        status = self.get_status(self.reactor.monotonic())
        if status['state'] == 'connected':
            return '툴헤드 온도센서 연결: %.1f°C (센서 연결 감지)' % status['temperature']
        return {'disconnected': '툴헤드 미부착 / 온도센서 연결 끊김',
                'short_circuit': '툴헤드 온도센서 단락 의심',
                'invalid': '툴헤드 온도센서 측정 범위 이상',
                'checking': '툴헤드 온도센서 상태 확인 중',
                'stale': '툴헤드 온도센서 응답 대기'}.get(status['state'], '센서 확인 중')

    def query(self, gcmd):
        gcmd.respond_info(self._message())


def load_config(config):
    return ToolheadAuxiliary(config)
