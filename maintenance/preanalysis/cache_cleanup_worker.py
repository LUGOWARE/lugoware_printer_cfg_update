"""Idle-only orphan cache cleanup in a separate low-priority process."""
import json
import os
from pathlib import Path
import stat
import sys
import time
import urllib.request

FOLDERS = ('.cache/lugoware-preanalysis', '.cache/lugoware-tool-analysis',
           '.cache/KlipperScreen/toolchanges', '.cache/KlipperScreen/exclusion_eta')

def idle():
    try:
        with urllib.request.urlopen('http://127.0.0.1:7125/printer/objects/query?print_stats&lugo_preanalysis', timeout=2) as r:
            s=json.load(r)['result']['status']
        return (s['print_stats']['state'] in ('standby','complete','cancelled','error')
                and s['lugo_preanalysis']['state'] not in ('reading','finishing'))
    except Exception:
        return False

def identity(p):
    s=p.lstat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)

def missing(p):
    try: p.stat(); return False
    except FileNotFoundError: return True
    except OSError: return False

def source(data):
    for key in ('stamp','signature','identity'):
        value=data.get(key)
        if isinstance(value,list) and value and isinstance(value[0],str):
            return Path(value[0])
    key=data.get('key')
    if isinstance(key,list) and len(key)==2 and isinstance(key[1],list) and key[1] and isinstance(key[1][0],str):
        return Path(key[1][0])

def cleanup(home, root, is_idle=idle, sleep=time.sleep):
    root=root.resolve()
    if not root.is_dir() or not is_idle(): return 0
    candidates=[]
    for name in FOLDERS:
        folder=home/name
        if folder.is_symlink() or not folder.is_dir(): continue
        for cache in folder.glob('*.json'):
            if not is_idle(): return 0
            try:
                st=cache.lstat()
                if not stat.S_ISREG(st.st_mode) or st.st_size>16*1024*1024: continue
                before=identity(cache)
                data=json.loads(cache.read_text(encoding='utf-8'))
                p=source(data)
                if p is None or not p.is_absolute(): continue
                p=p.resolve()
                p.relative_to(root)
                # Removable media disappearing is not a confirmed G-code deletion.
                if 'usb' in p.relative_to(root).parts and not os.path.ismount(root/'usb'): continue
                if missing(p): candidates.append((cache,before,p))
            except (OSError,ValueError,TypeError,AttributeError): pass
            sleep(.005)
    if not candidates: return 0
    # Upload replacement/rename grace period; check file and cache again below.
    sleep(2.)
    removed=0
    for cache,before,p in candidates:
        if not is_idle() or not root.is_dir(): break
        try:
            if identity(cache)==before and missing(p):
                cache.unlink();removed+=1
        except OSError: pass
    return removed

if __name__=='__main__':
    os.nice(19)
    if len(sys.argv)!=2: raise SystemExit('Expected G-code root')
    print(cleanup(Path.home(),Path(sys.argv[1])))
