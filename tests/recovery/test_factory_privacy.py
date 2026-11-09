import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, call

spec=importlib.util.spec_from_file_location('privacy',Path(__file__).resolve().parents[2]/'maintenance/recovery/factory_privacy.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class PrivacyTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='posix','Linux descriptor security')
    def test_directory_symlink_cannot_escape(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);outside=root/'preserve';outside.mkdir();(outside/'config').write_text('safe')
            data=root/'backups';data.mkdir();(data/'link').symlink_to(outside,target_is_directory=True)
            p.clear(data,contents=True)
            self.assertEqual((outside/'config').read_text(),'safe')
            self.assertEqual(list(data.iterdir()),[])
            (root/'parent').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(OSError):p.clear(root/'parent/config')
            self.assertTrue((outside/'config').exists())

    @unittest.skipUnless(os.name=='posix','Linux descriptor security')
    def test_hardlinked_log_not_truncated(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);original=root/'config';original.write_text('safe')
            os.link(original,root/'log')
            with self.assertRaises(RuntimeError):p.clear(root/'log',truncate=True)
            self.assertEqual(original.read_text(),'safe')

    @unittest.skipUnless(os.name=='posix','Linux descriptor security')
    def test_cleanup_is_idempotent_and_preserves_config(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);cfg=root/'config';cfg.mkdir();(cfg/'printer.cfg').write_text('calibration')
            backups=root/'lugoware_backups';backups.mkdir();(backups/'old').mkdir();(backups/'old/file').write_text('old')
            for _ in range(2):p.clear(backups,contents=True)
            log=root/'log';log.write_text('old')
            p.clear(log,truncate=True)
            self.assertEqual(log.read_text(),'')
            self.assertEqual((cfg/'printer.cfg').read_text(),'calibration')

    def test_wifi_only_no_ethernet_deletion(self):
        wifi='11111111-1111-1111-1111-111111111111'
        eth='22222222-2222-2222-2222-222222222222'
        def command(*args):
            if args[-2:]==('connection','show'):
                return f'{wifi}:802-11-wireless\n{eth}:802-3-ethernet\n' if not getattr(command,'deleted',False) else f'{eth}:802-3-ethernet\n'
            if args[1:4]==('connection','delete','uuid'):command.deleted=True;return ''
            return 'eth0:ethernet:connected\nwlan0:wifi:connected\n'
        with patch.object(p,'run',side_effect=command) as run,patch.object(p,'status') as status:
            p.finish()
            self.assertIn(call('/usr/bin/nmcli','connection','delete','uuid',wifi),run.call_args_list)
            self.assertNotIn(call('/usr/bin/nmcli','connection','delete','uuid',eth),run.call_args_list)
            self.assertNotIn(call('/usr/bin/nmcli','device','disconnect','eth0'),run.call_args_list)
            status.assert_called_once_with('complete')

    def test_wifi_failure_is_not_reported_as_success(self):
        with patch.object(p,'wifi_profiles',side_effect=RuntimeError('offline')),patch.object(p,'status') as status:
            with self.assertRaises(RuntimeError):p.finish()
            status.assert_called_once_with('failed',error='offline')

    def test_schedule_does_not_delete_wifi_inline(self):
        with patch.object(p,'run') as run,patch.object(p,'status'),patch.object(p,'finish') as finish:
            p.schedule();finish.assert_not_called()
            self.assertIn('--on-active=20s',run.call_args.args)
            self.assertEqual(run.call_args.args[-2:],(p.SELF,'--finish'))

    def test_fixed_backup_scope(self):
        self.assertEqual(p.BACKUPS,('lugoware_backups','lugoware_m8p_backups'))
        self.assertNotIn('.ssh',p.HISTORY)

if __name__=='__main__':unittest.main()
