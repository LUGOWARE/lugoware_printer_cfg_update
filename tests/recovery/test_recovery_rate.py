import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import unittest,queue
from types import SimpleNamespace as O
from lugo_recovery import Recovery
class RateTests(unittest.TestCase):
 def test_periodic_coalescing_terminal_immediate(self):
  r=Recovery.__new__(Recovery);r.pending=queue.Queue(1);now=[10.]
  r.reactor=O(monotonic=lambda:now[0]);r.record={'status':'recording','value':1}
  r.submit();self.assertEqual(r.pending.get()['value'],1)
  for t in [10.1,10.25,10.5,10.9]:now[0]=t;r.submit()
  self.assertTrue(r.pending.empty())
  now[0]=11.;r.record['value']=2;r.submit();self.assertEqual(r.pending.get()['value'],2)
  now[0]=11.1;r.record['status']='interrupted';r.submit();self.assertEqual(r.pending.get()['status'],'interrupted')
