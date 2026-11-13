"""Read-only G-code preparation in a low-priority process, persistent cache."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import re
import math
import csv

HERE = Path(__file__).resolve().parent
UI = Path.home() / 'KlipperScreen/ks_includes'
sys.path[:0] = [str(HERE), str(UI)]
from lugo_preanalysis import stamp
from recovery_index import MARKER, CURA, HEIGHT




def progress(value):
    print(json.dumps({'progress': value}), flush=True)

def scan(path, identity):
    digest=hashlib.sha256();layers=[];timeline=[];commands=[];used=set()
    offset=0;total=0;current=None;head=bytearray();tail=bytearray();last_report=0.
    used_command=re.compile(r'^\s*(?:N\d+\s+)?(START_PRINT|CHANGE_TOOL|T[0-3])(?=\s|\*|$)',re.I)
    def lines(stream):
        pending=b''
        while True:
            chunk=stream.read(1048576)
            if not chunk:break
            digest.update(chunk)
            if len(head)<262144:head.extend(chunk[:262144-len(head)])
            tail.extend(chunk);del tail[:-262144]
            rows=(pending+chunk).split(b'\n');pending=rows.pop()
            for row in rows:yield row+b'\n'
        if pending:yield pending
    with path.open('rb') as stream:
        for raw in lines(stream):
            start=offset;offset+=len(raw)
            if offset//262144 != start//262144:
                now=time.monotonic()
                if now-last_report>.15:
                    progress(.02+.94*offset/max(identity[3],1));last_report=now
            # G0/G1 moves dominate large files; no text decode or regex needed.
            candidate=raw.lstrip()
            if not candidate.startswith((b';',b'M',b'm',b'T',b't',b'S',b's',b'C',b'c',b'E',b'e',b'N',b'n')):continue
            line=raw.decode('utf-8','replace').strip()
            if line.startswith(';'):
                if MARKER.match(line) or CURA.match(line):
                    if len(layers)>=100000:raise ValueError('Too many layers')
                    layers.append(dict(offset=start,layer=len(layers)+1,height=None))
                elif layers:
                    m=HEIGHT.match(line)
                    if m and math.isfinite(float(m[1])):layers[-1]['height']=float(m[1])
            else:
                # Most lines are G0/G1 motion. No movement parsing is needed
                # for the print-start gate; the display ETA owns that work.
                code=line.split(';',1)[0].strip()
                command=code.split(None,1)[0].upper() if code else ''
                if command=='M73':
                    m=re.search(r'\bR([\d.]+)\b',line,re.I)
                    if m and len(timeline)<100000:
                        seconds=float(m[1])*60
                        if math.isfinite(seconds) and (not timeline or seconds<=timeline[-1]['remaining']):timeline.append(dict(offset=start,remaining=seconds))
                if command in ('START_PRINT','END_PRINT','PRINT_END','CHANGE_TOOL','M104','M109','EXCLUDE_OBJECT_START') or (command.startswith('T') and command[1:].isdigit()):
                    commands.append([start,code])
                    if len(commands)>200000:raise ValueError('First tool index exceeds safe size limit')
                if command in ('START_PRINT','CHANGE_TOOL') or (command.startswith('T') and command[1:].isdigit()):
                    target=None
                    if command=='START_PRINT':
                        m=re.search(r'\bINITIAL_TOOL=(\d+)\b',code,re.I);target=int(m[1]) if m else 0
                    elif command=='CHANGE_TOOL':
                        m=re.search(r'\bNEXT_TOOL=(\d+)\b',code,re.I);target=int(m[1]) if m else None
                    else:target=int(command[1:])
                    if target is not None and target!=current:total+=1;current=target
                if command.startswith(('T','START_PRINT','CHANGE_TOOL','N')):
                    m=used_command.match(code)
                    if m:
                        name=m[1].upper()
                        if name.startswith('T'):used.add(int(name[1:]))
                        else:
                            key='INITIAL_TOOL' if name=='START_PRINT' else 'NEXT_TOOL'
                            param=re.search(r'\b'+key+r'\s*=\s*([0-3])(?=\s|\*|$)',code,re.I)
                            if param:used.add(int(param[1]))
                            elif name=='START_PRINT':used.add(0)
    values={}
    text=(bytes(head)+b'\n'+bytes(tail[-262144:])).decode('utf-8','replace')
    for line in text.splitlines():
        m=re.match(r';\s*(filament_settings_id|lugo_tool_materials|filament_type|nozzle_temperature|nozzle_temperature_initial_layer)\s*=\s*(.*)$',line)
        if m:values[m[1]]=next(csv.reader([m[2]],delimiter=',' if m[1].startswith('nozzle_temperature') else ';',escapechar='\\'))
    recovery=dict(identity=dict(sha256=digest.hexdigest(),size=identity[3],mtime_ns=identity[4]),layers=layers,timeline=timeline)
    return recovery,dict(metadata=values,used=sorted(used)),total,commands

def prepare(path):
    path = Path(path).resolve(); identity = stamp(path)
    dependencies = [HERE / n for n in ('preanalysis_worker.py', 'recovery_index.py', 'recovery_objects.py', 'lugo_tool_temperature.py')]
    dependencies += [UI / n for n in ('toolchange_count.py',)]
    version = hashlib.sha256(b''.join(p.read_bytes() for p in dependencies)).hexdigest()
    folder = Path.home()/'.cache/lugoware-preanalysis'; folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(path).encode()).hexdigest(); cache = folder/(key+'.json')
    try:
        saved = json.loads(cache.read_text())
        if saved['stamp'] == identity and saved['version'] == version:
            # Screen cache files can be removed independently: repopulate them.
            for name, payload in saved['screen_caches'].items():
                target = Path.home()/'.cache/KlipperScreen'/name/(key+'.json')
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix('.prepare.tmp'); tmp.write_text(json.dumps(payload)); os.replace(tmp, target)
            progress(1.)
            return {k: saved[k] for k in ('stamp', 'recovery', 'tools', 'first_commands')}
    except (OSError, ValueError, KeyError, TypeError): pass
    progress(.02)
    recovery, tools, total, commands = scan(path, identity)
    if stamp(path) != identity: raise ValueError('G-code changed during analysis')
    stat = path.stat(); screen_identity = [str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino]
    saved = dict(version=version, stamp=identity, recovery=recovery, tools=tools, first_commands=commands,
        screen_caches={'toolchanges':dict(identity=screen_identity, total=total)})
    tmp = cache.with_suffix('.tmp'); tmp.write_text(json.dumps(saved)); os.replace(tmp, cache)
    # Bound disk usage to 64 most recently prepared files. Only own cache.
    entries = sorted(folder.glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
    for old in entries[64:]: old.unlink()
    progress(1.)
    return {k: saved[k] for k in ('stamp', 'recovery', 'tools', 'first_commands')}

if __name__ == '__main__':
    if hasattr(os, 'nice'): os.nice(10)
    print(json.dumps({'result': prepare(sys.argv[1])}), flush=True)
