import ast
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from final_print_ui import job_status, temperature, PRINT_MESSAGE_HELPER

class PrintDisplayTests(unittest.TestCase):
    def test_all_languages_progress_and_specific_messages(self):
        scope={};exec(PRINT_MESSAGE_HELPER,scope)
        render=scope['_lugo_print_message']
        for path in (Path(__file__).resolve().parents[1]/'maintenance/printer_locales').glob('*.json'):
            catalog=json.loads(path.read_text(encoding='utf-8'));tr=lambda s:catalog.get(s,s)
            self.assertEqual(render('37%','printing',.2,tr),tr('PRINTING...')+' 37%')
            self.assertEqual(render('PRINTING...','printing',0,tr),tr('PRINTING...')+' 0%')
            for message in ('Heating...','Bed Mesh...','Tool-head is not in position.'):
                self.assertEqual(render(message,'printing',.1,tr),tr(message))
            self.assertEqual(render('10%','paused',.1,tr),tr('10%'))

    def test_upgrade_old_panel_and_repeat_install(self):
        source='''class Panel:
    def update(self, data):
        if True:
            if True:
                self.labels["lcdmessage"].set_label(f"{data['display_status']['message']}")
    def show_buttons_for_state(self):
        if self.state == "printing":
            self.buttons["button_grid"].attach(self.buttons["pause"], 0, 0, 1, 1)
            self.enable_button("pause", "cancel")
        elif self.state == "paused":
            self.enable_button("resume", "cancel")
'''
        result=job_status(source);compile(result,'panel','exec')
        self.assertEqual(job_status(result),result)
        self.assertEqual(result.count('def _lugo_print_message('),1)
        self.assertIn('old_pause.destroy()',result)
        self.assertIn('self.buttons["pause"].connect("clicked", self.pause)',result)

    def test_temperature_keeps_landscape_scale(self):
        source='''increase = self._gtk.Button("increase", None, "color1")
decrease = self._gtk.Button("decrease", None, "color3")
'''
        result=temperature(source)
        self.assertEqual(temperature(result),result)
        self.assertEqual(result.count('self.bts if self._screen.vertical_mode else None'),2)
