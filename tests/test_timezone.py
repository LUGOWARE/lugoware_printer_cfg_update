import json
from pathlib import Path
import sys,types,unittest
if sys.platform=='win32': sys.modules.setdefault('pwd',types.SimpleNamespace())
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from install_timezone import patch_settings,policy
class TimezoneTests(unittest.TestCase):
    def test_settings_hook_is_idempotent(self):
        source='class Panel:\n    def __init__(self):\n        self.content.add(self.labels["settings_menu"])\n'
        once=patch_settings(source)
        self.assertEqual(once,patch_settings(once))
        self.assertIn('setting_title(self._config.get_main_config())',once)
    def test_permission_scope_is_timezone_only(self):
        for legacy in (False,True):
            text=policy('biqu',legacy)
            self.assertIn('org.freedesktop.timedate1.set-timezone',text)
            self.assertNotIn('set-time\n',text)
            self.assertNotIn('*',text)
        with self.assertRaises(ValueError): policy('biqu;root',True)
    def test_all_screen_languages_have_full_ui_and_zone_data(self):
        root=Path(__file__).resolve().parents[1]
        names={p.stem for p in (root/'translations').glob('*.json')}
        catalogs={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in (root/'maintenance/timezone_locales').glob('*.json')}
        self.assertEqual(names,set(catalogs))
        base=catalogs['en']
        for name,data in catalogs.items():
            for group in ('ui','countries','cities'):
                self.assertEqual(set(base[group]),set(data[group]),name)
                self.assertTrue(all(data[group].values()),name)
            self.assertEqual(len(data['ui']),9)
