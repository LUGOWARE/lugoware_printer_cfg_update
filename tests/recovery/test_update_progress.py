import ast, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'maintenance'))
sys.path.insert(0,str(ROOT/'maintenance/recovery'))
from install_update_progress import patch, OLD
from update_progress_i18n import caption, ROWS, KEYS
import unittest
from lugoware_update_progress import Progress

class ProgressTests(unittest.TestCase):
    def test_download_cannot_complete_real_install(self):
        p=Progress()
        p.update({'application':'lugoware_system','message':'Receiving objects: 100%'})
        self.assertEqual(p.percent,25)
        p.update({'message':'Update Finished','complete':True})
        self.assertEqual(p.state,'running');self.assertLess(p.percent,100)
        p.update({'message':'lugoware_system: 다운로드 완료 — 실제 설치 진행 중입니다.','complete':False})
        p.update({'message':'[업데이트 4/6] 화면 설치'})
        before=p.percent
        p.update({'message':'Receiving objects: 10%'})
        self.assertEqual(p.percent,before)
        p.update({'message':'lugoware_system: 업데이트 완료 — 실제 설치 및 검증 완료','complete':True})
        self.assertEqual((p.state,p.percent),('complete',100))

    def test_failure_is_not_100_percent(self):
        p=Progress();p.update({'application':'lugoware_config','message':'설치 진행 중'})
        p.update({'message':'설치 실패 — 업데이트 미완료','complete':True})
        self.assertEqual(p.state,'failed');self.assertLess(p.percent,100)
        p.update({'message':'업데이트 완료 — 실제 설치 및 검증 완료','complete':True})
        self.assertEqual(p.state,'failed')

    def test_non_lugoware_retains_native_completion(self):
        p=Progress();p.update({'application':'other','message':'Done','complete':True})
        self.assertEqual(p.percent,100)



class InstallTests(unittest.TestCase):
    def test_patch_preserves_other_methods_and_is_repeatable(self):
        source='class Panel:\n    def custom(self):\n        return "device-specific"\n    def show_update_dialog(self):\n        pass\n    def finish_updating(self):\n        pass\n    def process(self, data):\n        if True:\n'+OLD+'\n                pass\n'
        result=patch(source)
        self.assertEqual(patch(result),result)
        self.assertIn('return "device-specific"',result)
        self.assertIn('terminal = self.render_update_progress(data)',result)
        self.assertIn('Gtk.Expander',result)
        self.assertIn('32768',result)
        compile(result,'patched','exec')
    def test_unknown_source_rejected(self):
        with self.assertRaises(ValueError):patch('class Panel: pass')
    def test_all_supported_language_captions(self):
        tree=ast.parse((ROOT/'maintenance/recovery/first_run.py').read_text(encoding='utf-8'))
        text=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TEXT' for t in n.targets))
        for lang in text:
            self.assertIn(lang,ROWS)
            for key in KEYS:self.assertTrue(caption(lang,key).strip())
        self.assertEqual(caption('unknown','notice'),caption('en','notice'))
        self.assertEqual(caption('zh-CN','notice'),caption('zh_CN','notice'))
