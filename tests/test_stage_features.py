import ast
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
ROOT=Path(__file__).resolve().parents[1]/'maintenance'
sys.path.insert(0,str(ROOT))
import stage_features
import screen_restart_schedule as schedule

class StageFeaturesTests(unittest.TestCase):
 def test_stage_order_preserves_commands_and_is_idempotent(self):
  source='[gcode_macro START_PRINT]\ngcode:\n    {% if True %}\n    M104 S220\n    M117 Bed Mesh...\n    HOME_CHECK\n    BED_MESH_CALIBRATE\n    M117 PRINTING...\n    TEMPERATURE_WAIT SENSOR=extruder MINIMUM=200\n    G1 X230 F9000\n    {% endif %}\n'
  result=stage_features.config(source)
  self.assertEqual(stage_features.config(result),result)
  markers=['M117 Homing...','HOME_CHECK','M117 Bed Mesh...','BED_MESH_CALIBRATE','M117 Heating...','TEMPERATURE_WAIT','M117 PRINTING...']
  positions=[result.index(x) for x in markers];self.assertEqual(positions,sorted(positions))
  commands=lambda t:[x.strip() for x in t.splitlines() if x.strip().startswith(('G1 ','M104 ','TEMPERATURE_WAIT','HOME_CHECK','BED_MESH_CALIBRATE'))]
  self.assertEqual(commands(source),commands(result))
 def test_notice_timing(self):
  tree=ast.parse((ROOT/'print_features/restart_notice.py').read_text())
  fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='phase')
  ns={'math':math};exec(compile(ast.Module(body=[fn],type_ignores=[]),'notice','exec'),ns)
  phase=ns['phase']
  self.assertEqual(phase(60,0),('notice',60));self.assertIsNone(phase(60,10))
  for i in range(1,6):self.assertEqual(phase(60,60-i),('countdown',i))
  self.assertIsNone(phase(60,60))
 def test_busy_or_disconnected_defers_restart(self):
  import json
  for state, idle, allowed in [('printing','Printing',False),('paused','Ready',False),('cancelled','Ready',True),('standby','Printing',False),('unknown','Ready',False)]:
   response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'result':{'status':{'print_stats':{'state':state},'idle_timeout':{'state':idle}}}}).encode()
   with patch.object(schedule.urllib.request,'urlopen',return_value=response):self.assertEqual(schedule.idle(),allowed)
  with patch.object(schedule.urllib.request,'urlopen',side_effect=OSError):self.assertFalse(schedule.idle())
 def test_screen_install_is_idempotent(self):
  source='class Screen:\n    def init(self):\n        self.initial_connection()\n'
  result=stage_features.screen(source);self.assertEqual(stage_features.screen(result),result)
