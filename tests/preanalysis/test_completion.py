import sys,json,tempfile,unittest,io
from pathlib import Path
from unittest.mock import Mock,patch
from lugo_preanalysis import Preanalysis,stamp
from test_preanalysis import GateTests

class CompletionTests(GateTests):
    def finished(self,path):
        g=self.gate(str(path));g.state='reading'
        proc=Mock(stdout=io.StringIO(json.dumps({'result':{'stamp':stamp(path)}})+'\n'),stderr=io.StringIO(''))
        proc.wait.return_value=0
        with patch('lugo_preanalysis.subprocess.Popen',return_value=proc),patch('lugo_preanalysis.threading.Timer'):
            g.work(0,str(path),g.sd.current_file)
        return g

    def test_waits_for_ack_and_ignores_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_text('G1 X1');g=self.finished(p)
            self.assertEqual(g.state,'finishing');g.resume.assert_not_called()
            cmd=Mock();cmd.get_int.return_value=1;g.cmd_continue(cmd);g.resume.assert_not_called()
            cmd.get_int.return_value=0
            with patch('lugo_preanalysis.threading.Thread'):
                g.cmd_continue(cmd);g.cmd_continue(cmd)
                g.reactor.register_timer.call_args[0][0](5)
            g.resume.assert_called_once()

    def test_cancel_and_file_change_block_start(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_text('G1 X1');g=self.finished(p)
            timer=g.reactor.register_timer.call_args[0][0];g.cancel();timer(5);g.resume.assert_not_called()
            g=self.finished(p);p.write_text('G1 X2\n');g.display_start(1)
            self.assertEqual(g.state,'error');g.resume.assert_not_called()

    def test_headless_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';p.write_text('G1 X1');g=self.finished(p)
            with patch('lugo_preanalysis.threading.Thread'):
                g.reactor.register_timer.call_args[0][0](5)
            g.resume.assert_called_once()

if __name__=='__main__':unittest.main()
