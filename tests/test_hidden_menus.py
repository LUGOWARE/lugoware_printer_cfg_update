import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from install_screen_config import hide_advanced_menus, merge, SAVED

class MenuPolicyTests(unittest.TestCase):
    def test_menu_policy_preserves_saved_language_and_is_repeatable(self):
        source='[main]\nlanguage: ko\n\n[menu __print macros]\nenable: True\n\n'+SAVED+'\n#~# language = de\n'
        result=hide_advanced_menus(source)
        self.assertEqual(hide_advanced_menus(result),result)
        self.assertEqual(result.partition(SAVED)[2],source.partition(SAVED)[2])
        self.assertIn('language: ko',result)
        for section in ('menu __main more macros','menu __print macros','menu __main more limits','menu __print limits'):
            self.assertIn('['+section+']\nenable: False',result)
        updated=merge(result,'[menu __print macros]\nenable: True\n')
        self.assertIn('[menu __print macros]\nenable: False',updated)
