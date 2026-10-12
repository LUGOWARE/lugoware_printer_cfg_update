import ast
import builtins
import gettext
import json
from pathlib import Path
import string
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maintenance'))
from lugo_i18n import Translations, translate_prompt, preheat_label
from install_screen_config import merge, SAVED
from install_i18n import patch_config, patch_screen, patch_prompts, patch_temperature, patch_gtk, patch_title, patch_network


class I18nTests(unittest.TestCase):
    def test_catalog_coverage_and_placeholders(self):
        base = json.loads((ROOT/'translations/en.json').read_text(encoding='utf-8'))
        locales = 'ar bg cs da de de_formal en es et fa fr he hr hu it jp ko lt nl pl pt pt_BR rs ru sk sl sv tr uk vi zh_CN zh_TW'.split()
        self.assertEqual(set(locales), {p.stem for p in (ROOT/'translations').glob('*.json')})
        fields = lambda s: sorted(f for _, f, _, _ in string.Formatter().parse(s) if f is not None)
        for locale in locales:
            catalog = json.loads((ROOT/f'translations/{locale}.json').read_text(encoding='utf-8'))
            self.assertEqual(set(base), set(catalog), locale)
            for key, value in catalog.items():
                self.assertTrue(value.strip(), (locale, key))
                self.assertEqual(fields(key), fields(value), (locale, key))
        for path in (ROOT/'panels/common').glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == '_':
                    self.assertIsInstance(node.args[0], ast.Constant)
                    self.assertIn(node.args[0].value, base, str(path))

    def test_language_switch_and_command_integrity(self):
        old = getattr(builtins, '_', None)
        try:
            for path in (ROOT/'translations').glob('*.json'):
                tr = Translations(gettext.NullTranslations(), path.stem, ROOT/'translations')
                tr.install()
                self.assertEqual(translate_prompt('prompt_footer_button 확인|TEST X=1|primary'),
                                 'prompt_footer_button '+tr.gettext('Confirm')+'|TEST X=1|primary')
                self.assertEqual(translate_prompt('prompt_footer_button M112'), 'prompt_footer_button M112')
                self.assertEqual(translate_prompt('prompt_text PLA_Profile_123'), 'prompt_text PLA_Profile_123')
                self.assertEqual(preheat_label('Bed : 60℃'), tr.gettext('Bed')+' : 60°C')
                self.assertEqual(preheat_label('Custom PLA'), 'Custom PLA')
                text = translate_prompt('prompt_text 히터 2 (PA4): 정상 작동')
                self.assertIn('PA4', text)
                self.assertIn('2', text)
        finally:
            if old is None: del builtins._
            else: builtins._ = old

    def test_official_translation_priority(self):
        class Official(gettext.NullTranslations):
            def gettext(self, text): return 'official' if text == 'Bed' else text
        tr = Translations(Official(), 'ko', ROOT/'translations')
        self.assertEqual(tr.gettext('Bed'), 'official')
        self.assertEqual(tr.gettext('unrecognized'), 'unrecognized')

    def test_preserve_language_settings_and_repeat(self):
        template = '[printer FLEX4]\nextrude_distances: 15\n[menu __main prepare_preview]\nname: Prepare\npanel: tool_prepare\n'+SAVED+'\n#~# [main]\n#~# language = en\n'
        for lang in ('ko', 'de', 'jp', 'system_lang'):
            current = '[main]\nlanguage: fr\n[include custom.conf]\n[printer My Printer]\nmoonraker_host: 192.168.0.151\n'+SAVED+'\n#~# [main]\n#~# language = '+lang+'\n#~# theme = material-darker\n'
            updated = merge(current, template)
            self.assertEqual(updated.partition(SAVED)[2], current.partition(SAVED)[2])
            self.assertIn('language: fr', updated)
            self.assertIn('moonraker_host: 192.168.0.151', updated)
            self.assertIn('[include custom.conf]', updated)
            self.assertIn("name: {{ _('Prepare') }}", updated)
            self.assertEqual(merge(updated, template), updated)
        fresh = merge('', template)
        self.assertNotIn('language', fresh)
        self.assertEqual(merge(fresh, template), fresh)

    def test_patch_repeat(self):
        pairs = [(patch_config, '        self.lang = self.langs[lang]\n'),
                 (patch_screen, '    def show_popup_message(self, message, level=3, from_ws=False):\n'),
                 (patch_prompts, '    def decode(self, data):\n'),
                 (patch_temperature, 'button(label=option, style="x")\n')]
        for patch, source in pairs:
            result = patch(source)
            self.assertEqual(patch(result), result)

    def test_popup_patch_with_clock_filter_between_insertions(self):
        source = '    def show_popup_message(self, message, level=3, from_ws=False):\n'
        patched = patch_screen(source)
        patched = patched.replace(source, source+'        # another installer inserts its filter here\n')
        self.assertEqual(patch_screen(patched), patched)

    def test_layout_patch_repeat_and_preserve_other_methods(self):
        original = ('def format_label(widget, lines=2):\n    pass\n\n'
                    'class KlippyGtk:\n    def keep(self):\n        return 42\n')
        patched = patch_gtk(original)
        self.assertIn('format_button(widget, lines)', patched)
        self.assertIn('return 42', patched)
        self.assertEqual(patch_gtk(patched), patched)
        title = '        self.control["time"] = Gtk.Label(label="00:00")\n'
        self.assertEqual(patch_title(patch_title(title)), patch_title(title))

    def test_unrecognized_layout_stops_installation(self):
        with self.assertRaises(ValueError): patch_gtk('unknown implementation')
        with self.assertRaises(ValueError): patch_title('unknown implementation')

    def test_upgrade_unbounded_title_patch(self):
        previous = ('        from ks_includes.lugo_layout import wrap_label\n'
                    '        wrap_label(self.titlelbl, 20)\n\n'
                    '        self.control["time"] = Gtk.Label(label="00:00")\n')
        updated = patch_title(previous)
        self.assertNotIn('wrap_label(self.titlelbl', updated)
        self.assertEqual(updated.count('fit_title(self.titlelbl)'), 1)
        self.assertEqual(patch_title(updated), updated)

    def test_network_selector_patch_is_scoped_and_repeatable(self):
        original = ('            self.labels["interface"] = Gtk.ComboBoxText()\n'
                    '            self.labels["interface"].connect("changed", self.iface_changed)\n'
                    '        eap_method = Gtk.ComboBoxText(hexpand=True)\n')
        updated = patch_network(original)
        self.assertIn('InterfaceSelector()', updated)
        self.assertIn('eap_method = Gtk.ComboBoxText(hexpand=True)', updated)
        self.assertIn('connect("changed", self.iface_changed)', updated)
        self.assertEqual(patch_network(updated), updated)
        with self.assertRaises(ValueError): patch_network('unsupported network panel')


if __name__ == '__main__': unittest.main()
