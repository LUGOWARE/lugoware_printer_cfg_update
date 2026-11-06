import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from install_screen_config import preserve_menu_choices, merge, SAVED, USER_MENUS

class MenuChoiceTests(unittest.TestCase):
    def test_user_choices_survive_templates(self):
        for enabled in ('True','False'):
            existing='[main]\nlanguage: ko\n\n'+''.join('['+s+']\nenable: '+enabled+'\n\n' for s in USER_MENUS)
            template=''.join('['+s+']\nenable: False\n\n' for s in USER_MENUS)
            for result in (merge(existing,template),preserve_menu_choices(existing,template)):
                for section in USER_MENUS:
                    self.assertIn('['+section+']\nenable: '+enabled,result)
                self.assertEqual(preserve_menu_choices(existing,result),result)
    def test_fresh_install_uses_conf_defaults(self):
        template='[menu __print macros]\nenable: False\n'
        self.assertEqual(preserve_menu_choices('',template),template)
