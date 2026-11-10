import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'maintenance'))
from auto_expand_root import plan

class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.table=dict(label='dos',unit='sectors',sectorsize=512,device='/dev/mmcblk1',partitions=[
            dict(node='/dev/mmcblk1p1',start=32768,size=524288,type='e'),
            dict(node='/dev/mmcblk1p2',start=557056,size=10649600,type='83')])
        self.total=61071360
    def test_16_layout_preserves_start_and_boot(self):
        before=copy.deepcopy(self.table)
        disk,p,size=plan(self.table,'/dev/mmcblk1p2',self.total)
        self.assertEqual(disk,'/dev/mmcblk1')
        self.assertEqual(size+p['start'],self.total)
        self.assertGreater(size,p['size'])
        self.assertEqual(before,self.table)
    def test_full_partition_no_growth(self):
        self.table['partitions'][1]['size']=self.total-557056
        self.assertEqual(plan(self.table,'/dev/mmcblk1p2',self.total)[2],self.table['partitions'][1]['size'])
    def test_reject_gpt_usb_extended_overlap_and_extra_partition(self):
        cases=[]
        for field,value in [('label','gpt'),('sectorsize',4096),('device','/dev/sda')]:
            t=copy.deepcopy(self.table);t[field]=value;cases.append(t)
        t=copy.deepcopy(self.table);t['partitions'][1]['type']='5';cases.append(t)
        t=copy.deepcopy(self.table);t['partitions'][1]['start']=100;cases.append(t)
        t=copy.deepcopy(self.table);t['partitions'].append(dict(node='/dev/mmcblk1p3',start=12000000,size=100,type='83'));cases.append(t)
        for t in cases:
            with self.assertRaises(ValueError):plan(t,'/dev/mmcblk1p2',self.total)
        with self.assertRaises(ValueError):plan(self.table,'/dev/sda2',self.total)
    def test_installer_before_backups(self):
        source=(Path(__file__).resolve().parents[1]/'install.sh').read_text(encoding='utf-8')
        self.assertLess(source.index('auto_expand_root.py'),source.index('export BACKUP_DIR='))

if __name__=='__main__': unittest.main()
