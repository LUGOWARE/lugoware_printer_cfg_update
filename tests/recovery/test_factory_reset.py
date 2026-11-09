import importlib.util,sys,types,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
sys.modules.setdefault('fcntl',types.SimpleNamespace())
spec=importlib.util.spec_from_file_location('factory_reset',Path(__file__).resolve().parents[2]/'maintenance/recovery/factory_reset.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class ResetTests(unittest.TestCase):
 def test_reset_preserves_config_clears_only_selected_data(self):
  with tempfile.TemporaryDirectory() as t:
   h=Path(t);data=h/'printer_data';cfg=data/'config';cfg.mkdir(parents=True);(cfg/'printer.cfg').write_text('CALIBRATION')
   for folder in ('gcodes','recovery','logs'):(data/folder).mkdir()
   (data/'gcodes/test.gcode').write_text('G1 X0');(data/'recovery/current.json').write_text('{}')
   (data/'logs/lugoware_diagnostics.jsonl').write_text('result');(data/'logs/klippy.log').write_text('log')
   calls=[]
   def api(p,m='GET'):
    calls.append((p,m))
    if p=='/server/files/list?root=gcodes':return []
    if p.startswith('/server/history/list'):return {'count':0}
    return {}
   with patch.object(f,'HOME',h),patch.object(f,'DATA',data),patch.object(f,'STATE',h/'state.json'),patch.object(f,'api',api),patch.object(f,'privacy',return_value=None) as privacy,patch.object(f,'check',return_value={'machine_id':'id','ready':True,'files':[]}):
    self.assertTrue(f.reset('id')['ok'])
    self.assertEqual((cfg/'printer.cfg').read_text(),'CALIBRATION')
    self.assertFalse(list((data/'gcodes').iterdir()));self.assertFalse(list((data/'recovery').iterdir()))
    self.assertFalse((data/'logs/lugoware_diagnostics.jsonl').exists());self.assertTrue((data/'logs/klippy.log').exists())
    self.assertEqual(json.loads((h/'state.json').read_text())['status'],'pending')
    self.assertIn(('/server/history/reset_totals','POST'),calls)
    self.assertEqual([c.args[0] for c in privacy.call_args_list],['--clean','--schedule'])
 def test_identity_or_active_print_rejects_before_mutation(self):
  with patch.object(f,'write_state') as write,patch.object(f,'check',return_value={'machine_id':'id','ready':False,'reasons':['Print is active']}):
   with self.assertRaises(RuntimeError):f.reset('wrong')
   with self.assertRaises(RuntimeError):f.reset('id')
   write.assert_not_called()
 def test_unexpected_root_rejected(self):
  with self.assertRaises(RuntimeError):f.checked_folder(Path('something'),Path('elsewhere').resolve())
if __name__=='__main__':unittest.main()
