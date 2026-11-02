import ast
import json
import math
import re
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1] / 'maintenance'
sys.path.insert(0, str(ROOT))
import october_features as features
import screen_restart_schedule as schedule
import printer_messages

class NovemberTests(unittest.TestCase):
    def test_schedule_never_repeats_same_slot(self):
        for mode in ('idle', 'activity', 'deadline'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                clock=[0]; checks=[0]
                def idle():
                    checks[0]+=1
                    self.assertLess(checks[0],100,'Repeated countdown loop')
                    return clock[0] < {'idle': 999, 'activity': 3, 'deadline':60}[mode]
                timer=NS(time=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n))
                with patch.object(schedule,'Path',return_value=Path(d)), patch.object(schedule,'time',timer), patch.object(schedule,'idle',idle), patch.object(schedule.subprocess,'run') as run:
                    schedule.main()
                self.assertEqual(run.call_count,1 if mode=='idle' else 0)
                self.assertEqual(clock[0],3 if mode=='activity' else 60)
                self.assertFalse((Path(d)/'notice.json').exists())

    def test_retry_popup_timer_and_translation(self):
        ns={'re':re,'monotonic':lambda:10.,'GLib':Mock()}
        exec('def event(self,data):\n'+features.RETRY_NOTICE_BLOCK, ns)
        for message in ('Probe tolerance exceeded (1/5) - retrying.', 'Probe trigger error - recovering and retrying.'):
            screen=Mock(popup_message=object());obj=NS(_screen=screen)
            self.assertTrue(ns['event'](obj,'echo: '+message))
            args=ns['GLib'].timeout_add.call_args.args
            self.assertEqual(args[0],2000)
            screen.popup_message=object();args[1]()
            screen.close_popup_message.assert_not_called()
        for p in (ROOT/'printer_locales').glob('*.json'):
            catalog=json.loads(p.read_text(encoding='utf-8'))
            tr=lambda key:catalog.get(key,key)
            for i in range(1,5):
                key='Probe tolerance exceeded ({attempt}/5) - retrying.'
                self.assertEqual(printer_messages.translate_printer_message(key.format(attempt=i),tr), catalog[key].format(attempt=i))
            for key in ('Probe trigger error - recovering and retrying.', 'Excluded'):
                self.assertTrue(catalog[key])
            key='Object excluded. ({name})'
            self.assertEqual(printer_messages.translate_printer_message('Excluding object PART_4',tr),catalog[key].format(name='PART_4'))

    def test_patch_idempotence_and_specific_prefix(self):
        source='class Handler:\n    def _gcode_response(self, data):\n        return False\n'
        result=features.notification(source)
        self.assertEqual(features.notification(result),result)
        compile(result,'handler','exec')
        ns={};exec('def popup(message):\n'+features.EXCLUDE_NOTICE_BLOCK+'        return message\n',ns)
        self.assertEqual(ns['popup']('// Excluding object PART_4'),'Excluding object PART_4')
        self.assertEqual(ns['popup']('// Other message'),'// Other message')
        screen='class Screen:\n    def init(self):\n        self.initial_connection()\n    def show_popup_message(self, message, level=3, from_ws=False):\n        return message\n'
        result=features.popup(screen)
        self.assertEqual(features.popup(result),result)
        compile(result,'screen','exec')

    def test_restore_command_contains_name(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('guard',ROOT/'print_features/exclude_tool_guard.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        r=mod.ExcludeToolGuard.__new__(mod.ExcludeToolGuard);r.depth=0;r.reset()
        r.exclude=NS(current_object='PART_4');r.sd=NS(file_path=lambda:'same.gcode')
        r.gcode=NS(create_gcode_command=lambda cmd,line,params:line,run_script_from_command=lambda _:setattr(r.exclude,'current_object',None))
        # Extended handlers reconstruct parameters from the full line, not the params dict.
        def restore(line):
            name=re.search(r'\bNAME=(\S+)',line)
            self.assertIsNotNone(name)
            r.exclude.current_object=name[1]
        r.original={'EXCLUDE_OBJECT_START':restore}
        r.physical(lambda _:self.assertIsNone(r.exclude.current_object),None)
        self.assertEqual(r.exclude.current_object,'PART_4')

if __name__=='__main__':unittest.main()
