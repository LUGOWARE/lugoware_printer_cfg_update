from pathlib import Path
import sys, unittest
from types import SimpleNamespace as Obj
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'maintenance'))
sys.path.insert(0,str(ROOT/'maintenance/recovery'))
from install_recovery_factory import header, updater_menu
from recovery_execution import RecoveryExecution

class ReleaseTests(unittest.TestCase):
 def test_updater_menu_enabled_without_losing_user_settings(self):
  for source in ('[main]\nlanguage: ko\n', '[menu __main more updater]\nenable: False\n\n[main]\nlanguage: ko\n'):
   source += '#~# --- Do not edit below this line.\n#~# [main]\n#~# language = ko\n'
   result=updater_menu(source)
   self.assertEqual(updater_menu(result),result)
   self.assertEqual(result.count('[menu __main more updater]'),1)
   self.assertIn('enable: True',result)
   self.assertIn('language: ko',result)
   self.assertTrue(result.endswith('#~# language = ko\n'))

 def test_header_preserves_calibration_and_connection(self):
  original='[mcu]\nserial: custom\n#*# <---------------------- SAVE_CONFIG ---------------------->\n#*# z_offset = 1.123\n'
  result=header(original)
  self.assertEqual(header(result),result)
  self.assertIn('serial: custom',result)
  self.assertTrue(result.endswith('#*# z_offset = 1.123\n'))
  self.assertLess(result.index('[lugo_recovery]'),result.index('#*# <'))
 def test_model_station_and_speed_limits(self):
  for x,maximum in ((230,277),(230,277),(334,377)):
   r=RecoveryExecution();r.reactor=Obj(monotonic=lambda:0)
   settings={'printer':{'max_velocity':100},'gcode_macro start_print':{'gcode':f'EXCLUDE_TOOL_PREPARE {{ct}} APPROACH_X={x} APPROACH_F=9000'}}
   r.status=lambda name,t:{'settings':settings} if name=='configfile' else {'axis_minimum':[-10,0,0],'axis_maximum':[maximum,257,375]}
   self.assertEqual(r.station_approach(),(x,6000))
   for source in ('', 'EXCLUDE_TOOL_PREPARE {ct} APPROACH_X=999 APPROACH_F=9000', 'EXCLUDE_TOOL_PREPARE {ct} APPROACH_X={variable} APPROACH_F=9000'):
    settings['gcode_macro start_print']['gcode']=source
    with self.assertRaises(ValueError):r.station_approach()
