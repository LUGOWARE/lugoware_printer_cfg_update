import sys, unittest
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(root / p) for p in ('maintenance/preanalysis', 'maintenance/recovery', 'maintenance', 'tests/preanalysis')]
suite = unittest.defaultTestLoader.loadTestsFromNames(['test_preanalysis', 'test_completion', 'test_cache_cleanup'])
raise SystemExit(not unittest.TextTestRunner().run(suite).wasSuccessful())
