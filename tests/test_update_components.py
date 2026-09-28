from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
import update_components as module


class ComponentTests(unittest.TestCase):
    def test_version_hash_and_packages(self):
        self.assertFalse(module.needs_update('system', {'package_count': 0}))
        self.assertTrue(module.needs_update('system', {'package_count': 3}))
        self.assertFalse(module.needs_update('mainsail', {'version': 'v2', 'remote_version': 'v2'}))
        self.assertTrue(module.needs_update('moonraker', {'version': 'v2', 'remote_version': 'v2', 'current_hash': 'a', 'remote_hash': 'b'}))
        for info in ({}, {'version': 'v2', 'remote_version': '?'}, {'is_dirty': True}, {'is_valid': False}):
            with self.assertRaises(RuntimeError):
                module.needs_update('moonraker', info)

    def test_targets_order_skip_latest_and_restore_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            states = {name: {'version': 'old', 'remote_version': 'new'} for name in module.COMPONENTS}
            states['system'] = {'package_count': 3}
            states['mainsail'] = {'version': 'new', 'remote_version': 'new'}
            calls = []
            def request(label, endpoint, body):
                calls.append((label, endpoint, body))
                states[label] = {'package_count': 0} if label == 'system' else {'version': 'new', 'remote_version': 'new'}
                return 'ok'
            with patch.dict(os.environ, {'BACKUP_DIR': tmp}), patch.object(module, 'check_idle'), \
                 patch.object(module, 'restore_known_patch', return_value=Path(tmp) / 'updater.py'), \
                 patch.object(module, 'wait_status', side_effect=lambda: {'version_info': states}), \
                 patch.object(module, 'refresh', side_effect=lambda name: {'version_info': states}), \
                 patch.object(module, 'progress_request', side_effect=request), \
                 patch.object(module, 'patch') as restore, patch.object(module.subprocess, 'run'):
                module.main()
                restore.assert_called_once()
            self.assertEqual([c[0] for c in calls], ['system', 'print_area_bed_mesh', 'sonar', 'moonraker'])
            self.assertTrue(all(c[1] != '/machine/update/full' for c in calls))

    def test_failure_still_reapplies_patch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'BACKUP_DIR': tmp}), \
             patch.object(module, 'check_idle'), patch.object(module, 'restore_known_patch', return_value=Path(tmp) / 'updater.py'), \
             patch.object(module, 'wait_status', side_effect=RuntimeError('offline')), \
             patch.object(module, 'patch') as restore, patch.object(module.subprocess, 'run'):
            with self.assertRaises(RuntimeError):
                module.main()
            restore.assert_called_once()

    def test_unknown_modification_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'moonraker/components/update_manager/update_manager.py'
            target.parent.mkdir(parents=True)
            target.write_text('user modification')
            with patch.object(module.subprocess, 'check_output', return_value=b'original'), \
                 patch.object(module, 'replacement', return_value=('known patch', True)):
                with self.assertRaises(RuntimeError):
                    module.restore_known_patch(root, root)
            self.assertEqual(target.read_text(), 'user modification')
