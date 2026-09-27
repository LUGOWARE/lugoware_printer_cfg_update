import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maintenance'))
import upgrade_klipper as upgrade
import firmware_action as firmware


class UpgradePolicyTests(unittest.TestCase):
    def test_release_order_and_unknown(self):
        self.assertLess(upgrade.release('v0.12.0-249-gabc-dirty'), (0, 13, 0))
        self.assertEqual(upgrade.release('v0.13.0-745-gabc-dirty'), (0, 13, 0))
        self.assertGreater(upgrade.release('v0.14.0-1-gabc'), (0, 13, 0))
        with self.assertRaises(ValueError):
            upgrade.release('abcdef')

    def test_new_hosts_do_not_fetch_checkout_or_build(self):
        for version in ('v0.13.0-770-gabc', 'v0.13.0-771-gabc-dirty', 'v0.14.0-1-gabc'):
            with tempfile.TemporaryDirectory() as tmp, patch.object(upgrade, 'output', return_value=version), patch.object(upgrade, 'run') as run:
                upgrade.upgrade(Path(tmp), Path(tmp) / 'backup')
                run.assert_not_called()

    def test_unknown_customizations_block_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(upgrade, 'output', side_effect=['v0.12.0-1-gabc', 'klippy/mcu.py']), patch.object(upgrade, 'run') as run:
            with self.assertRaises(RuntimeError):
                upgrade.upgrade(Path(tmp), Path(tmp) / 'backup')
            run.assert_not_called()

    def test_old_host_preflight_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(upgrade, 'output', side_effect=['v0.12.0-1-gabc', 'klippy/extras/multi_pin.py']), patch.object(upgrade, 'run') as run:
            upgrade.upgrade(Path(tmp), Path(tmp) / 'backup', check=True)
            run.assert_not_called()

    def test_interrupted_cb2_build_is_not_skipped_on_new_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / '.git').mkdir()
            (folder / '.git/lugoware-linux-mcu-pending').write_text('pending')
            with patch.object(upgrade, 'output', side_effect=['v0.13.0-770-gabc', 'klippy/extras/multi_pin.py']) as output, patch.object(upgrade, 'run') as run:
                upgrade.upgrade(folder, folder / 'backup', check=True)
                self.assertEqual(output.call_count, 2)
                run.assert_not_called()

    def test_revision_threshold(self):
        for version in ('v0.12.0-249-ga19d64feb-dirty', 'v0.13.0', 'v0.13.0-745-gf0892d82b-dirty', 'v0.13.0-769-gabc'):
            self.assertLess(upgrade.version_key(version), upgrade.MIN_VERSION)
        for version in ('v0.13.0-770-gce7002be-dirty', 'v0.13.0-1000-gabc', 'v0.13.1', 'v0.14.0'):
            self.assertGreaterEqual(upgrade.version_key(version), upgrade.MIN_VERSION)

    def test_live_firmware_policy(self):
        ready = {'state': 'ready', 'software_version': 'v0.13.0-745-gabc'}
        self.assertEqual(firmware.decide(ready, {'mcu': {'mcu_version': 'exact'}}, 'exact'), 'skip')
        self.assertEqual(firmware.decide(ready, {'mcu': {'mcu_version': 'newer'}}, 'exact'), 'keep')
        self.assertEqual(firmware.decide({'state': 'error'}, {}, 'exact'), 'flash')
        self.assertEqual(firmware.decide(ready, {}, 'exact'), 'flash')
        self.assertEqual(firmware.decide({'state': 'ready', 'software_version': 'v0.12.0-1-gabc'}, {'mcu': {'mcu_version': 'old'}}, 'exact'), 'flash')
