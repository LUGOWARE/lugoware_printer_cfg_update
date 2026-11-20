import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from preserve_sensor_pins import preserve, sensor_pins


class SensorPinsTest(unittest.TestCase):
    def test_preserve_wiring_and_update_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'printer.cfg').write_text('[include base.cfg]\n[include custom.cfg]\n')
            (root / 'base.cfg').write_text('[extruder] # legacy\nsensor_pin: PA2 # wiring\n[heater_bed]\nsensor_pin: PA0\n')
            (root / 'custom.cfg').write_text('[temperature_sensor chamber]\nsensor_pin: aux:PA3\n')
            template = '[extruder]\nsensor_pin: PA1\nmax_temp: 350\n[heater_bed]\nsensor_pin: PB0\n'
            result = preserve(template, root / 'printer.cfg')
            self.assertIn('sensor_pin: PA2\nmax_temp: 350', result)
            self.assertIn('sensor_pin: PA0', result)
            self.assertNotIn('sensor_pin: PA1', result)
            self.assertEqual(preserve(result, root / 'printer.cfg'), result)

    def test_include_order_and_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'a.cfg').write_text('[extruder]\nsensor_pin: PA1\n')
            (root / 'b.cfg').write_text('[extruder]\nsensor_pin: ^aux:PA2\n')
            main = root / 'printer.cfg'
            main.write_text('[include a.cfg]\n[include b.cfg]\n')
            self.assertEqual(sensor_pins(main)['extruder'], '^aux:PA2')
            main.write_text('[include a.cfg]\n[extruder]\nsensor_pin: PA3\n')
            self.assertEqual(sensor_pins(main)['extruder'], 'PA3')

    def test_missing_or_recursive_include_fails_before_write(self):
        with tempfile.TemporaryDirectory() as folder:
            main = Path(folder) / 'printer.cfg'
            for text in ('[include missing.cfg]\n', '[include printer.cfg]\n'):
                main.write_text(text)
                with self.assertRaises(ValueError):
                    sensor_pins(main)

    def test_preserves_driver_currents_and_implicit_hold_current(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'base.cfg').write_text(
                '[tmc5160 stepper_x]\nrun_current: 2.75\nhold_current: 1.20\n'
                '[tmc2209 stepper_z]\nrun_current: 0.92\n')
            (root / 'custom.cfg').write_text('[tmc5160 stepper_x]\nrun_current: 2.85\n')
            main = root / 'printer.cfg'
            main.write_text('[include base.cfg]\n[include custom.cfg]\n')
            template = ('# Updated profile\n[tmc5160 stepper_x]\nrun_current = 3.0 # amps\n'
                        'sense_resistor: 0.075\n[tmc2209 stepper_z]\nrun_current: 1.6\n'
                        'hold_current: 0.8\n[tmc2209 extruder]\nrun_current: 0.7\n')
            result = preserve(template, main)
            self.assertIn('run_current = 2.85 # amps', result)
            self.assertIn('hold_current: 1.20', result)
            self.assertIn('sense_resistor: 0.075', result)
            self.assertIn('[tmc2209 stepper_z]\nrun_current: 0.92\n[tmc2209 extruder]', result)
            self.assertTrue(result.endswith('run_current: 0.7\n'))
            self.assertEqual(preserve(result, main), result)


if __name__ == '__main__':
    unittest.main()
