"""Conservative online growth for the standard CB2 DOS/MMC/ext4 layout only."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True,
                          env=dict(os.environ, LC_ALL='C'), **kwargs).stdout.strip()


def plan(table, root, sectors):
    if table.get('label') != 'dos' or table.get('unit') != 'sectors' or table.get('sectorsize', 512) != 512:
        raise ValueError('Unsupported partition table')
    if not re.fullmatch(r'/dev/mmcblk[0-9]+p2', root):
        raise ValueError('Unsupported root device')
    disk = root[:-2]
    parts = table.get('partitions', [])
    if table.get('device') != disk or len(parts) != 2:
        raise ValueError('Expected two primary partitions')
    boot, system = sorted(parts, key=lambda p: p['start'])
    if boot['node'] != disk+'p1' or system['node'] != root or str(system['type']).lower() != '83':
        raise ValueError('Unexpected root partition')
    if str(boot['type']).lower() not in ('6','e','b','c'):
        raise ValueError('Unexpected boot partition')
    if not (0 < boot['start'] < boot['start']+boot['size'] <= system['start'] < system['start']+system['size'] <= sectors):
        raise ValueError('Invalid partition boundaries')
    if sectors >= 2**32:
        raise ValueError('Unsupported DOS disk size')
    return disk, system, sectors-system['start']


def idle():
    with urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/query?print_stats', timeout=5) as response:
        state=json.load(response)['result']['status']['print_stats']['state']
    if state not in ('standby','complete','cancelled','error'):
        raise RuntimeError('Printer must be idle before storage expansion')


def main():
    if os.geteuid() != 0:
        raise RuntimeError('Root permission required')
    if any(not shutil.which(tool) for tool in ('findmnt','sfdisk','blockdev','partx','resize2fs','dumpe2fs')):
        print('[Storage] Expansion skipped: required local tools unavailable'); return
    mount=json.loads(run('findmnt','-J','-o','SOURCE,FSTYPE,OPTIONS','/'))['filesystems'][0]
    root=os.path.realpath(mount['source'])
    if mount['fstype'] != 'ext4' or 'rw' not in mount['options'].split(',') or not re.fullmatch(r'/dev/mmcblk[0-9]+p2',root):
        print('[Storage] Expansion skipped: nonstandard root filesystem'); return
    disk=root[:-2]
    table=json.loads(run('sfdisk','--json',disk))['partitiontable']
    sectors=int(run('blockdev','--getsz',disk))
    try:
        disk, partition, size=plan(table,root,sectors)
    except ValueError as exc:
        print('[Storage] Expansion skipped: '+str(exc)); return
    header=run('dumpe2fs','-h',root)
    blocks=int(re.search(r'^Block count:\s+(\d+)',header,re.M)[1])
    blocksize=int(re.search(r'^Block size:\s+(\d+)',header,re.M)[1])
    grow=(size-partition['size'])*512 >= 64*1024**2
    fs_grow=partition['size']*512-blocks*blocksize >= 64*1024**2
    if not grow and not fs_grow:
        print('[Storage] Root filesystem already uses available space'); return
    idle()
    # /boot is separate on the supported layout, so a full root does not block backup.
    boot=os.path.realpath(run('findmnt','-n','-o','SOURCE','--target','/boot'))
    if boot != disk+'p1':
        raise RuntimeError('Separate boot partition required for partition backup')
    backup=Path('/boot')/('lugoware-partitions-'+time.strftime('%Y%m%d-%H%M%S')+'.txt')
    with backup.open('x') as stream:
        stream.write(run('sfdisk','--dump',disk)+'\n');stream.flush();os.fsync(stream.fileno())
    print('[Storage] Partition backup: '+str(backup), flush=True)
    if grow:
        command=['sfdisk','--no-reread','--no-tell-kernel','--wipe','never','--wipe-partitions','never','-N','2',disk]
        change='size='+str(size)+'\n'
        run(*command,'--no-act',input=change)
        idle()
        # Verify no partition changed since planning.
        if json.loads(run('sfdisk','--json',disk))['partitiontable'] != table:
            raise RuntimeError('Partition table changed; aborting')
        run(*command,input=change)
        updated=json.loads(run('sfdisk','--json',disk))['partitiontable']
        expected=json.loads(json.dumps(table))
        next(p for p in expected['partitions'] if p['node']==root)['size']=size
        if updated != expected:
            raise RuntimeError('Partition verification failed; stop installation and inspect backup')
    run('partx','--update','--nr','2',disk)
    expected_size=size if grow else partition['size']
    if int(run('blockdev','--getsz',root)) != expected_size:
        raise RuntimeError('Kernel size not updated; reboot manually and rerun installer')
    run('resize2fs',root)
    after=run('dumpe2fs','-h',root)
    count=int(re.search(r'^Block count:\s+(\d+)',after,re.M)[1])
    if expected_size*512-count*blocksize >= 64*1024**2:
        raise RuntimeError('Filesystem expansion incomplete')
    print('[Storage] Root filesystem expanded successfully')


if __name__ == '__main__':
    import fcntl
    with open('/run/lugoware-root-expand.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        main()
