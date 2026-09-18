import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('patch_prompts', Path(__file__).resolve().parents[1] / 'maintenance/patch_prompts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

ORIGINAL = '''class Prompt:
    text = ""
    def parse(self, data):
        if data == "prompt_begin":
            self.text = ""
        elif data.startswith("prompt_text"):
            self.text = data.replace("prompt_text ", "")
            return
        elif data.startswith("prompt_button "):
            return "button preserved"
'''


class PromptTests(unittest.TestCase):
    def test_accumulates_and_preserves_button_and_reset(self):
        text, changed = module.replacement(ORIGINAL)
        self.assertTrue(changed)
        namespace = {}
        exec(text, namespace)
        prompt = namespace['Prompt']()
        prompt.parse('prompt_text first')
        prompt.parse('prompt_text second prompt_text literal')
        self.assertEqual(prompt.text, 'first\nsecond prompt_text literal')
        self.assertEqual(prompt.parse('prompt_button OK'), 'button preserved')
        prompt.parse('prompt_begin')
        self.assertEqual(prompt.text, '')

    def test_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'prompts.py'
            target.write_bytes(ORIGINAL.encode())
            self.assertTrue(module.patch(target))
            patched = target.read_bytes()
            self.assertFalse(module.patch(target))
            self.assertEqual(target.read_bytes(), patched)
            self.assertEqual(target.with_suffix('.py.backup').read_bytes(), ORIGINAL.encode())

    def test_unexpected_block_unchanged_without_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'prompts.py'
            original = ORIGINAL.replace('self.text = data.replace', 'self.other = data.replace')
            target.write_bytes(original.encode())
            with self.assertRaises(ValueError):
                module.patch(target)
            self.assertEqual(target.read_bytes(), original.encode())
            self.assertFalse(target.with_suffix('.py.backup').exists())

    def test_missing_marker_rejected(self):
        with self.assertRaises(ValueError):
            module.replacement('x = 1\n')

    def test_syntax_error_rejected_before_write(self):
        with self.assertRaises(SyntaxError):
            module.replacement(ORIGINAL + '\ninvalid python syntax!\n')

    def test_crlf_preserved(self):
        result, changed = module.replacement(ORIGINAL.replace('\n', '\r\n'))
        self.assertTrue(changed)
        self.assertNotIn('\n', result.replace('\r\n', ''))
