import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from lugoware_updates import UpdateStatus


class RetryTests(unittest.TestCase):
    def test_failed_current_install_can_retry_without_git_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = UpdateStatus.__new__(UpdateStatus)
            obj.folder = Path(tmp)
            path = obj.folder / 'system-status.json'
            path.write_text(json.dumps(dict(state='failed', detail='heater target', time=1)))
            original = {'is_valid': True, 'current_hash': 'abc', 'remote_hash': 'abc',
                        'version': 'v1', 'commits_behind': [], 'warnings': []}
            updater = SimpleNamespace(get_update_status=lambda: original,
                update=AsyncMock(return_value=False), restart_service=AsyncMock(), notify_status=Mock(),
                repo=SimpleNamespace(wait_for_refresh=AsyncMock(), is_current=lambda: True, is_dirty=lambda: False))
            git_update = updater.update
            obj.enable_retry(updater, 'system')
            info = updater.get_update_status()
            self.assertTrue(info['commits_behind'])
            self.assertEqual(info['current_hash'], info['remote_hash'])
            self.assertEqual(info['version'], 'v1')
            self.assertEqual(original['warnings'], [])
            self.assertTrue(asyncio.run(updater.update()))
            updater.restart_service.assert_awaited_once()
            git_update.assert_not_awaited()
            path.write_text(json.dumps(dict(state='complete')))
            self.assertFalse(updater.get_update_status()['commits_behind'])
            asyncio.run(updater.update())
            git_update.assert_awaited_once()

    def test_new_commits_and_dirty_repos_keep_normal_update_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = UpdateStatus.__new__(UpdateStatus);obj.folder=Path(tmp)
            (obj.folder/'config-status.json').write_text('{"state":"failed"}')
            for current,dirty in [(False,False),(True,True)]:
                updater=SimpleNamespace(get_update_status=lambda:{'is_valid':True},
                    update=AsyncMock(return_value=False),restart_service=AsyncMock(),notify_status=Mock(),
                    repo=SimpleNamespace(wait_for_refresh=AsyncMock(),is_current=lambda:current,is_dirty=lambda:dirty))
                original=updater.update
                obj.enable_retry(updater,'config')
                asyncio.run(updater.update())
                original.assert_awaited_once();updater.restart_service.assert_not_awaited()
