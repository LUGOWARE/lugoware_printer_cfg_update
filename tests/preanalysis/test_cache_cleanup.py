import json,tempfile,unittest
from pathlib import Path
from cache_cleanup_worker import cleanup,FOLDERS

class Tests(unittest.TestCase):
    def setup_files(self,d):
        h=Path(d);r=h/'gcodes';r.mkdir();f=h/FOLDERS[0];f.mkdir(parents=True)
        return h,r,f
    def test_deleted_only_all_formats(self):
        with tempfile.TemporaryDirectory() as d:
            h,r,f=self.setup_files(d);live=r/'live.gcode';live.write_text('ok')
            for i,key in enumerate(('stamp','signature','identity','key')):
                folder=h/FOLDERS[i];folder.mkdir(parents=True,exist_ok=True)
                payload=[str(r/'gone.gcode')]
                (folder/'gone.json').write_text(json.dumps({key:['job',payload] if key=='key' else payload}))
                (folder/'live.json').write_text(json.dumps({'identity':[str(live)]}))
            self.assertEqual(cleanup(h,r,lambda:True,lambda _:None),4)
            self.assertTrue(all((h/x/'live.json').exists() for x in FOLDERS))
    def test_reupload_and_replaced_cache_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            h,r,f=self.setup_files(d);c=f/'a.json';p=r/'a.gcode'
            c.write_text(json.dumps({'stamp':[str(p)]}))
            def wait(t):
                if t==2:p.write_text('new upload')
            self.assertEqual(cleanup(h,r,lambda:True,wait),0);self.assertTrue(c.exists())
    def test_busy_corrupt_outside_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            h,r,f=self.setup_files(d)
            (f/'outside.json').write_text(json.dumps({'stamp':[str(h/'outside.gcode')]}))
            (f/'bad.json').write_text('bad')
            self.assertEqual(cleanup(h,r,lambda:False,lambda _:None),0)
            self.assertEqual(cleanup(h,r,lambda:True,lambda _:None),0)
    def test_starting_print_aborts_delete(self):
        with tempfile.TemporaryDirectory() as d:
            h,r,f=self.setup_files(d);c=f/'a.json';c.write_text(json.dumps({'stamp':[str(r/'gone')]}))
            busy=[False]
            def wait(t):
                if t==2:busy[0]=True
            self.assertEqual(cleanup(h,r,lambda:not busy[0],wait),0);self.assertTrue(c.exists())

if __name__=='__main__':unittest.main()
