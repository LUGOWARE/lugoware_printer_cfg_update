from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maintenance'))
from install_multi_pin import install
from verify_multi_pin import verify


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / 'klipper'
        self.target = self.folder / 'klippy/extras/multi_pin.py'
        self.target.parent.mkdir(parents=True)
        self.target.write_text('# default\n')
        self.source = Path(temp.name) / 'custom.py'
        self.source.write_text('# custom\n')

    def query(self, url):
        if url == '/printer/info':
            return {'state': 'ready', 'klipper_path': str(self.folder)}
        return {'SET_MULTI_PIN_MODE': 'Select mode'}

    def test_restore_and_verify(self):
        install(self.folder, self.source)
        verify(self.folder, self.source, self.query)
        self.target.write_text('# overwritten\n')
        install(self.folder, self.source)
        self.assertEqual(self.target.read_bytes(), self.source.read_bytes())

    def test_overwritten_file_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'replaced'):
            verify(self.folder, self.source, self.query)

    def test_missing_runtime_command_rejected(self):
        install(self.folder, self.source)
        with self.assertRaisesRegex(RuntimeError, 'not registered'):
            verify(self.folder, self.source, lambda url: self.query(url) if url == '/printer/info' else {})

    def test_stale_cache_removed(self):
        cache = self.target.parent / '__pycache__/multi_pin.cpython-39.pyc'
        cache.parent.mkdir()
        cache.write_bytes(b'stale')
        install(self.folder, self.source)
        self.assertFalse(cache.exists())
