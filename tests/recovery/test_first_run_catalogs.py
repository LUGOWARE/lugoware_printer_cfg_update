"""Catalog selection regression tests without requiring a GTK display."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[2]
tree=ast.parse((ROOT/'maintenance/recovery/first_run.py').read_text(encoding='utf-8'))
scope={}
for node in tree.body:
    if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name):
        name=node.targets[0].id
        if name in ('TEXT','TIMEZONE_PROMPTS'):scope[name]=ast.literal_eval(node.value)
panel=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Panel')
for node in panel.body:
    if isinstance(node,ast.FunctionDef) and node.name in ('tr','timezone_prompt'):
        exec(compile(ast.Module(body=[node],type_ignores=[]),'wizard-catalog','exec'),scope)

class CatalogTests(unittest.TestCase):
    def panel(self,language):
        return SimpleNamespace(_config=SimpleNamespace(get_main_config=lambda:{'language':language}))

    def test_every_supported_locale_has_complete_native_copy(self):
        languages={p.stem for p in (ROOT/'maintenance/screen_locales').glob('*.json')}
        self.assertGreaterEqual(len(languages),32)
        for language in languages:
            with self.subTest(language=language):
                obj=self.panel(language)
                result=scope['tr'](obj)
                self.assertEqual(result,scope['TEXT'][language])
                self.assertEqual(len(result),17)
                self.assertTrue(all(result))
                for index in (0,1):
                    prompt=scope['timezone_prompt'](obj,index)
                    self.assertTrue(prompt)
                    if language!='en':
                        self.assertNotEqual(prompt,scope['TIMEZONE_PROMPTS']['en'][index])

    def test_regional_variants_and_aliases(self):
        for alias,canonical in [('pt-BR','pt_BR'),('zh-TW','zh_TW'),('zh-Hant','zh_TW'),('ja','jp'),('sr','rs'),('de-formal','de_formal')]:
            self.assertEqual(scope['tr'](self.panel(alias)),scope['TEXT'][canonical])
        self.assertNotEqual(scope['tr'](self.panel('zh_TW')),scope['tr'](self.panel('zh_CN')))

if __name__=='__main__':unittest.main()
