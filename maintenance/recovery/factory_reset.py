#!/usr/bin/env python3
"""Factory-only SSH tool. --check is read-only. No printer configuration edits."""
import argparse,fcntl,json,os,shutil,sys,time,urllib.request,urllib.parse
from pathlib import Path
HOME=Path.home();DATA=HOME/'printer_data';STATE=HOME/'.local/share/lugoware/first_run.json'
def api(path,method='GET'):
    req=urllib.request.Request('http://127.0.0.1:7125'+path,method=method,data=b'' if method=='POST' else None)
    with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)['result']
def write_state(status,**extra):
    STATE.parent.mkdir(parents=True,exist_ok=True);tmp=STATE.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(dict(status=status,step=0,**extra),f);f.flush();os.fsync(f.fileno())
    tmp.replace(STATE)
def checked_folder(path,expected):
    if path.is_symlink() or path.resolve()!=expected:raise RuntimeError('Unexpected folder: '+str(path))
    return path
def clear_folder(path):
    checked_folder(path,HOME.resolve()/path.relative_to(HOME))
    if not path.exists():return
    for item in path.iterdir():
        if item.is_symlink() or item.is_file():item.unlink()
        elif item.is_dir():shutil.rmtree(item)
def check():
    status=api('/printer/objects/query?print_stats&extruder&heater_bed&lugo_recovery&lugo_diagnostics')['status']
    reasons=[]
    if status.get('print_stats',{}).get('state') in ('printing','paused'):reasons.append('Print is active')
    if status.get('lugo_recovery',{}).get('recovering'):reasons.append('Recovery is active')
    diag=status.get('lugo_diagnostics',{})
    if diag.get('active') or diag.get('running') or diag.get('busy'):reasons.append('Diagnostics are active')
    for name in ('extruder','heater_bed'):
        if name not in status or status[name].get('target',0)>0:reasons.append('Heater target must be OFF: '+name)
    roots=api('/server/files/roots');root=next(x for x in roots if x['name']=='gcodes')
    folder=checked_folder(Path(root['path']),HOME.resolve()/'printer_data/gcodes')
    files=api('/server/files/list?root=gcodes')
    jobs=api('/server/history/totals').get('job_totals',{})
    return {'machine_id':Path('/etc/machine-id').read_text().strip(),'hostname':os.uname().nodename,
            'ready':not reasons,'reasons':reasons,'gcode_files':len(files),'history_count':jobs.get('total_jobs'),
            'delete':['G-code files and thumbnails','Print history and cumulative statistics','Queued jobs','Recovery journals','Diagnostic results','KlipperScreen runtime cache'],
            'preserve':['Printer configuration and calibration','Network credentials','Firmware and update channel'],
            'files':files}
def service(name,action):return api('/machine/services/'+action+'?service='+name,'POST')
def reset(expected):
    plan=check()
    if expected!=plan['machine_id']:raise RuntimeError('Printer identity changed; reconnect')
    if not plan['ready']:raise RuntimeError('; '.join(plan['reasons']))
    write_state('resetting')
    try:
        api('/server/job_queue/pause','POST')
        api('/server/job_queue/job?all=true','DELETE')
        # Stop writers before clearing their state. Moonraker remains available.
        service('KlipperScreen','stop');service('klipper','stop')
        for item in plan['files']:
            path=item['path']
            api('/server/files/gcodes/'+urllib.parse.quote(path,safe='/'),'DELETE')
        api('/server/history/job?all=true','DELETE')
        api('/server/history/reset_totals','POST')
        for p in (DATA/'gcodes',DATA/'recovery',HOME/'.cache/lugoware-tool-analysis',HOME/'.cache/KlipperScreen'):
            clear_folder(p)
        for n in ('lugoware_diagnostics.jsonl','lugoware_diagnostics.previous.jsonl'):
            p=DATA/'logs'/n
            if p.is_symlink():p.unlink()
            elif p.exists():p.unlink()
        # Verify before marking complete; a failure is rerunnable, never hidden.
        if api('/server/files/list?root=gcodes'):raise RuntimeError('G-code list is not empty')
        if api('/server/history/list?limit=1').get('count',0):raise RuntimeError('History is not empty')
        write_state('pending')
        service('klipper','start');service('KlipperScreen','start')
        return {'ok':True,'message':'Factory reset completed. First-run setup is ready.'}
    except Exception as exc:
        write_state('failed',error=str(exc))
        for name in ('klipper','KlipperScreen'):
            try:service(name,'start')
            except Exception:pass
        raise

def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');p.add_argument('--reset',action='store_true');p.add_argument('--confirm')
    args=p.parse_args()
    try:
        if args.reset:
            if not args.confirm:raise RuntimeError('--confirm MACHINE_ID is required. Run --check first.')
            lock=HOME/'.local/share/lugoware/factory-reset.lock';lock.parent.mkdir(parents=True,exist_ok=True)
            with lock.open('w') as f:
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);result=reset(args.confirm)
        else:result=check();result.pop('files',None)
        print(json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),flush=True);sys.exit(1)
if __name__=='__main__':main()
