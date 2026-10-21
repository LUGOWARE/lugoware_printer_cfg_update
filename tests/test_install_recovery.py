import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
import check_idle

class RecoveryTests(unittest.TestCase):
 def test_stopped_failed_install_starts_but_never_restarts(self):
  with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'home',return_value=Path(tmp)), patch('subprocess.check_output',return_value='inactive\n'), patch('subprocess.run') as run, patch.object(check_idle,'request',return_value={'state':'ready'}):
   check_idle.recover_stopped({'state':'failed'})
   self.assertEqual([c.args[0] for c in run.call_args_list],[['sudo','systemctl','start','moonraker'],['sudo','systemctl','start','klipper']])
 def test_unknown_stop_not_recovered(self):
  with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'home',return_value=Path(tmp)), patch('subprocess.run') as run:
   check_idle.recover_stopped();run.assert_not_called()
 def test_running_service_never_restarted(self):
  with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'home',return_value=Path(tmp)), patch('subprocess.check_output',return_value='active\n'), patch('subprocess.run') as run:
   check_idle.recover_stopped({'state':'failed'});run.assert_not_called()
 def test_interrupted_install_marker(self):
  with tempfile.TemporaryDirectory() as tmp, patch.object(Path,'home',return_value=Path(tmp)), patch('subprocess.check_output',return_value='failed\n'), patch('subprocess.run') as run, patch.object(check_idle,'request',return_value={'state':'ready'}):
   folder=Path(tmp)/'.local/share/lugoware';folder.mkdir(parents=True);(folder/'maintenance-stopped.json').write_text('{}')
   check_idle.recover_stopped();self.assertEqual(run.call_count,2)
