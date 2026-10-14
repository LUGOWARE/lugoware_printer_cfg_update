"""Exercise lifecycle logic with fake devices and mount commands, no sudo/mounts."""
import os
import subprocess
import tempfile
from pathlib import Path

STUB = '''#!/usr/bin/python3
import os, sys
from pathlib import Path
r=Path(os.environ['USB_TEST_ROOT']); m=r/'mounted'
cmd=Path(sys.argv[0]).name; args=sys.argv[1:]
if cmd=='blkid': print('vfat')
elif cmd=='mount':
 m.write_text(args[-2]); (r/'mount-count').write_text(str(int((r/'mount-count').read_text())+1))
elif cmd=='umount':
 if (r/'busy').exists() and '-l' not in args: sys.exit(1)
 m.unlink(missing_ok=True)
elif cmd=='findmnt':
 if not m.exists(): sys.exit(1)
 if '-S' in args and args[args.index('-S')+1] != m.read_text(): sys.exit(1)
 print(m.read_text())
'''

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    for name in ('bin','dev','lock'): (root/name).mkdir()
    for cmd in ('blkid','mount','umount','findmnt'):
        p=root/'bin'/cmd; p.write_text(STUB); p.chmod(0o755)
    source=Path(__file__).with_name('usb_udev.sh').read_text()
    source=source.replace('/home/biqu/printer_data/gcodes/usb',str(root/'usb'))
    source=source.replace('/run/lugoware-usb-owner',str(root/'owner'))
    source=source.replace('/run/lock/lugoware-usb.lock',str(root/'lock/file'))
    source=source.replace('/dev/$2',str(root/'dev')+'/$2').replace('-b "$device"','-e "$device"')
    script=root/'mount.sh'; script.write_text(source)
    env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],USB_TEST_ROOT=str(root))
    (root/'mount-count').write_text('0')
    for name in ('sda1','sdb1'): (root/'dev'/name).touch()
    def run(device,action,ok=True):
        result=subprocess.run(['bash',str(script),'usb',device,action],env=env,capture_output=True,text=True)
        assert (result.returncode==0)==ok,(device,action,result.stdout,result.stderr)
    run('sda1','add'); run('sda1','add')
    assert (root/'mount-count').read_text()=='1'
    run('sdb1','add'); run('sdb1','remove')
    assert (root/'mounted').read_text().endswith('sda1')
    (root/'busy').touch(); run('sda1','remove',False)
    assert (root/'mounted').exists()
    (root/'dev/sda1').unlink(); run('sda1','remove')
    assert not (root/'usb').exists()
    (root/'busy').unlink(); run('sdb1','add'); run('sdb1','remove')
    (root/'usb').mkdir(); (root/'usb/keep.gcode').write_text('G1 X1')
    run('sdb1','add',False)
    assert (root/'usb/keep.gcode').read_text()=='G1 X1'
    assert not (root/'mounted').exists()
    print('PASS repeated add, second drive, live busy failure, unplug cleanup, changed device name, local-file protection')
