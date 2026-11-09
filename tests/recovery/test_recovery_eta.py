import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"maintenance/recovery"))
import unittest
from recovery_eta import estimate, remaining_at
class RecoveryEtaTests(unittest.TestCase):
 def setUp(self):
  self.ctx={'filename':'a','initial_remaining':1200,'timeline':[{'offset':100,'remaining':1200},{'offset':1100,'remaining':0}]}
 def calc(self,t,pos):
  return estimate(self.ctx,{'filename':'a','state':'printing','print_duration':t},pos)['remaining']
 def test_startup_not_extrapolated(self):
  self.assertAlmostEqual(self.calc(30,101),1198.8)
 def test_later_bounded(self):
  self.assertEqual(self.calc(600,600),600)
  self.assertEqual(self.calc(3600,600),1200)
 def test_normal_job_untouched(self):
  self.assertIsNone(estimate(self.ctx,{'filename':'b','state':'printing'},100))
 def test_missing_anchors(self):
  self.ctx.update(timeline=[],initial_remaining=None)
  self.assertIsNone(self.calc(30,100))
 def test_completion(self):
  self.assertEqual(self.calc(1200,1100),0)
