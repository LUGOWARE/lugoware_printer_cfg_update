import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import unittest,tempfile,threading,json
from pathlib import Path
from types import SimpleNamespace as O
from lugo_recovery import Recovery
class SourceCleanupTests(unittest.TestCase):
 def test_delete_only_missing_source_after_two_checks(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);g=root/'gcodes';g.mkdir();folder=root/'recovery';folder.mkdir()
   session='a'*32;other='b'*32
   data={'version':1,'session':session,'filename':'gone.gcode'}
   r=Recovery.__new__(Recovery);r.record=data;r.running=r.recovering=False;r.folder=folder;r.path=folder/'current.json'
   r.missing_sources={};r.deleted_sessions=set();r.io_lock=threading.Lock()
   r.printer=O(lookup_object=lambda n:O(sdcard_dirname=str(g)))
   r.status=lambda n,t:{'state':'standby'}
   r.path.write_text(json.dumps(data));(folder/(session+'.json')).write_text(json.dumps(data))
   (g/'keep.gcode').write_text('G1 X0')
   (folder/(other+'.json')).write_text(json.dumps({'version':1,'session':other,'filename':'keep.gcode'}))
   r.cleanup_missing_sources(5);self.assertTrue(r.path.exists())
   r.cleanup_missing_sources(10);self.assertFalse(r.path.exists());self.assertIsNone(r.record)
   self.assertFalse((folder/(session+'.json')).exists());self.assertTrue((folder/(other+'.json')).exists())
   self.assertIn(session,r.deleted_sessions)
 def test_active_print_skips_cleanup(self):
  r=Recovery.__new__(Recovery);r.running=True
  self.assertEqual(r.cleanup_missing_sources(1),6)
