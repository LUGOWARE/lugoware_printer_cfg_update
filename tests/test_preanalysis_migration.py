import ast, json, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'maintenance'))
from install_preanalysis import patch_sd
ASSETS=ROOT/'maintenance/preanalysis'
class Migration(unittest.TestCase):
 def test_supported_and_idempotent(self):
  before,after=json.loads((ASSETS/'virtual_sd_work.json').read_text())
  legacy=json.loads((ASSETS/'virtual_sd_legacy.json').read_text())
  for body in [before,after]+legacy:
   source='class VirtualSD:\n'+body
   actual=patch_sd(source,ASSETS)
   self.assertEqual(actual,'class VirtualSD:\n'+after)
   self.assertEqual(patch_sd(actual,ASSETS),actual)
   ast.parse(actual)
 def test_unknown_changes_rejected(self):
  body=json.loads((ASSETS/'virtual_sd_legacy.json').read_text())[0]
  with self.assertRaises(ValueError):
   patch_sd('class VirtualSD:\n'+body.replace('read(8192)','read(4096)'),ASSETS)
if __name__=='__main__': unittest.main()
