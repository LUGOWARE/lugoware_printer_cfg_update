import ast,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'maintenance'))
from install_diagnostics import install,header,strip_legacy,screen_menu

class DiagnosticInstallTests(unittest.TestCase):
 def test_models_idempotent_and_preserve(self):
  for model in ('M','L','W'):
   with self.subTest(model=model), tempfile.TemporaryDirectory() as tmp:
    home=Path(tmp);cfg=home/'config';ks=home/'screen';kp=home/'klipper';cfg.mkdir()
    base='[extruder]\nsensor_pin: PA2\nheater_pin: multi_pin:dual_hotend_heater\n\n[gcode_macro HEATER_TEST]\ngcode:\n G4 P1\n\n[probe]\nz_offset: 1.234\n'
    printer='[mcu]\nserial: /dev/serial/test\n\n#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# [probe]\n#*# z_offset = 1.234\n'
    screen='[main]\nlanguage: ko\n\n[menu __main more heater_test]\nname: old\nenable: True\n\n#~# --- Do not edit below this line. This section is auto generated --- #~#\n#~# language = zh_CN\n'
    (cfg/'printer_base.cfg').write_text(base);(cfg/'printer.cfg').write_text(printer);(cfg/'KlipperScreen.conf').write_text(screen)
    install(cfg,ks,kp,home/'backup',model)
    before={str(p.relative_to(home)):p.read_bytes() for folder in (cfg,ks,kp) for p in folder.rglob('*') if p.is_file()}
    install(cfg,ks,kp,home/'backup',model)
    after={str(p.relative_to(home)):p.read_bytes() for folder in (cfg,ks,kp) for p in folder.rglob('*') if p.is_file()}
    self.assertEqual(before,after)
    self.assertIn('model: '+model,(cfg/'printer.cfg').read_text())
    self.assertIn('#*# z_offset = 1.234',(cfg/'printer.cfg').read_text())
    text=(cfg/'printer_base.cfg').read_text();self.assertIn('sensor_pin: PA2',text);self.assertNotIn('[gcode_macro HEATER_TEST]',text)
    text=(cfg/'KlipperScreen.conf').read_text();self.assertIn('#~# language = zh_CN',text);self.assertIn('panel: diagnostics',text)
 def test_translation_coverage(self):
  assets=ROOT/'maintenance/diagnostics';catalogs=json.loads((assets/'locales.json').read_text(encoding='utf-8'))
  keys=set()
  for node in ast.walk(ast.parse((assets/'diagnostics.py').read_text(encoding='utf-8'))):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='_' and node.args and isinstance(node.args[0],ast.Constant):keys.add(node.args[0].value)
  self.assertEqual(len(catalogs),32)
  for lang,entries in catalogs.items():
   self.assertFalse(keys-set(entries),(lang,keys-set(entries)))
   self.assertTrue(all(entries[k].strip() for k in keys),lang)
 def test_menu_config_only_upgrade(self):
  self.assertEqual(screen_menu(screen_menu('[main]\n')),screen_menu('[main]\n'))
  self.assertEqual(strip_legacy('[probe]\npin: PC13\n'),'[probe]\npin: PC13\n')

if __name__=='__main__':unittest.main()
