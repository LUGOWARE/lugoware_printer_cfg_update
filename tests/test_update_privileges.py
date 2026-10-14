from pathlib import Path
import sys
import types
if sys.platform == "win32":
    sys.modules.setdefault("fcntl", types.SimpleNamespace())
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from update_root import authorized_channel, validate_action, prepare, execute, WORKER_FILES
from update_sudo import translate


class PrivilegeTests(unittest.TestCase):
    def test_system_service_accepts_v1_and_v2_cgroups(self):
        for prefix in ('0::', '1:name=systemd:'):
            self.assertEqual(authorized_channel(prefix + '/system.slice/lugoware-system-worker.service', 1000, 1000), 'system')

    def test_ssh_and_user_service_are_denied(self):
        for path in ('/user.slice/user-1000.slice/session-3.scope',
                     '/user.slice/lugoware-system-worker.service',
                     '/system.slice/lugoware-system-worker.service-fake',
                     '/system.slice/ssh.service'):
            with self.assertRaises(PermissionError):
                authorized_channel('0::' + path, 1000, 1000)

    def test_wrong_account_is_denied(self):
        with self.assertRaises(PermissionError):
            authorized_channel('0::/system.slice/lugoware-system-worker.service', 1001, 1000)

    def test_arbitrary_commands_and_paths_are_denied_even_inside_system_service(self):
        for argv in (['sh', '-c', 'id'], ['python3', '/tmp/code.py'],
                     ['service', 'restart', 'ssh'], ['packages', 'curl'],
                     ['extensions', '/tmp/evil.py'], ['cron-ensure', '/tmp/cron'],
                     ['refresh-worker', 'update_root.py'], ['logo', 'restore']):
            with self.assertRaises(PermissionError): validate_action(argv, 'system')

    def test_config_worker_can_only_probe_and_restart(self):
        validate_action(['probe'], 'config')
        validate_action(['restart-printer'], 'config')
        for argv in (['packages'], ['service', 'restart', 'moonraker'], ['prepare', 'a'*40]):
            with self.assertRaises(PermissionError): validate_action(argv, 'config')

    def test_fixed_operations_are_accepted(self):
        for argv in (['service', 'restart', 'klipper'], ['logo', 'verify'],
                     ['packages'], ['extensions'], ['cron-ensure'], ['refresh-worker']):
            validate_action(argv, 'system')

    def test_policy_cannot_be_replaced_by_worker_refresh(self):
        for name in ('update_root.py', 'update_sudo.py', 'logo_guard.py', 'install_update_privileges.py'):
            self.assertNotIn(name, WORKER_FILES)

    def test_rejected_action_never_executes(self):
        with patch('update_root.run_fixed') as run:
            with self.assertRaises(PermissionError): execute(['sh', '-c', 'id'], 'system', {})
            run.assert_not_called()

    def test_shim_does_not_need_password_or_broaden_environment(self):
        self.assertEqual(translate(['-v']), ['probe'])
        self.assertEqual(translate(['-n', 'systemctl', 'restart', 'klipper']), ['service', 'restart', 'klipper'])
        self.assertEqual(translate(['--lugoware-prepare', 'a'*40]), ['prepare', 'a'*40])
        with self.assertRaises(PermissionError): translate(['-E', 'sh'])

    def test_untrusted_commit_input_rejected_before_network(self):
        with self.assertRaises(ValueError): prepare('../../etc')

    def test_adapter_rejects_root_shell_and_apt_hooks(self):
        for args in (['/bin/sh', '-c', 'id'], ['python3', '/tmp/anything.py'],
                     ['tee', '/etc/sudoers'], ['install', '-m', '755', '/tmp/x', '/usr/bin/x'],
                     ['apt-get', '-o', 'APT::Update::Pre-Invoke::=id', 'update'],
                     ['apt-get', 'install', '-y', 'unapproved-package'],
                     ['systemctl', 'restart', 'ssh']):
            with self.assertRaises(PermissionError): translate(args)

    def test_adapter_never_passes_user_script_or_cron_path(self):
        self.assertEqual(translate(['python3', '/tmp/logo_guard.py', 'verify']), ['logo', 'verify'])
        self.assertEqual(translate(['crontab', '/tmp/arbitrary-cron']), ['cron-ensure'])
        self.assertEqual(translate(['tee', '/etc/systemd/system/klipper.service.d/90-lugoware-extension.conf']), ['extensions'])

    def test_package_lists_match_and_arguments_are_fixed(self):
        import update_root, update_sudo
        self.assertEqual(update_root.PACKAGES, update_sudo.PACKAGES)
        self.assertEqual(translate(['apt-get', 'install', '-y', 'fonts-noto-cjk']), ['packages'])

    def test_old_base_migration_stops_before_privileged_work(self):
        import upgrade_klipper
        import tempfile
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'LUGOWARE_SYSTEM_ONLY': '1'}), patch.object(upgrade_klipper, 'output', return_value='v0.12.0-1-gabc'), patch.object(upgrade_klipper, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'SSH installer'):
                upgrade_klipper.upgrade(Path(d), Path(d)/'backup')
            run.assert_not_called()

    def test_no_blanket_sudo_and_no_writable_system_snapshot(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'maintenance/install_update_privileges.py').read_text(encoding='utf-8')
        self.assertNotIn('NOPASSWD: ALL', source)
        self.assertIn('visudo', source)
        worker = (root/'maintenance/channel_worker.py').read_text(encoding='utf-8')
        self.assertIn("['sudo', '--lugoware-prepare', commit]", worker)
        script = (root/'install.sh').read_text(encoding='utf-8')
        self.assertNotIn('sudo -n -k true', script)


if __name__ == '__main__':
    unittest.main()
