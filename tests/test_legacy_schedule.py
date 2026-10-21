from pathlib import Path
import subprocess
import tempfile
import unittest

class LegacyScheduleTests(unittest.TestCase):
 def test_legacy_preserves_crontab_before_stopping_klipper(self):
  source=(Path(__file__).resolve().parents[1]/'maintenance/apply.sh').read_text()
  begin=source.index('# Legacy service-restricted root policy')
  end=source.index('sudo systemctl stop klipper',begin)
  block=source[begin:end].replace('/opt/lugoware/screen-restart/schedule.py', '$BACKUP_DIR/schedule.py')
  for system, installed, expected in [('1',False,'old'),('1',True,'new'),('0',False,'new')]:
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);(root/'root.crontab').write_text('old');(root/'root.crontab.new').write_text('new')
    if installed:(root/'schedule.py').touch()
    import os
    subprocess.run(['bash','-eu','-c',block],env={**os.environ,'BACKUP_DIR':tmp,'LUGOWARE_SYSTEM_ONLY':system},check=True)
    self.assertEqual((root/'root.crontab.new').read_text(),expected)
