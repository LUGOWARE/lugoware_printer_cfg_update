# Virtual pin that propagates its changes to multiple output pins
# Copyright (C) 2017-2021 Kevin O'Connor <kevin@koconnor.net>
# This file may be distributed under the terms of the GNU GPLv3 license.
# LUGOWARE: selectable dual-heater output.

class PrinterMultiPin:
    def __init__(self, config):
        self.printer = config.get_printer()
        ppins = self.printer.lookup_object('pins')
        try:
            ppins.register_chip('multi_pin', self)
        except ppins.error:
            pass
        self.pin_type = None
        self.pin_list = config.getlist('pins')
        self.mcu_pins = []
        self.test_mode = 0
        self.last_print_time = 0.
        self.printer.lookup_object('gcode').register_mux_command(
            'SET_MULTI_PIN_MODE', 'PIN', config.get_name().split()[-1],
            self.cmd_SET_MULTI_PIN_MODE,
            desc='Select dual heater output; turn off heaters before switching')

    def setup_pin(self, pin_type, pin_params):
        ppins = self.printer.lookup_object('pins')
        pin_name = pin_params['pin']
        pin = self.printer.lookup_object('multi_pin ' + pin_name, None)
        if pin is not self:
            if pin is None:
                raise ppins.error('multi_pin %s not configured' % pin_name)
            return pin.setup_pin(pin_type, pin_params)
        if self.pin_type is not None:
            raise ppins.error("Can't setup multi_pin %s twice" % pin_name)
        self.pin_type = pin_type
        invert = '!' if pin_params['invert'] else ''
        self.mcu_pins = [ppins.setup_pin(pin_type, invert + desc)
                         for desc in self.pin_list]
        return self

    def get_mcu(self):
        return self.mcu_pins[0].get_mcu()

    def setup_max_duration(self, max_duration):
        for pin in self.mcu_pins:
            pin.setup_max_duration(max_duration)

    def setup_start_value(self, start_value, shutdown_value):
        for pin in self.mcu_pins:
            pin.setup_start_value(start_value, shutdown_value)

    def setup_cycle_time(self, cycle_time, hardware_pwm=False):
        for pin in self.mcu_pins:
            pin.setup_cycle_time(cycle_time, hardware_pwm)

    def _write(self, method, print_time, value):
        self.last_print_time = max(self.last_print_time, print_time)
        for index, pin in enumerate(self.mcu_pins):
            enabled = self.test_mode == 0 or index == self.test_mode - 1
            getattr(pin, method)(print_time, value if enabled else 0.)

    def set_digital(self, print_time, value):
        self._write('set_digital', print_time, value)

    def next_aligned_print_time(self, print_time, allow_early=0.):
        return print_time

    def set_pwm(self, print_time, value):
        self._write('set_pwm', print_time, value)

    def cmd_SET_MULTI_PIN_MODE(self, gcmd):
        mode = gcmd.get_int('MODE', 0, minval=0, maxval=2)
        if len(self.mcu_pins) != 2 or self.pin_type not in ('pwm', 'digital_out'):
            raise gcmd.error('Heater test mode requires exactly 2 output pins')
        heaters = self.printer.lookup_object('heaters')
        eventtime = self.printer.get_reactor().monotonic()
        for name in heaters.get_all_heaters():
            if heaters.lookup_heater(name).get_temp(eventtime)[1] > 0:
                raise gcmd.error('Run TURN_OFF_HEATERS before changing mode')
        print_time = max(
            self.printer.lookup_object('toolhead').get_last_move_time(),
            self.last_print_time + 0.001)
        method = 'set_pwm' if self.pin_type == 'pwm' else 'set_digital'
        # Drain previous scheduled output before accepting a new selection.
        self._write(method, print_time, 0.)
        self.test_mode = mode
        label = 'NORMAL' if mode == 0 else 'HEATER %d ONLY' % mode
        gcmd.respond_info('Dual heater mode: %s (pins: %s)' % (
            label, ', '.join(self.pin_list)))


def load_config_prefix(config):
    return PrinterMultiPin(config)
