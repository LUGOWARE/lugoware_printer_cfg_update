from pathlib import Path
import sys, unittest, json, re
from types import SimpleNamespace as NS
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
import october_features as features

class OctoberTests(unittest.TestCase):
 def test_popup_lifetime_and_newer_warning(self):
  ns={'re':re,'monotonic':lambda:10.,'GLib':Mock()}
  exec('def event(self,data):\n'+features.NOTIFICATION_BLOCK,ns)
  screen=Mock(popup_message=object());obj=NS(_screen=screen)
  event=ns['event'];event(obj,'echo: Probe measurement error - redeploying probe (2/2)')
  event(obj,'// PROBE_RECOVERY_SAMPLING')
  screen.close_popup_message.assert_not_called()
  args=ns['GLib'].timeout_add.call_args.args
  self.assertEqual(args[0],2001)
  args[1]();screen.close_popup_message.assert_called_once()
  screen.close_popup_message.reset_mock();event(obj,'echo: Probe measurement error - redeploying probe (2/2)');event(obj,'// PROBE_RECOVERY_SAMPLING')
  screen.popup_message=object();ns['GLib'].timeout_add.call_args.args[1]();screen.close_popup_message.assert_not_called()
 def test_count_only_popups_suppressed(self):
  ns={};exec('def popup(message,from_ws=True):\n'+features.POPUP_BLOCK+'        return from_ws\n',ns)
  self.assertIsNone(ns['popup']('Toolchange 12'))
  self.assertFalse(ns['popup']('Probe measurement error - redeploying probe (2/2)'))
  self.assertTrue(ns['popup']('Tool-head is not in position.'))
 def test_macros_and_homing_guards(self):
  from jinja2 import Environment
  env=Environment(variable_start_string='{',variable_end_string='}')
  source='[probe]\npin: ^!PC13\nspeed: 15\nactivate_gcode:\n    G4 P200\n'
  for prefix in ('DOCK_','PARK_'):
   for i in range(4):source+=f'\n[gcode_macro {prefix}{i}]\ngcode:\n    HOME_CHECK\n    G1 Z20 F1000\n    G1 X{200+i} Y{30+i} F6000\n'
  for i in range(4):source+=f'\n[gcode_macro DOCK_TOOL_{i}]\ngcode:\n    RESPOND MSG="DOCKING T{i}."\n    G1 Z5\n'
  result=features.config(source);self.assertEqual(features.config(result),result)
  self.assertTrue(result.startswith(source.split('[gcode_macro')[0]))
  for prefix in ('DOCK_','PARK_'):
   for i in range(4):
    block=re.search(r'(?s)\[gcode_macro '+prefix+str(i)+r'\].*?(?=\n\[|\Z)',result)[0].split('gcode:',1)[1]
    for axes in ('xyz','xy','z',''):
     commands=env.from_string(block).render(printer=NS(toolhead=NS(homed_axes=axes)))
     self.assertEqual('G1 Z20' in commands,axes!='xyz');self.assertIn(f'G1 X{200+i} Y{30+i} F6000',commands)
  template=env.from_string(features.LOWER_BED.split('gcode:',1)[1])
  def reject(message):raise ValueError(message)
  for axes,state,z,expected in [('xyz','cancelled',100,'Z10.0'),('xyz','complete',272,'Z3.0'),('xyz','complete',275,None)]:
   output=template.render(printer=NS(print_stats=NS(state=state),toolhead=NS(homed_axes=axes,position=NS(z=z),axis_maximum=NS(z=275))),action_raise_error=reject)
   if expected:self.assertIn(expected,output)
   else:self.assertNotIn('G1 ',output)
  for axes,state in [('','cancelled'),('xyz','printing'),('xyz','paused')]:
   with self.assertRaises(ValueError):template.render(printer=NS(print_stats=NS(state=state),toolhead=NS(homed_axes=axes)),action_raise_error=reject)
