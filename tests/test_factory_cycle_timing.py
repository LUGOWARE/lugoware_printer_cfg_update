import importlib.util
from pathlib import Path
import unittest
p=Path(__file__).resolve().parents[1]/"maintenance/diagnostics/lugo_factory_qc.py"
spec=importlib.util.spec_from_file_location("qc_timing",p)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class TimingTests(unittest.TestCase):
    def test_whole_cycles_fit(self):
        costs={"docking":33.,"motor":180.,"probe":30.}
        for minutes in (5,30,60):
            available=minutes*60-20
            plan=module.cycle_plan(costs,available,minutes)
            self.assertTrue(all(isinstance(v,int) and v>=1 for v in plan.values()))
            self.assertLessEqual(sum(costs[k]*v*1.05 for k,v in plan.items())+3,available)
    def test_quick_reserves_motor_probe(self):
        plan=module.cycle_plan({"docking":33.,"motor":180.,"probe":30.},280,5)
        self.assertEqual(plan,{"docking":1,"motor":1,"probe":1})
    def test_minimum_one_each_even_when_budget_too_short(self):
        self.assertEqual(module.cycle_plan({"docking":100.,"motor":250.,"probe":80.},280,5),{"docking":1,"motor":1,"probe":1})
