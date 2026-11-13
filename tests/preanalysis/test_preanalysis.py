import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from lugo_preanalysis import Preanalysis, stamp

class GateTests(unittest.TestCase):
    def gate(self, path):
        g=Preanalysis.__new__(Preanalysis)
        g.generation=0;g.state='idle';g.progress=0;g.result=None;g.process=None
        g.reactor=Mock();g.reactor.register_async_callback.side_effect=lambda f:f(0)
        g.sd=Mock(file_position=0,work_timer=None,current_file=object())
        g.sd.file_path.return_value=path;g.sd.gcode.error=ValueError;g.resume=Mock()
        return g

    def test_print_waits_for_analysis(self):
        g=self.gate('test.gcode')
        with patch('lugo_preanalysis.threading.Thread') as t:
            g.start();self.assertEqual(g.state,'reading');g.resume.assert_not_called();t.return_value.start.assert_called_once()

    def test_duplicate_rejected(self):
        g=self.gate('test.gcode');g.state='reading'
        with self.assertRaises(ValueError):g.start()

    def test_resume_not_reanalyzed(self):
        g=self.gate('test.gcode');g.sd.file_position=20;g.start();g.resume.assert_called_once()

    def test_cancel_invalidates(self):
        g=self.gate('test.gcode');g.process=Mock();g.process.poll.return_value=None
        g.cancel();self.assertEqual(g.generation,1);g.process.terminate.assert_called_once()

    def test_file_replacement_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a.gcode';p.write_text('G1 X1');g=self.gate(str(p))
            g.result={'stamp':stamp(p)};self.assertIsNotNone(g.for_file(p))
            p.write_text('G1 X2\n');self.assertIsNone(g.for_file(p))

    def test_failed_worker_never_starts(self):
        g=self.gate('test.gcode')
        with patch('lugo_preanalysis.subprocess.Popen',side_effect=OSError('test failure')):
            g.work(0,'test.gcode',g.sd.current_file)
        self.assertEqual(g.state,'error');g.resume.assert_not_called()

if __name__=='__main__':unittest.main()
