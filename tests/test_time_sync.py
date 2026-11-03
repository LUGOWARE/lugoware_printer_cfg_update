import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from install_time_sync import config_text, select_provider


class TimeSyncTests(unittest.TestCase):
    def test_active_provider_preferred(self):
        self.assertEqual(select_provider({'chrony.service': (True, False), 'systemd-timesyncd.service': (True, True)}), 'systemd-timesyncd.service')

    def test_no_provider(self):
        self.assertIsNone(select_provider({'ntp.service': (False, False)}))

    def test_multiple_providers_rejected(self):
        with self.assertRaises(RuntimeError):
            select_provider({'chrony.service': (True, True), 'ntp.service': (True, True)})

    def test_existing_provider_not_replaced(self):
        self.assertEqual(select_provider({'ntp.service': (True, False)}), 'ntp.service')

    def test_chrony_idempotent_and_custom_config_retained(self):
        old = 'server local.example iburst\nmakestep 0.5 2\nrtcfile /var/lib/chrony/rtc\n'
        result = config_text('chrony.service', old)
        self.assertIn(old.strip(), result)
        self.assertNotIn('rtcsync', result)
        self.assertEqual(result, config_text('chrony.service', result))

    def test_chrony_startup_step_and_rtc_defaults(self):
        result = config_text('chrony.service', '')
        self.assertIn('makestep 1.0 3', result)
        self.assertIn('rtcsync', result)
        self.assertEqual(result, config_text('chrony.service', result))

    def test_ntp_configuration_idempotent(self):
        old = 'driftfile /var/lib/ntp/ntp.drift\nrestrict default kod nomodify nopeer noquery\n'
        result = config_text('ntp.service', old)
        self.assertIn(old.strip(), result)
        self.assertEqual(result, config_text('ntp.service', result))

    def test_timesyncd_supported_bullseye_options(self):
        result = config_text('systemd-timesyncd.service', '')
        self.assertTrue(result.startswith('[Time]\nNTP='))
        self.assertIn('ntp.aliyun.com', result)
        self.assertNotIn('SaveIntervalSec', result)


if __name__ == '__main__':
    unittest.main()
