import importlib.util
from pathlib import Path
import unittest
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('run_flash',
    Path(__file__).resolve().parents[1] / 'maintenance/run_flash.py')
flash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash)


class FlashResultTests(unittest.TestCase):
    def run_ready_check(self, actual):
        root = Path(__file__).resolve().parents[1]
        request = Mock(side_effect=lambda url: (
            {'state': 'ready'} if url == '/printer/info' else
            {'status': {'mcu': {'mcu_version': actual}}}))
        with patch.dict(sys.modules, {
            'check_idle': SimpleNamespace(request=request),
            'verify_firmware': SimpleNamespace(inspect=lambda data: {'version': 'new-version'})
        }), patch.object(sys, 'argv', ['wait_ready.py', str(root / 'firmware/firmware.bin')]), patch('time.sleep'):
            runpy.run_path(str(root / 'maintenance/wait_ready.py'), run_name='__main__')

    def test_runtime_version_match_accepted(self):
        self.run_ready_check('new-version')

    def test_ready_with_old_firmware_rejected(self):
        with self.assertRaisesRegex(SystemExit, 'MCU version mismatch'):
            self.run_ready_check('old-version')

    def test_ready_without_mcu_version_rejected(self):
        with self.assertRaisesRegex(SystemExit, 'MCU version mismatch'):
            self.run_ready_check(None)

    def test_completed_transfer_reset_error_requires_live_check(self):
        self.assertTrue(flash.completed_with_reset_error(
            'dfu-util: Invalid DFU suffix signature\n'
            'dfu-util: A valid DFU suffix will be required in a future dfu-util release!!!\n'
            'Download done.\nFile downloaded successfully\n'
            'dfu-util: Error during download get_status\n'
            'Failed to flash to /dev/ttyACM0: Error running dfu-util\n'))

    def test_partial_transfer_rejected(self):
        self.assertFalse(flash.completed_with_reset_error(
            'Download 16%\ndfu-util: Error during download get_status\n'))

    def test_other_error_after_completion_rejected(self):
        self.assertFalse(flash.completed_with_reset_error(
            'Download done.\nFile downloaded successfully\n'
            'dfu-util: Error during download get_status\n'
            'dfu-util: Verification failed\n'))

    def test_error_before_completion_rejected(self):
        self.assertFalse(flash.completed_with_reset_error(
            'dfu-util: Error during download get_status\n'
            'Download done.\nFile downloaded successfully\n'))

    def test_unrelated_failure_rejected(self):
        self.assertFalse(flash.completed_with_reset_error('Permission denied\n'))
