import importlib.util, os, tempfile, time, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('retention', Path(__file__).resolve().parents[1] / 'maintenance/config_backup_retention.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class RetentionTests(unittest.TestCase):
 def test_scope_and_idempotence(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); (p/'printer.cfg').write_text('[printer]')
   names=[]
   for i in range(1,7):
    f=p/('printer-202611%02d_120000.cfg'%i); f.write_text('backup'); os.utime(f,(100+i,100+i)); names.append(f.name)
   for n in ['printer_base.cfg','printer.cfg.bak','printer-20269999_120000.cfg','other-20261101_120000.cfg']:(p/n).write_text('keep')
   (p/'printer-20261107_120000.cfg').symlink_to(p/'printer.cfg')
   self.assertEqual(m.prune(p,1000),list(reversed(names[:3])))
   self.assertEqual(m.prune(p,1000),[])
   self.assertTrue((p/'printer_base.cfg').exists()); self.assertTrue((p/'printer-20261107_120000.cfg').is_symlink())
 def test_fresh_or_missing_primary(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)
   for i in range(1,6):(p/('printer-202611%02d_120000.cfg'%i)).write_text('backup')
   self.assertEqual(m.prune(p),[])
   (p/'printer.cfg').write_text('[printer]')
   self.assertEqual(m.prune(p),[])
if __name__=='__main__':unittest.main()
