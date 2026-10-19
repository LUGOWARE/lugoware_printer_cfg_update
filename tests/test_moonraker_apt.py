from pathlib import Path, PurePosixPath
import shlex
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'maintenance'))
from moonraker_apt import scoped_script


class ScopedAptTests(unittest.TestCase):
    def test_both_commands_scoped_and_original_installer_flags_preserved(self):
        original = ('SRCDIR="old"\n'
                    '    sudo apt-get update --allow-releaseinfo-change\n'
                    '    sudo apt-get install --yes ${PACKAGES}\n'
                    'sudo systemctl restart moonraker\n')
        result = scoped_script(original, PurePosixPath('/home/biqu/moon raker'), PurePosixPath('/tmp/test apt/sources.list'))
        self.assertIn("SRCDIR='/home/biqu/moon raker'", result)
        lines = [shlex.split(line) for line in result.splitlines() if 'sudo apt-get' in line]
        self.assertEqual(len(lines), 2)
        for args in lines:
            self.assertIn('Dir::Etc::sourceparts=-', args)
            self.assertIn('Dir::Etc::sourcelist=/tmp/test apt/sources.list', args)
            self.assertIn('Acquire::http::Timeout=30', args)
            self.assertNotIn('trusted=yes', ' '.join(args))
        self.assertTrue(result.endswith('sudo systemctl restart moonraker\n'))
        self.assertIn('update --allow-releaseinfo-change', result)
        self.assertIn('install --yes ${PACKAGES}', result)

    def test_unknown_installer_rejected(self):
        with self.assertRaises(ValueError):
            scoped_script('echo unsupported\n', Path('/source'), Path('/sources'))

    def test_bullseye_uses_archive_without_vendor_sources(self):
        import tempfile
        from unittest.mock import patch
        from moonraker_apt import installer
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'moonraker'
            (folder/'scripts').mkdir(parents=True)
            original = folder/'scripts/install-moonraker.sh'
            content = 'SRCDIR="old"\nsudo apt-get update\nsudo apt-get install --yes ${PACKAGES}\n'
            original.write_text(content)
            read = Path.read_text
            def fake_read(path, *args, **kwargs):
                if str(path).replace('\\', '/') == '/etc/os-release':
                    return 'VERSION_CODENAME="bullseye"\n'
                return read(path, *args, **kwargs)
            with patch.object(Path, 'read_text', fake_read):
                with installer(folder) as script:
                    sources = (script.parent/'sources.list').read_text()
                    self.assertIn('https://archive.debian.org/debian-security bullseye-security', sources)
                    self.assertNotIn('armbian', sources)
                    self.assertNotIn('backports', sources)
                    self.assertIn('Acquire::https::No-Cache=true', script.read_text())
                    self.assertIn('APT::Update::Error-Mode=any', script.read_text())
                    self.assertEqual(original.read_text(), content)
                self.assertFalse(script.exists())
