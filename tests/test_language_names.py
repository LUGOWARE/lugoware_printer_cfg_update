import sys,types,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from install_i18n import patch_languages
from lugo_language_names import NAMES,language_name

class LanguageNamesTests(unittest.TestCase):
    def test_autonyms_cover_every_supported_locale(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(set(NAMES),{p.stem for p in (root/'translations').glob('*.json')})
        self.assertEqual(language_name('ko'),'한국어')
        self.assertEqual(language_name('en'),'English')
    def test_label_never_becomes_saved_locale_code(self):
        source='''class Panel:
    def __init__(self, config, screen):
        self._config=config
        self._screen=screen
        self.langs={}
        for lang in ["system_lang", *self._config.lang_list]:
            self.langs[lang] = {
                "name": lang,
                "type": "button",
                "callback": self._screen.change_language,
            }
'''
        result=patch_languages(source)
        self.assertEqual(patch_languages(result),result)
        module=types.ModuleType('ks_includes.lugo_language_names'); module.language_name=language_name
        from unittest.mock import patch,Mock
        with patch.dict(sys.modules,{'ks_includes':types.ModuleType('ks_includes'),'ks_includes.lugo_language_names':module}):
            ns={}; exec(result,ns)
            screen=types.SimpleNamespace(change_language=Mock())
            p=ns['Panel'](types.SimpleNamespace(lang_list=list(NAMES)),screen)
            self.assertNotIn('system_lang', p.langs)
            for code in NAMES:
                p.langs[code]['callback'](None,p.langs[code]['name'])
                screen.change_language.assert_called_with(None,code)
