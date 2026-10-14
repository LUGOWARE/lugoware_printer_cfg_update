import asyncio
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from lugoware_updates import UpdateStatus

class ProgressTests(unittest.TestCase):
    def instance(self, folder):
        obj = UpdateStatus.__new__(UpdateStatus)
        obj.folder = folder
        obj.requests = {}
        obj.timer = Mock()
        obj.server = Mock()
        obj.server.lookup_component.return_value = None
        return obj

    def test_download_success_is_not_install_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = self.instance(Path(tmp))
            original = Mock()
            helper = SimpleNamespace(cur_update_app='lugoware_system', cur_update_id=42,
                                     notify_update_response=original)
            obj.server.lookup_component.return_value = SimpleNamespace(cmd_helper=helper)
            with self.assertRaises(StopIteration):
                obj.component_init().send(None)
            helper.notify_update_response('Git Repo lugoware_system: Update Finished...', True)
            self.assertFalse(original.call_args.args[1])
            self.assertTrue(obj.ui_pending(42))
            helper.notify_update_response('Error updating lugoware_system: failure', True)
            self.assertTrue(original.call_args.args[1])

    def test_progress_completion_and_reconnect_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = self.instance(Path(tmp))
            obj.queue_ui('lugoware_system', 42, 'system', 100)
            data = dict(run_id=str(101*10**9), state='queued', detail='waiting')
            obj.update_dialog({'system': data})
            self.assertFalse(obj.server.send_event.call_args.args[1]['complete'])
            # Simulate Moonraker restart: load pending request from disk.
            obj = self.instance(Path(tmp))
            data.update(state='complete', detail='abc123')
            obj.update_dialog({'system': data})
            self.assertTrue(obj.server.send_event.call_args.args[1]['complete'])
            self.assertIn('실제 설치 및 검증 완료', obj.server.send_event.call_args.args[1]['message'])

    def test_old_success_cannot_finish_new_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = self.instance(Path(tmp))
            obj.queue_ui('lugoware_config', 43, 'config', 100)
            obj.update_dialog({'config': dict(run_id=str(99*10**9), state='complete', detail='old')})
            obj.server.send_event.assert_not_called()

    def test_failed_install_is_explicit_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = self.instance(Path(tmp))
            obj.queue_ui('lugoware_system', 42, 'system', 100)
            obj.update_dialog({'system': dict(run_id=str(101*10**9), state='failed', detail='bad configuration')})
            event = obj.server.send_event.call_args.args[1]
            self.assertTrue(event['complete'])
            self.assertIn('설치 실패', event['message'])

    def test_full_update_waits_for_all_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            obj = self.instance(Path(tmp))
            obj.queue_ui('full', 42, 'system', 100)
            obj.queue_ui('full', 42, 'config', 100)
            states = {'system': dict(run_id=str(101*10**9), state='complete', detail='system done'),
                      'config': dict(run_id=str(101*10**9), state='queued', detail='config waiting')}
            obj.update_dialog(states)
            self.assertFalse(obj.server.send_event.call_args.args[1]['complete'])
            states['config']['state']='complete'
            obj.update_dialog(states)
            self.assertTrue(obj.server.send_event.call_args.args[1]['complete'])
