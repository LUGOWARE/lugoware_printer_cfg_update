import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'maintenance' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


multi = load('multi_pin')
idle = load('check_idle')
firmware = load('verify_firmware')


class MaintenanceTests(unittest.TestCase):
    def test_supplied_firmware_is_m5p_usb(self):
        import hashlib
        folder = ROOT / 'firmware'
        data = (folder / 'firmware.bin').read_bytes()
        self.assertEqual(firmware.inspect(data)['config']['MCU'], 'stm32g0b1xx')
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         (folder / 'firmware.sha256').read_text().split()[0])

    def test_invalid_firmware_rejected(self):
        for data in (b'', b'<html>' * 1000, b'\x00' * 40000):
            with self.assertRaises(ValueError):
                firmware.inspect(data)

    def test_wrong_bootloader_rejected(self):
        import struct
        data = bytearray((ROOT / 'firmware/firmware.bin').read_bytes())
        struct.pack_into('<I', data, 4, 0x08000251)
        with self.assertRaises(ValueError):
            firmware.inspect(data)

    def pin(self, count=2, target=0):
        pin = object.__new__(multi.PrinterMultiPin)
        pin.mcu_pins = [Mock() for _ in range(count)]
        pin.pin_list = ['PC5', 'PA7']
        pin.pin_type = 'pwm'
        pin.test_mode = 0
        pin.last_print_time = 100.
        heater = Mock()
        heater.get_temp.return_value = (25., target)
        heaters = Mock()
        heaters.get_all_heaters.return_value = ['extruder']
        heaters.lookup_heater.return_value = heater
        toolhead = Mock()
        toolhead.get_last_move_time.return_value = 50.
        pin.printer = Mock()
        pin.printer.lookup_object.side_effect = {'heaters': heaters, 'toolhead': toolhead}.__getitem__
        return pin

    def command(self, mode):
        return SimpleNamespace(get_int=lambda *args, **kwargs: mode,
                               error=ValueError, respond_info=Mock())

    def test_normal_supports_any_number_of_pins(self):
        pin = self.pin(3)
        pin.set_pwm(101., .6)
        for output in pin.mcu_pins:
            output.set_pwm.assert_called_once_with(101., .6)

    def test_each_selection_disables_other_output(self):
        for method in ('set_pwm', 'set_digital'):
            for mode in (1, 2):
                pin = self.pin()
                pin.test_mode = mode
                getattr(pin, method)(101., .7)
                for index, output in enumerate(pin.mcu_pins):
                    getattr(output, method).assert_called_once_with(
                        101., .7 if index == mode - 1 else 0.)

    def test_switch_drains_scheduled_output_and_normal_can_resume(self):
        pin = self.pin()
        pin.cmd_SET_MULTI_PIN_MODE(self.command(2))
        for output in pin.mcu_pins:
            output.set_pwm.assert_called_once_with(100.001, 0.)
        self.assertEqual(pin.test_mode, 2)
        pin.cmd_SET_MULTI_PIN_MODE(self.command(0))
        pin.set_pwm(102., .4)
        for output in pin.mcu_pins:
            output.set_pwm.assert_called_with(102., .4)

    def test_heating_rejects_switch_without_changing_mode(self):
        pin = self.pin(target=200)
        with self.assertRaisesRegex(ValueError, 'TURN_OFF_HEATERS'):
            pin.cmd_SET_MULTI_PIN_MODE(self.command(1))
        self.assertEqual(pin.test_mode, 0)
        pin.mcu_pins[0].set_pwm.assert_not_called()

    def test_one_pin_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exactly 2'):
            self.pin(1).cmd_SET_MULTI_PIN_MODE(self.command(1))

    def test_printing_and_paused_rejected(self):
        for state in ('printing', 'paused'):
            with patch.object(idle, 'request', side_effect=[
                {'state': 'ready'}, {'status': {'print_stats': {'state': state},
                                               'heaters': {'available_heaters': []}}}]):
                with self.assertRaises(SystemExit):
                    idle.main()

    def test_mismatch_error_allowed(self):
        with patch.object(idle, 'request', return_value={'state': 'error'}):
            idle.main()

    def test_api_failure_rejected(self):
        with patch.object(idle, 'request', side_effect=OSError('unavailable')):
            with self.assertRaises(SystemExit):
                idle.main()

    def test_heating_rejected_and_cold_idle_allowed(self):
        for target in (0, 200):
            with patch.object(idle, 'request', side_effect=[
                {'state': 'ready'},
                {'status': {'print_stats': {'state': 'standby'},
                            'heaters': {'available_heaters': ['extruder']}}},
                {'status': {'extruder': {'target': target}}}]):
                if target:
                    with self.assertRaises(SystemExit):
                        idle.main()
                else:
                    idle.main()


if __name__ == '__main__':
    unittest.main()
