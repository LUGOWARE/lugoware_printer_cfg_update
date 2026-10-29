import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
import run_worker


class BootstrapTests(unittest.TestCase):
    def test_complete_verified_release_selected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            root = Path(tmp); commit = 'a' * 40
            (root / 'active-release').write_text(commit)
            with patch.object(run_worker, 'STATE', root), patch.object(run_worker, 'trusted') as trust:
                self.assertEqual(run_worker.worker_source(), root / commit / 'maintenance')
                self.assertEqual(trust.call_count, 3)

    def test_unverified_marker_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            root = Path(tmp); (root / 'active-release').write_text('../../other')
            with patch.object(run_worker, 'STATE', root), patch.object(run_worker, 'trusted'):
                with self.assertRaises(ValueError): run_worker.worker_source()

    def test_bootstrap_failure_reports_failed_and_log(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as tmp:
            home = Path(tmp)
            with patch.object(run_worker.Path, 'home', return_value=home), patch.object(
                    run_worker, 'worker_source', side_effect=ModuleNotFoundError('preserve_sensor_pins')):
                with self.assertRaises(ModuleNotFoundError): run_worker.main('system')
            state = json.loads((home/'.local/share/lugoware/system-status.json').read_text())
            self.assertEqual(state['state'], 'failed')
            self.assertIn('preserve_sensor_pins', state['detail'])
            self.assertIn('ModuleNotFoundError', Path(state['log']).read_text())

    def test_invalid_channel_creates_no_state(self):
        with patch.object(run_worker, 'report_failure') as report:
            with self.assertRaises(ValueError): run_worker.main('../bad')
            report.assert_not_called()


if __name__ == '__main__':
    unittest.main()
