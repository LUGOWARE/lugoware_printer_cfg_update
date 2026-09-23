import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_panels', ROOT / 'maintenance/install_panels.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PanelInstallTests(unittest.TestCase):
    def test_both_languages_replace_and_backup(self):
        for lang in ('ko', 'en'):
            with self.subTest(lang=lang), tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'panels'
                target.mkdir()
                backup = Path(tmp) / 'backup'
                (target / 'extrude.py').write_text('# original')
                source = ROOT / 'panels' / lang
                module.install(source, target, backup, check=True)
                self.assertFalse(backup.exists())
                module.install(source, target, backup)
                module.install(source, target, backup)
                self.assertEqual((backup / 'extrude.py').read_text(), '# original')
                for name in module.FILES:
                    self.assertEqual((source / name).read_bytes(), (target / name).read_bytes())

    def test_invalid_source_does_not_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / 'source', root / 'target'
            source.mkdir()
            target.mkdir()
            for name in module.FILES:
                (source / name).write_text('# valid')
                (target / name).write_text('# original')
            (source / module.FILES[-1]).write_text('def broken(')
            with self.assertRaises(SyntaxError):
                module.install(source, target, root / 'backup')
            for name in module.FILES:
                self.assertEqual((target / name).read_text(), '# original')


if __name__ == '__main__':
    unittest.main()
