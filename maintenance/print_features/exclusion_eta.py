"""Display-only exclusion ETA. All G-code scanning runs in a low-priority child."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

PARAM = re.compile(r'([XYZEFIJKRSP])\s*(-?(?:\d+(?:\.\d*)?|\.\d+))', re.I)
NAME = re.compile(r'\bNAME=([^\s;]+)', re.I)

def build_index(path):
    xyz = [0., 0., 0.]
    e = 0.; feed = 1800.; absolute = True; relative_e = False
    tool_seconds = None
    owner = None; pending_tool = None; records = []; events = []
    bucket = None; position = 0; lines = 0; total = 0.
    with open(path, 'rb') as stream:
        for raw in stream:
            start = position; position += len(raw); lines += 1
            if lines % 2048 == 0:
                time.sleep(.02)  # Yield CPU/I/O even on controllers under load.
            decoded = raw.decode('utf-8', 'replace')
            match = re.match(r';\s*machine_tool_change_time\s*=\s*([0-9.]+)', decoded)
            if match:tool_seconds=float(match[1])
            line = decoded.split(';', 1)[0].strip()
            if not line:
                continue
            command = line.split()[0].upper()
            if command in ('START_PRINT', 'CHANGE_TOOL'):
                key = 'INITIAL_TOOL' if command == 'START_PRINT' else 'NEXT_TOOL'
                match = re.search(r'\b'+key+r'=(\d+)', line, re.I)
                if match:pending_tool = (start, int(match[1]))
            elif re.fullmatch(r'T\d+', command):
                if pending_tool is None or pending_tool[1] != int(command[1:]):
                    pending_tool = (start, int(command[1:]))
            elif command == 'EXCLUDE_OBJECT_START':
                match = NAME.search(line)
                owner = match[1].upper() if match else None
                if pending_tool is not None:
                    events.append([pending_tool[0], pending_tool[1], owner]);pending_tool = None
            # Retain the last owner across END/START wipe gaps. These are only
            # estimation weights; this code never filters executable moves.
            elif command in ('G90', 'G91'):absolute = command == 'G90'
            elif command in ('M82', 'M83'):relative_e = command == 'M83'
            elif command == 'G92':
                values = dict((k.upper(),float(v)) for k,v in PARAM.findall(line[len(command):]))
                if 'E' in values:e = values['E']
                for i,k in enumerate('XYZ'):
                    if k in values:xyz[i] = values[k]
            elif command in ('G0','G1','G2','G3','G4'):
                values = dict((k.upper(),float(v)) for k,v in PARAM.findall(line[len(command):]))
                if command == 'G4':
                    seconds = values.get('P',0)/1000 + values.get('S',0)
                else:
                    feed = values.get('F',feed)
                    target = [values.get(k,xyz[i] if absolute else 0)+(0 if absolute else xyz[i]) for i,k in enumerate('XYZ')]
                    extrusion = values.get('E',0 if relative_e else e)
                    de = extrusion if relative_e else extrusion-e
                    distance = math.sqrt(sum((a-b)**2 for a,b in zip(target,xyz)))
                    if command in ('G2','G3') and ('I' in values or 'J' in values):
                        cx,cy=xyz[0]+values.get('I',0),xyz[1]+values.get('J',0)
                        radius=math.hypot(xyz[0]-cx,xyz[1]-cy)
                        first=math.atan2(xyz[1]-cy,xyz[0]-cx);last=math.atan2(target[1]-cy,target[0]-cx)
                        angle=(first-last if command=='G2' else last-first)%(2*math.pi)
                        if angle==0:angle=2*math.pi
                        distance=math.hypot(radius*angle,target[2]-xyz[2])
                    seconds = (distance if distance>0 else abs(de))*60/max(feed,1)
                    xyz=target;e=e+extrusion if relative_e else extrusion
                if math.isfinite(seconds) and seconds>0:
                    total += seconds
                    if bucket is None or bucket[2]!=owner or position-bucket[0]>131072:
                        bucket=[start,position,owner,seconds];records.append(bucket)
                    else:
                        bucket[1]=position;bucket[3]+=seconds
            if len(records)>100000 or len(events)>100000:
                raise ValueError('ETA index limit reached')
    return dict(records=records,events=events,total=total,tool_seconds=tool_seconds)

def index_file(path, cache_dir=None):
    path=Path(path).resolve()
    def stamp():
        s=path.stat();return [str(path),s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_ino]
    identity=stamp();folder=Path(cache_dir) if cache_dir else Path.home()/'.cache/KlipperScreen/exclusion_eta'
    cache=folder/(hashlib.sha256(str(path).encode()).hexdigest()+'.json')
    try:
        result=json.loads(cache.read_text())
        if result.get('version')==2 and result.get('identity')==identity:return result['index']
    except (OSError,ValueError,KeyError):pass
    index=build_index(path)
    if stamp()!=identity:raise ValueError('File changed during ETA analysis')
    try:
        folder.mkdir(parents=True,exist_ok=True)
        temp=cache.with_suffix('.%d.tmp'%os.getpid())
        temp.write_text(json.dumps(dict(version=2,identity=identity,index=index)));os.replace(temp,cache)
    except OSError:pass
    return index

def work_left(index, excluded, position, slicer):
    excluded=set(excluded);total=index['total'];motion=0.;changes=0;raw=0;old=None
    for offset,tool,owner in index['events']:
        if tool!=old:raw+=1;old=tool
    old=None
    for offset,tool,owner in index['events']:
        if owner in excluded:continue
        if tool!=old:
            if offset>=position:changes+=1
            old=tool
    for start,end,owner,seconds in index['records']:
        if end>position and owner not in excluded:
            motion+=seconds*min(1.,max(0.,(end-position)/max(1,end-start)))
    tool=index.get('tool_seconds')
    if tool is None:return None
    scale=max(1.,(slicer-raw*tool)/max(total,1))
    return motion*scale+changes*tool

def interpolate(points, position):
    for (x0,y0),(x1,y1) in zip(points,points[1:]):
        if position<=x1:return y0+(y1-y0)*min(1.,max(0.,(position-x0)/max(1,x1-x0)))
    return points[-1][1]

def atomic(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data));os.replace(tmp,path)

def warmup_ratio(dt, consumed):
    # Slow first layers and sparse profile points are not whole-print speed.
    # Require both observation time and meaningful consumed work, then blend.
    if dt <= 120 or consumed <= 60:
        return 1.
    confidence = min(1., (dt-120)/180., (consumed-60)/120.)
    measured = max(1., min(3., dt/consumed))
    return 1. + confidence*(measured-1.)

def calculate(root, filename, excluded, position, slicer, elapsed):
    import urllib.request
    path=(Path(root).expanduser()/filename).resolve();path.relative_to(Path(root).expanduser().resolve())
    index=index_file(path)
    st=path.stat();identity=[str(path),st.st_size,st.st_mtime_ns,sorted(excluded)]
    digest=hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    folder=Path.home()/'.cache/KlipperScreen/exclusion_eta'
    # Moonraker job IDs survive screen restart and distinguish repeat prints.
    jobs=json.load(urllib.request.urlopen('http://localhost:7125/server/history/list?limit=1&order=desc',timeout=3))['result']['jobs']
    job=jobs[0]
    if job['filename']!=filename or job['status']!='in_progress':return None
    key=[job['job_id'],identity]
    statepath=folder/'active-v3.json';state={}
    try:state=json.loads(statepath.read_text())
    except (OSError,ValueError):pass
    if state.get('key')!=key:state={'key':key,'samples':[]}
    samples=state['samples']
    base=work_left(index,excluded,position,slicer)
    if base is None:return None
    profilepath=folder/('profile-'+digest+'.json')
    try:
        profile=json.loads(profilepath.read_text());points=profile['points']
        if profile['identity']==identity:base=max(0.,points[-1][1]-interpolate(points,position))
    except (OSError,ValueError,KeyError,IndexError):pass
    if samples and (elapsed<samples[-1][0] or position<samples[-1][1]):samples=[]
    samples.append([elapsed,position,base]);samples=samples[-2048:]
    first=samples[0];dt=elapsed-first[0];consumed=first[2]-base
    ratio=warmup_ratio(dt, consumed)
    remaining=base*ratio
    state['samples']=samples;atomic(statepath,state)
    return remaining

def adjusted_total(panel, original, elapsed):
    from gi.repository import GLib
    import subprocess,sys,threading
    printer=panel._printer
    excluded=tuple(sorted(printer.get_stat('exclude_object','excluded_objects') or []))
    filename=printer.get_stat('print_stats','filename')
    actual=float(printer.get_stat('print_stats','print_duration') or 0)
    duration=float(printer.get_stat('print_stats','total_duration') or 0)
    if not excluded or not filename or panel.state not in ('printing','paused'):return original
    if actual<1:return 0
    if duration+1<getattr(panel,'_eta3_duration',0):panel._eta3_epoch=getattr(panel,'_eta3_epoch',0)+1
    panel._eta3_duration=duration
    key=(filename,excluded,getattr(panel,'_eta3_epoch',0))
    if getattr(panel,'_eta3_key',None)!=key:
        panel._eta3_key=key;panel._eta3_result=None;panel._eta3_next=0
    if not getattr(panel,'_eta3_busy',False) and time.monotonic()>=getattr(panel,'_eta3_next',0):
        panel._eta3_busy=True
        root=printer.get_config_section('virtual_sdcard').get('path','')
        position=int(printer.get_stat('virtual_sdcard','file_position') or 0)
        slicer=float(panel.file_metadata.get('estimated_time') or 0)
        def work():
            value=None
            try:
                args=[sys.executable,'-I',__file__,root,filename,json.dumps(excluded),str(position),str(slicer),str(actual)]
                result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=180,check=True)
                value=json.loads(result.stdout)['remaining']
                if value is not None and (not math.isfinite(value) or value<0):value=None
            except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
            def done():
                panel._eta3_busy=False
                if panel._eta3_key==key:
                    if value is not None:panel._eta3_result=(value,actual)
                    panel._eta3_next=time.monotonic()+30
                return False
            GLib.idle_add(done)
        threading.Thread(target=work,daemon=True).start()
    result=getattr(panel,'_eta3_result',None)
    if result is None:return 0
    seconds,at=result
    return elapsed+max(0.,seconds-max(0.,actual-at))

if __name__=='__main__':
    import sys,resource
    os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
    try:value=calculate(sys.argv[1],sys.argv[2],json.loads(sys.argv[3]),int(sys.argv[4]),float(sys.argv[5]),float(sys.argv[6]))
    except Exception:value=None
    print(json.dumps({'remaining':value}))
