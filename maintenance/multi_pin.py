# Virtual pin that propagates its changes to multiple output pins
# Copyright (C) 2017-2021 Kevin O'Connor <kevin@koconnor.net>
# This file may be distributed under the terms of the GNU GPLv3 license.

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

        # 0 = normal
        # 1 = heater 1 only
        # 2 = heater 2 only
        self.test_mode = 0

        # G-code command registration
        gcode = self.printer.lookup_object('gcode')
        gcode.register_mux_command(
            'SET_MULTI_PIN_MODE',
            'PIN',
            config.get_name().split()[-1],
            self.cmd_SET_MULTI_PIN_MODE,
            desc='Select multi-pin output mode'
        )

    def setup_pin(self, pin_type, pin_params):
        ppins = self.printer.lookup_object('pins')
        pin_name = pin_params['pin']

        pin = self.printer.lookup_object(
            'multi_pin ' + pin_name, None)

        if pin is not self:
            if pin is None:
                raise ppins.error(
                    "multi_pin %s not configured" % (pin_name,))
            return pin.setup_pin(pin_type, pin_params)

        if self.pin_type is not None:
            raise ppins.error(
                "Can't setup multi_pin %s twice" % (pin_name,))

        self.pin_type = pin_type

        invert = ""
        if pin_params['invert']:
            invert = "!"

        self.mcu_pins = [
            ppins.setup_pin(pin_type, invert + pin_desc)
            for pin_desc in self.pin_list
        ]

        return self

    def get_mcu(self):
        return self.mcu_pins[0].get_mcu()

    def setup_max_duration(self, max_duration):
        for mcu_pin in self.mcu_pins:
            mcu_pin.setup_max_duration(max_duration)

    def setup_start_value(self, start_value, shutdown_value):
        for mcu_pin in self.mcu_pins:
            mcu_pin.setup_start_value(
                start_value, shutdown_value)

    def setup_cycle_time(self, cycle_time, hardware_pwm=False):
        for mcu_pin in self.mcu_pins:
            mcu_pin.setup_cycle_time(
                cycle_time, hardware_pwm)

    def set_digital(self, print_time, value):
        if self.test_mode == 0:
            for mcu_pin in self.mcu_pins:
                mcu_pin.set_digital(print_time, value)

        elif self.test_mode == 1:
            self.mcu_pins[0].set_digital(print_time, value)
            self.mcu_pins[1].set_digital(print_time, 0)

        elif self.test_mode == 2:
            self.mcu_pins[0].set_digital(print_time, 0)
            self.mcu_pins[1].set_digital(print_time, value)

    def next_aligned_print_time(self, print_time, allow_early=0.):
        return print_time

    def set_pwm(self, print_time, value):
        if self.test_mode == 0:
            # NORMAL
            # PC5 + PA7
            for mcu_pin in self.mcu_pins:
                mcu_pin.set_pwm(print_time, value)

        elif self.test_mode == 1:
            # HEATER 1 ONLY
            # PC5 ON / PA7 OFF
            self.mcu_pins[0].set_pwm(print_time, value)
            self.mcu_pins[1].set_pwm(print_time, 0.)

        elif self.test_mode == 2:
            # HEATER 2 ONLY
            # PC5 OFF / PA7 ON
            self.mcu_pins[0].set_pwm(print_time, 0.)
            self.mcu_pins[1].set_pwm(print_time, value)

    def cmd_SET_MULTI_PIN_MODE(self, gcmd):
        mode = gcmd.get_int('MODE', 0, minval=0, maxval=2)

        if len(self.mcu_pins) != 2:
            raise gcmd.error(
                "Heater test mode requires exactly 2 pins")

        self.test_mode = mode

        if mode == 0:
            gcmd.respond_info(
                "Dual heater mode: NORMAL (PC5 + PA7)")
        elif mode == 1:
            gcmd.respond_info(
                "Dual heater mode: HEATER 1 ONLY (PC5)")
        elif mode == 2:
            gcmd.respond_info(
                "Dual heater mode: HEATER 2 ONLY (PA7)")


def load_config_prefix(config):
    return PrinterMultiPin(config)
