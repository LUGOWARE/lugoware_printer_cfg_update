import ast
import logging
from pathlib import Path
from types import SimpleNamespace as Obj
import unittest

tree = ast.parse((Path(__file__).resolve().parents[1] / 'panels/common/tool_temperature.py').read_text(encoding='utf-8'))
panel = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Panel')
methods = [n for n in panel.body if isinstance(n, ast.FunctionDef) and n.name in ('reset_request', 'query', 'activate', 'deactivate', 'saved', 'adjust_temperature')]
clock = Obj(monotonic=lambda: 100.)
namespace = {'_': lambda s: s, 'time': clock, 'logging': logging, 'GLib': Obj(timeout_add_seconds=lambda *a: 1, source_remove=lambda *a: None)}
cls = ast.ClassDef(name='Panel', bases=[], keywords=[], body=methods, decorator_list=[])
exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'recovery', 'exec'), namespace)

class Tests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.p = namespace['Panel']()
        self.p._screen = Obj(_ws=Obj(connected=True, send_method=lambda *a: self.sent.append(a)), show_popup_message=lambda s: None)
        self.p.socket = self.p._screen._ws
        self.p.timer = None
        self.p.generation = 0
        self.p.request_serial = 1
        self.p.sending = True
        self.p.sent_at = 98.
        self.p.pending = 0
        self.p.status = Obj(set_text=lambda s: None)
        self.p.received = lambda *a: None

    def test_reenter_after_missing_reply_restores_query(self):
        self.p.activate()
        self.assertFalse(self.p.sending)
        self.assertEqual(self.sent[0][0], 'printer.objects.query')

    def test_query_continues_during_request(self):
        self.p.query()
        self.assertTrue(self.p.sending)
        self.assertEqual(len(self.sent), 1)

    def test_timeout_recovers_without_resending_temperature(self):
        self.p.sent_at = 90.
        self.p.query()
        self.assertFalse(self.p.sending)
        self.assertEqual([s[0] for s in self.sent], ['printer.objects.query'])

    def test_disconnect_clears_pending_request(self):
        self.p._screen._ws.connected = False
        self.p.query()
        self.assertFalse(self.p.sending)
        self.assertEqual(self.sent, [])

    def test_old_reply_cannot_unlock_new_request(self):
        self.p.request_serial = 4
        self.p.saved({'result': {}}, serial=3)
        self.assertTrue(self.p.sending)

    def test_bed_press_during_home_sends_nothing(self):
        self.p.sending = False
        self.p.last_status = 100
        self.p.state = {'active': True, 'bed_ready': False}
        self.p.bed_target = 0
        self.p.adjust_temperature(None, 'bed', 1)
        self.assertEqual(self.sent, [])
        self.assertFalse(self.p.sending)

    def test_initialized_bed_uses_direct_api_and_actual_target(self):
        self.p.sending = False
        self.p.last_status = 100
        self.p.state = {'active': True, 'bed_ready': True, 'live_bed_api': True}
        self.p.bed_target = 60
        self.p.adjust_temperature(None, 'bed', 1)
        self.assertEqual(self.sent[0][:2], ('printer.lugo_tool_temperature.set_bed', {'temperature': 61}))

if __name__ == '__main__':
    unittest.main()
