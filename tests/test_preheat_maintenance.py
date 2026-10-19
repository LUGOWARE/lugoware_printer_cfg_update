import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'maintenance'))
import check_idle

class PreheatTests(unittest.TestCase):
    def run_check(self, state='standby', target=200, after=0):
        sent = MagicMock()
        sent.__enter__.return_value.read.return_value = b'{"result":"ok"}'
        off = [False]
        def read(path):
            if path == '/printer/info': return {'state':'ready'}
            if 'print_stats&heaters' in path:
                return {'status': {'print_stats':{'state':state}, 'heaters':{'available_heaters':['extruder','heater_bed']}}}
            name = path.split('?')[1]
            return {'status':{name:{'target':after if off[0] else target}}}
        def post(req, **kw):
            self.assertEqual(req.get_method(), 'POST')
            self.assertIn(b'TURN_OFF_HEATERS', req.data)
            off[0] = True
            return sent
        with patch.object(check_idle,'request',side_effect=read), patch.object(check_idle.urllib.request,'urlopen',side_effect=post) as call:
            try: check_idle.main()
            finally: self.calls = call.call_count
    def test_preheat_turns_off_once(self):
        self.run_check()
        self.assertEqual(self.calls,1)
    def test_cold_no_command(self):
        self.run_check(target=0)
        self.assertEqual(self.calls,0)
    def test_print_pause_unknown_never_turn_off(self):
        for state in ('printing','paused','unknown'):
            with self.assertRaises(SystemExit): self.run_check(state=state)
            self.assertEqual(self.calls,0)
    def test_failed_shutdown_aborts(self):
        with self.assertRaises(SystemExit): self.run_check(after=100)
